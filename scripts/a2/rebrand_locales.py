# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""Rebrand user-visible Hermes names and CLI references in locales/*.yaml values to A2Assistant.
Run with `uv run scripts/a2/rebrand_locales.py [--check]`; --check only reports pending changes and leftovers.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import yaml

PRODUCT = "A2Assistant"
COMMAND = "a2assistant"
LOCALES_DIR = Path(__file__).resolve().parents[2] / "locales"

PORTAL_PAGE_KEYS = frozenset(
    {
        "killswitch_reason_overview",
        "killswitch_reason_buy",
        "charge_error_remote_spending_disabled",
        "allowed_but_org_off",
        "billing.overview.remoteSpendingOff",
        "slashCmd.topup.error.remoteSpendingDisabled",
    }
)
TERMINAL_SLASH_KEYS = frozenset({"mic_silent_macos_hint"})

LEFT = r"(?:(?<=\\[nt])|(?<![A-Za-z0-9_./~\\-]))"
RIGHT = r"(?![A-Za-z0-9_])"
KEEP = re.compile(r"Hermes Cloud|[Hh]ey [Hh]ermes|Hermes(?= 3\b)|X-Hermes-|Hermes\.app")
KEY_LINE = re.compile(r"^(\s*)(\"[^\"]+\"|'[^']+'|[^\s#\"'][^:#]*?):(\s+|$)(.*)$")
BLOCK_INDICATOR = re.compile(r"^[|>][-+0-9]*\s*$")

Rule = tuple[re.Pattern[str], str]

PRE_RULES: dict[str, list[Rule]] = {
    "hu": [
        (re.compile(LEFT + r"Hermes Agenthez"), PRODUCT + "hoz"),
        (re.compile(LEFT + r"Hermes-t\b"), PRODUCT + "-ot"),
        (re.compile(LEFT + r"Hermest\b"), PRODUCT + "ot"),
        (re.compile(LEFT + r"Hermesnek\b"), PRODUCT + "nak"),
        (re.compile(LEFT + r"Hermesszel\b"), PRODUCT + "tal"),
        (re.compile(LEFT + r"Hermesben\b"), PRODUCT + "ban"),
        (re.compile(LEFT + r"Hermesbe\b"), PRODUCT + "ba"),
    ],
    "tr": [
        (re.compile(LEFT + r"Hermes'in\b"), PRODUCT + "'ın"),
        (re.compile(LEFT + r"Hermes'i\b"), PRODUCT + "'ı"),
        (re.compile(LEFT + r"Hermes'e\b"), PRODUCT + "'a"),
        (re.compile(LEFT + r"hermes'ten\b"), COMMAND + "'tan"),
    ],
}
COMMON_RULES: list[Rule] = [
    (re.compile(LEFT + r"Hermes[ -]Agent" + RIGHT), PRODUCT),
    (re.compile(LEFT + r"Hermes" + RIGHT), PRODUCT),
    (re.compile(r"`hermes(?=[ `])"), "`" + COMMAND),
    (re.compile(LEFT + r"hermes(?![A-Za-z0-9_-])"), COMMAND),
]
POST_RULES: dict[str, list[Rule]] = {
    "hu": [
        (re.compile(r"(?<![^\s\"('„—–-])([Aa]) (" + PRODUCT + "|" + COMMAND + ")"), r"\1z \2"),
    ],
}
TERMINAL_SLASH_RULES: list[Rule] = [
    (re.compile(r"/Hermest\b"), "/" + PRODUCT + "ot"),
    (re.compile(r"/Hermes'e\b"), "/" + PRODUCT + "'a"),
    (re.compile(r"/Hermes" + RIGHT), "/" + PRODUCT),
]
LEFTOVER_CAPITAL = re.compile(r"Hermes")
LEFTOVER_LOWER = re.compile(r"(?<![\w./~`-])hermes(?![\w-])")


@dataclass
class FileResult:
    path: Path
    original: str
    rebranded: str
    replacements: int
    problems: list[str] = field(default_factory=list)
    leftovers: Counter[str] = field(default_factory=Counter)

    @property
    def changed(self) -> bool:
        return self.original != self.rebranded


def apply_rules(text: str, rules: list[Rule]) -> tuple[str, int]:
    total = 0
    for pattern, replacement in rules:
        text, count = pattern.subn(replacement, text)
        total += count
    return text, total


def rebrand_value(value: str, lang: str, key: str) -> tuple[str, int]:
    kept: list[str] = []

    def stash(match: re.Match[str]) -> str:
        kept.append(match.group(0))
        return f"\x00{len(kept) - 1}\x00"

    text = KEEP.sub(stash, value)
    rules = PRE_RULES.get(lang, []) + COMMON_RULES
    if key in TERMINAL_SLASH_KEYS:
        rules = TERMINAL_SLASH_RULES + rules
    text, count = apply_rules(text, rules)
    text, _ = apply_rules(text, POST_RULES.get(lang, []))
    text = re.sub(r"\x00(\d+)\x00", lambda m: kept[int(m.group(1))], text)
    return text, count


def rebrand_document(text: str, lang: str, source: Path) -> tuple[str, int]:
    output: list[str] = []
    total = 0
    block_indent: int | None = None
    block_key = ""
    for line in text.split("\n"):
        stripped = line.strip()
        indent = len(line) - len(line.lstrip(" "))
        if block_indent is not None:
            if stripped == "" or indent > block_indent:
                new_line, count = rebrand_value(line, lang, block_key)
                output.append(new_line)
                total += count
                continue
            block_indent = None
        if stripped == "" or stripped.startswith("#"):
            output.append(line)
            continue
        match = KEY_LINE.match(line)
        if not match:
            raise ValueError(f"{source}: unexpected line: {line!r}")
        lead, raw_key, separator, value = match.groups()
        key = raw_key.strip("\"'")
        if BLOCK_INDICATOR.match(value):
            block_indent, block_key = indent, key
            output.append(line)
            continue
        if not value or key in PORTAL_PAGE_KEYS:
            output.append(line)
            continue
        new_value, count = rebrand_value(value, lang, key)
        total += count
        output.append(f"{lead}{raw_key}:{separator}{new_value}")
    return "\n".join(output), total


def flatten(node: object, prefix: str = "") -> dict[str, object]:
    if not isinstance(node, dict):
        return {prefix: node}
    flat: dict[str, object] = {}
    for key, value in node.items():
        flat.update(flatten(value, f"{prefix}.{key}" if prefix else str(key)))
    return flat


def validate(result: FileResult) -> None:
    try:
        before = flatten(yaml.safe_load(result.original))
        after = flatten(yaml.safe_load(result.rebranded))
    except yaml.YAMLError as error:
        result.problems.append(f"YAML parse error: {error}")
        return
    if before.keys() != after.keys():
        result.problems.append(f"key set changed: {sorted(before.keys() ^ after.keys())}")
        return
    for key, old in before.items():
        new = after[key]
        if type(old) is not type(new):
            result.problems.append(f"type changed: {key}")
        elif isinstance(old, str) and sorted(re.findall(r"\{[^}]*\}", old)) != sorted(re.findall(r"\{[^}]*\}", new)):
            result.problems.append(f"placeholders changed: {key}")


def classify_leftovers(result: FileResult) -> None:
    for key, value in flatten(yaml.safe_load(result.rebranded)).items():
        if not isinstance(value, str):
            continue
        leaf = key.rsplit(".", 1)[-1]
        for match in LEFTOVER_CAPITAL.finditer(value):
            context = value[max(0, match.start() - 4) : match.end() + 3]
            if "ey Hermes" in context:
                result.leftovers["wake word"] += 1
            elif value[match.end() :].startswith(" 3"):
                result.leftovers["Hermes 3/4 models"] += 1
            elif leaf in PORTAL_PAGE_KEYS or key in PORTAL_PAGE_KEYS:
                result.leftovers["portal page"] += 1
            else:
                result.leftovers[f"unexpected: {key}: {value[max(0, match.start() - 20) : match.end() + 20]!r}"] += 1
        for match in LEFTOVER_LOWER.finditer(value):
            if value[max(0, match.start() - 4) : match.start()].lower() != "hey ":
                result.leftovers[f"lowercase: {key}: {value[max(0, match.start() - 20) : match.end() + 20]!r}"] += 1


def process(path: Path) -> FileResult:
    original = path.read_text(encoding="utf-8")
    lang = path.name.split(".", 1)[0]
    rebranded, count = rebrand_document(original, lang, path)
    result = FileResult(path, original, rebranded, count)
    validate(result)
    classify_leftovers(result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="report pending changes without writing")
    args = parser.parse_args()

    results = [process(path) for path in sorted(LOCALES_DIR.glob("*.yaml"))]
    leftovers: Counter[str] = Counter()
    failed = False
    for result in results:
        leftovers.update(result.leftovers)
        status = "pending" if result.changed else "clean"
        print(f"{result.path.name}: {result.replacements} replacements ({status})")
        for problem in result.problems:
            failed = True
            print(f"  ERROR {problem}")
    print("Remaining Hermes mentions:")
    for label, count in sorted(leftovers.items()):
        print(f"  {count:4d}  {label}")
    if failed:
        return 2
    pending = [result for result in results if result.changed]
    if args.check:
        return 1 if pending else 0
    for result in pending:
        result.path.write_text(result.rebranded, encoding="utf-8")
    print(f"Wrote {len(pending)} file(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
