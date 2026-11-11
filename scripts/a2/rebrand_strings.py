import re
import sys

BRAND = "A2Assistant"
WORD = re.compile(r"\bHermes Agent\b|\bHermes\b(?!\.app|-Setup)")


def rebrand_literal(text):
    return WORD.sub(BRAND, text)


def rebrand_source(src):
    out = []
    i = 0
    n = len(src)
    while i < n:
        c = src[i]
        if src.startswith("//", i):
            j = src.find("\n", i)
            j = n if j == -1 else j
            out.append(src[i:j])
            i = j
        elif src.startswith("/*", i):
            j = src.find("*/", i + 2)
            j = n if j == -1 else j + 2
            out.append(src[i:j])
            i = j
        elif c in "'\"`":
            j = i + 1
            depth = 0
            while j < n:
                if src[j] == "\\":
                    j += 2
                    continue
                if c == "`" and src.startswith("${", j):
                    depth += 1
                    j += 2
                    continue
                if c == "`" and depth and src[j] == "}":
                    depth -= 1
                    j += 1
                    continue
                if src[j] == c and not depth:
                    break
                j += 1
            out.append(rebrand_literal(src[i:j + 1]))
            i = j + 1
        else:
            out.append(c)
            i += 1
    return "".join(out)


for path in sys.argv[1:]:
    with open(path, encoding="utf-8") as f:
        original = f.read()
    updated = rebrand_source(original)
    if updated != original:
        with open(path, "w", encoding="utf-8") as f:
            f.write(updated)
        print(f"{path}: {len(WORD.findall(original)) - len(WORD.findall(updated))}")
