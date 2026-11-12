# /// script
# requires-python = ">=3.12"
# dependencies = ["pyyaml>=6,<7"]
# ///
from __future__ import annotations

import argparse
import fnmatch
import io
import os
import re
import subprocess
import sys
import tokenize
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterator, Protocol

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DESCRIPTION = "Apply the brand defined in a2/brand.yaml to the working tree (deterministic and idempotent)."
MARKERS = ("ermes", "ERMES")
GIT_TIMEOUT_SECONDS = 120
DERIVE_TIMEOUT_SECONDS = 1800

Rule = tuple[re.Pattern[str], str]


def mentions_upstream(text: str) -> bool:
    return any(marker in text for marker in MARKERS)


@dataclass(frozen=True)
class Brand:
    values: dict[str, str]

    def expand(self, template: str) -> str:
        return re.sub(r"\{(\w+)\}", lambda m: self.values.get(m.group(1), m.group(0)), template)

    def compile(self, items: list) -> list[Rule]:
        return [(re.compile(self.expand(item["match"])), self.expand(item["replace"])) for item in flatten_rules(items)]


def flatten_rules(items: list) -> Iterator[dict]:
    for item in items:
        if isinstance(item, list):
            yield from flatten_rules(item)
        else:
            yield item


class Rebrander:
    def __init__(self, brand: Brand, keep: list[str], rules: list[dict]):
        self.keep = re.compile("|".join(f"(?:{brand.expand(pattern)})" for pattern in keep)) if keep else None
        self.rules = brand.compile(rules)

    def apply(self, text: str, before: list[Rule] = (), after: list[Rule] = ()) -> str:
        if not mentions_upstream(text):
            return text
        kept: list[str] = []

        def stash(match: re.Match[str]) -> str:
            kept.append(match.group(0))
            return f"\x00{len(kept) - 1}\x00"

        if self.keep:
            text = self.keep.sub(stash, text)
        for pattern, replacement in (*before, *self.rules, *after):
            text = pattern.sub(replacement, text)
        return re.sub(r"\x00(\d+)\x00", lambda m: kept[int(m.group(1))], text)


def scoped(patterns: list[tuple[str | None, re.Pattern[str]]], path: str) -> list[re.Pattern[str]]:
    return [pattern for scope, pattern in patterns if scope is None or fnmatch.fnmatchcase(path, scope)]


LITERAL = re.compile(r"^([A-Za-z]*)('''|\"\"\"|'|\"|`|/)(.*?)(\2[A-Za-z]*)?\Z", re.DOTALL)
NESTED_STRING = re.compile(r"'[^'\n]*'|\"[^\"\n]*\"")


@dataclass
class LiteralRewriter:
    rebrander: Rebrander
    keep_lines: list[tuple[str | None, re.Pattern[str]]]
    keep_spans: list[tuple[str | None, re.Pattern[str]]]

    def rewrite(self, text: str, path: str, spans: Iterator[tuple[int, int, Callable[[str], str] | None]]) -> str:
        keep = scoped(self.keep_lines, path)
        protected = [match.span() for pattern in scoped(self.keep_spans, path) for match in pattern.finditer(text)]
        out: list[str] = []
        cursor = 0
        for start, end, special in spans:
            if any(start < stop and begin < end for begin, stop in protected):
                continue
            pieces = self.pieces(text, start, end, keep)
            out.append(text[cursor:start])
            if not any(kept for _, _, kept in pieces):
                chunk = text[start:end]
                out.append(special(chunk) if special else self.literal(chunk))
            else:
                for piece_start, piece_end, kept in pieces:
                    piece = text[piece_start:piece_end]
                    out.append(piece if kept else self.literal(piece) if piece_start == start else self.rebrander.apply(piece))
            cursor = end
        out.append(text[cursor:])
        return "".join(out)

    @staticmethod
    def pieces(text: str, start: int, end: int, keep: list[re.Pattern[str]]) -> list[tuple[int, int, bool]]:
        result: list[tuple[int, int, bool]] = []
        position = start
        while position < end:
            line_start = text.rfind("\n", 0, position) + 1
            line_end = text.find("\n", position)
            line_end = len(text) if line_end == -1 else line_end
            kept = any(pattern.search(text[line_start:line_end]) for pattern in keep)
            piece_end = min(end, line_end + 1)
            if result and result[-1][2] == kept:
                result[-1] = (result[-1][0], piece_end, kept)
            else:
                result.append((position, piece_end, kept))
            position = piece_end
        return result

    def literal(self, chunk: str) -> str:
        match = LITERAL.match(chunk)
        if not match:
            return self.rebrander.apply(chunk)
        prefix, quote, body, closing = match.groups()
        return f"{prefix}{quote}{self.rebrander.apply(body)}{closing or ''}"

    def nested(self, code: str) -> str:
        return NESTED_STRING.sub(lambda m: self.literal(m.group(0)), code)


class Transformer(Protocol):
    def __call__(self, text: str, path: str) -> str: ...


@dataclass
class PlainText:
    rebrander: Rebrander

    def __call__(self, text: str, path: str) -> str:
        return self.rebrander.apply(text)


FSTRING_STARTS = {tokenize.FSTRING_START, getattr(tokenize, "TSTRING_START", tokenize.FSTRING_START)}
FSTRING_ENDS = {tokenize.FSTRING_END, getattr(tokenize, "TSTRING_END", tokenize.FSTRING_END)}
DOCSTRING_LEADERS = {tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT, tokenize.ENCODING}


@dataclass
class PythonStrings:
    rewriter: LiteralRewriter
    docstrings: bool

    def __call__(self, text: str, path: str) -> str:
        if not mentions_upstream(text):
            return text
        return self.rewriter.rewrite(text, path, self.spans(text))

    def spans(self, text: str) -> Iterator[tuple[int, int, Callable[[str], str] | None]]:
        offsets = [0, 0]
        for line in io.StringIO(text):
            offsets.append(offsets[-1] + len(line))
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
        previous = tokenize.NEWLINE
        fstring_start = 0
        depth = 0
        for index, token in enumerate(tokens):
            start = offsets[token.start[0]] + token.start[1]
            end = offsets[token.end[0]] + token.end[1]
            if token.type in FSTRING_STARTS:
                fstring_start = start if depth == 0 else fstring_start
                depth += 1
            elif token.type in FSTRING_ENDS:
                depth -= 1
                if depth == 0:
                    yield fstring_start, end, self.fstring
            elif token.type == tokenize.STRING and depth == 0 and self.rebrandable(tokens, index, previous):
                yield start, end, None
            if token.type not in (tokenize.NL, tokenize.COMMENT):
                previous = token.type

    def rebrandable(self, tokens: list[tokenize.TokenInfo], index: int, previous: int) -> bool:
        return self.docstrings or not self.is_docstring(tokens, index, previous)

    @staticmethod
    def is_docstring(tokens: list[tokenize.TokenInfo], index: int, previous: int) -> bool:
        if previous not in DOCSTRING_LEADERS:
            return False
        following = next((t for t in tokens[index + 1 :] if t.type not in (tokenize.NL, tokenize.COMMENT)), None)
        return following is None or following.type in (tokenize.NEWLINE, tokenize.ENDMARKER)

    def fstring(self, chunk: str) -> str:
        match = LITERAL.match(chunk)
        prefix, quote, body, closing = match.groups() if match else ("", "", chunk, "")
        out: list[str] = []
        literal: list[str] = []
        depth = 0
        index = 0
        while index < len(body):
            char = body[index]
            if depth == 0 and body.startswith(("{{", "}}"), index):
                literal.append(body[index : index + 2])
                index += 2
                continue
            if depth == 0 and char == "{":
                out.append(self.rewriter.rebrander.apply("".join(literal)))
                literal = []
                expression_start = index
            if char == "{":
                depth += 1
            elif char == "}" and depth:
                depth -= 1
                if depth == 0:
                    out.append(self.rewriter.nested(body[expression_start : index + 1]))
                    index += 1
                    continue
            if depth == 0:
                literal.append(char)
            index += 1
        if depth:
            out.append(body[expression_start:])
        out.append(self.rewriter.rebrander.apply("".join(literal)))
        return f"{prefix}{quote}{''.join(out)}{closing or ''}"


REGEX_PRECEDERS = set("(,=:[!&|?{};+-*%<>~^") | {""}
REGEX_KEYWORDS = {"return", "typeof", "case", "do", "else", "in", "of", "new", "delete", "void", "throw", "yield", "await"}


@dataclass
class ScriptStrings:
    rewriter: LiteralRewriter

    def __call__(self, text: str, path: str) -> str:
        if not mentions_upstream(text):
            return text
        return self.rewriter.rewrite(text, path, self.spans(text))

    def spans(self, src: str) -> Iterator[tuple[int, int, Callable[[str], str] | None]]:
        index = 0
        length = len(src)
        last = ""
        while index < length:
            char = src[index]
            if src.startswith("//", index):
                end = src.find("\n", index)
                index = length if end == -1 else end
            elif src.startswith("/*", index):
                end = src.find("*/", index + 2)
                index = length if end == -1 else end + 2
            elif char in "'\"`":
                end = self.string_end(src, index, char)
                yield index, end, None
                index, last = end, "a"
            elif char == "/" and (last in REGEX_PRECEDERS or last in REGEX_KEYWORDS):
                end = self.regex_end(src, index)
                if end > index + 1:
                    yield index, end, None
                index, last = end, "a"
            elif char.isalnum() or char in "_$":
                end = index
                while end < length and (src[end].isalnum() or src[end] in "_$"):
                    end += 1
                word = src[index:end]
                index, last = end, word if word in REGEX_KEYWORDS else "a"
            else:
                if not char.isspace():
                    last = char if char in REGEX_PRECEDERS else ")"
                index += 1

    @staticmethod
    def string_end(src: str, start: int, quote: str) -> int:
        index = start + 1
        depth = 0
        length = len(src)
        while index < length:
            char = src[index]
            if char == "\\":
                index += 2
                continue
            if quote == "`" and src.startswith("${", index):
                depth += 1
                index += 2
                continue
            if quote == "`" and depth and char == "}":
                depth -= 1
            elif char == quote and not depth:
                return index + 1
            elif quote != "`" and char == "\n":
                return index
            index += 1
        return length

    @staticmethod
    def regex_end(src: str, start: int) -> int:
        index = start + 1
        in_class = False
        length = len(src)
        while index < length:
            char = src[index]
            if char == "\\":
                index += 2
                continue
            if char == "\n":
                return start + 1
            if char == "[":
                in_class = True
            elif char == "]":
                in_class = False
            elif char == "/" and not in_class:
                index += 1
                while index < length and src[index].isalpha():
                    index += 1
                return index
            index += 1
        return start + 1


KEY_LINE = re.compile(r"^(\s*)(\"[^\"]+\"|'[^']+'|[^\s#\"'][^:#]*?):(\s+|$)(.*)$")
BLOCK_INDICATOR = re.compile(r"^[|>][-+0-9]*\s*$")


@dataclass
class LocaleDocument:
    rebrander: Rebrander
    skip_keys: frozenset[str]
    language_rules: dict[str, dict[str, list[Rule]]]
    key_rules: dict[str, list[Rule]]
    language_rebranders: dict[str, Rebrander]

    def __call__(self, text: str, path: str) -> str:
        language = Path(path).name.split(".", 1)[0]
        output: list[str] = []
        block_indent: int | None = None
        block_key = ""
        for line in text.split("\n"):
            stripped = line.strip()
            indent = len(line) - len(line.lstrip(" "))
            if block_indent is not None:
                if stripped == "" or indent > block_indent:
                    output.append(self.value(line, language, block_key))
                    continue
                block_indent = None
            if stripped == "" or stripped.startswith("#"):
                output.append(line)
                continue
            match = KEY_LINE.match(line)
            if not match:
                raise ValueError(f"{path}: unexpected line: {line!r}")
            lead, raw_key, separator, value = match.groups()
            key = raw_key.strip("\"'")
            if BLOCK_INDICATOR.match(value):
                block_indent, block_key = indent, key
                output.append(line)
            elif not value or key in self.skip_keys:
                output.append(line)
            else:
                output.append(f"{lead}{raw_key}:{separator}{self.value(value, language, key)}")
        result = "\n".join(output)
        self.validate(text, result, path)
        return result

    def value(self, value: str, language: str, key: str) -> str:
        rules = self.language_rules.get(language, {})
        before = [*self.key_rules.get(key, []), *rules.get("before", [])]
        rebrander = self.language_rebranders.get(language, self.rebrander)
        return rebrander.apply(value, before, rules.get("after", []))

    @staticmethod
    def validate(before_text: str, after_text: str, path: str) -> None:
        before, after = flatten(yaml.safe_load(before_text)), flatten(yaml.safe_load(after_text))
        if before.keys() != after.keys():
            raise ValueError(f"{path}: key set changed")
        for key, old in before.items():
            new = after[key]
            if isinstance(old, str) and sorted(re.findall(r"\{[^}]*\}", old)) != sorted(re.findall(r"\{[^}]*\}", new)):
                raise ValueError(f"{path}: placeholders changed in {key}")


def flatten(node: object, prefix: str = "") -> dict[str, object]:
    if not isinstance(node, dict):
        return {prefix: node}
    flat: dict[str, object] = {}
    for key, value in node.items():
        flat.update(flatten(value, f"{prefix}.{key}" if prefix else str(key)))
    return flat


@dataclass
class Edit:
    path: str
    pattern: re.Pattern[str]
    replacement: str

    def apply(self, text: str) -> tuple[str, bool]:
        updated, count = self.pattern.subn(self.replacement, text)
        return updated, count > 0 or self.result in text

    @property
    def result(self) -> str:
        return re.sub(r"\\(g<\w+>|\d+|n|\\)", lambda m: {"n": "\n", "\\": "\\"}.get(m.group(1), ""), self.replacement)


@dataclass
class Target:
    include: list[str]
    exclude: list[str]
    transformer: Transformer

    def matches(self, path: str) -> bool:
        return any(fnmatch.fnmatchcase(path, pattern) for pattern in self.include) and not any(
            fnmatch.fnmatchcase(path, pattern) for pattern in self.exclude
        )


@dataclass
class BrandOverlay:
    root: Path
    config: dict
    brand: Brand = field(init=False)
    targets: list[Target] = field(init=False)
    edits: list[Edit] = field(init=False)
    stale: list[str] = field(init=False, default_factory=list)

    def __post_init__(self) -> None:
        self.brand = Brand({key: str(value) for key, value in self.config["brand"].items()})
        self.targets = [self.target(item) for item in self.config["targets"]]
        self.edits = [
            Edit(item["path"], re.compile(self.brand.expand(item["match"])), self.brand.expand(item["replace"]))
            for item in self.config.get("edits", [])
        ]

    def rebrander(self, name: str) -> Rebrander:
        rules = self.config["rules"][name]
        return Rebrander(self.brand, self.config.get("keep", []) + rules.get("keep", []), rules["replace"])

    def rewriter(self, name: str) -> LiteralRewriter:
        return LiteralRewriter(self.rebrander(name), self.scoped_patterns("keep_lines"), self.scoped_patterns("keep_spans"))

    def scoped_patterns(self, key: str) -> list[tuple[str | None, re.Pattern[str]]]:
        return [
            (None, re.compile(item)) if isinstance(item, str) else (item["path"], re.compile(item["match"]))
            for item in self.config.get(key, [])
        ]

    def target(self, item: dict) -> Target:
        factories: dict[str, Callable[[], Transformer]] = {
            "python": lambda: PythonStrings(self.rewriter(item["rules"]), item.get("docstrings", False)),
            "script": lambda: ScriptStrings(self.rewriter(item["rules"])),
            "text": lambda: PlainText(self.rebrander(item["rules"])),
            "locale": lambda: self.locale(item["rules"]),
        }
        exclude = item.get("exclude", []) + self.config.get("exclude", [])
        return Target(item["include"], exclude, factories[item["format"]]())

    def locale(self, rules: str) -> LocaleDocument:
        locale = self.config["locale"]
        languages = {
            language: {phase: self.brand.compile(items) for phase, items in phases.items()}
            for language, phases in locale.get("languages", {}).items()
        }
        key_rules = {key: self.brand.compile(items) for key, items in locale.get("key_rules", {}).items()}
        overrides = {language: self.rebrander(name) for language, name in locale.get("rules", {}).items()}
        return LocaleDocument(self.rebrander(rules), frozenset(locale.get("skip_keys", [])), languages, key_rules, overrides)

    def tracked_files(self) -> list[str]:
        result = subprocess.run(["git", "ls-files", "-z"], cwd=self.root, check=True, capture_output=True,
                                stdin=subprocess.DEVNULL, timeout=GIT_TIMEOUT_SECONDS)
        return sorted(name for name in result.stdout.decode().split("\0") if name)

    def plan(self, only: list[str]) -> dict[str, str]:
        generated = {name: self.brand.expand(template) for name, template in self.config.get("generate", {}).items()}
        changes: dict[str, str] = {}
        for name in sorted(set(self.tracked_files()) | generated.keys()):
            if only and not any(name == item or name.startswith(item.rstrip("/") + "/") for item in only):
                continue
            path = self.root / name
            original = self.read(path)
            if name in generated:
                updated = generated[name]
            elif original is None:
                continue
            else:
                updated = self.transform(name, original)
            if updated != original:
                changes[name] = updated
        return changes

    @staticmethod
    def read(path: Path) -> str | None:
        if path.is_symlink() or not path.is_file():
            return None
        try:
            return path.read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            return None

    def transform(self, name: str, text: str) -> str:
        for edit in (edit for edit in self.edits if edit.path == name):
            text, settled = edit.apply(text)
            if not settled:
                self.stale.append(f"{name}: {edit.pattern.pattern}")
        target = next((target for target in self.targets if target.matches(name)), None)
        return target.transformer(text, name) if target else text

    def derived(self) -> list[list[str]]:
        return [item["run"] for item in self.config.get("derived", [])]


def outer_environment() -> dict[str, str]:
    own_bin = str(Path(sys.prefix) / "bin")
    env = {key: value for key, value in os.environ.items() if key not in ("VIRTUAL_ENV", "PYTHONHOME")}
    env["PATH"] = os.pathsep.join(entry for entry in env.get("PATH", "").split(os.pathsep) if entry != own_bin)
    return env


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=DESCRIPTION)
    parser.add_argument("paths", nargs="*", help="limit to these files or directories (relative to the root)")
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--check", action="store_true", help="only report files that would change")
    parser.add_argument("--derived", action="store_true", help="also regenerate derived files listed in the config")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    config_path = args.config or root / "a2" / "brand.yaml"
    overlay = BrandOverlay(root, yaml.safe_load(config_path.read_text(encoding="utf-8-sig")))
    changes = overlay.plan(args.paths)
    for name in sorted(changes):
        print(f"rebrand {name}")
    if args.check:
        return 1 if changes or overlay.stale else 0
    for name, text in changes.items():
        (root / name).write_bytes(text.encode("utf-8"))
    if args.derived and not overlay.stale:
        for command in overlay.derived():
            print(f"derive  {' '.join(command)}")
            subprocess.run(command, cwd=root, check=True, env=outer_environment(), stdin=subprocess.DEVNULL,
                           timeout=DERIVE_TIMEOUT_SECONDS)
    print(f"{len(changes)} files rebranded")
    for edit in overlay.stale:
        print(f"stale edit (matches nothing, result missing): {edit}", file=sys.stderr)
    return 2 if overlay.stale else 0


if __name__ == "__main__":
    sys.exit(main())
