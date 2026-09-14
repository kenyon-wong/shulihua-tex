#!/usr/bin/env python3
"""Audit the 17 canonical TeX sources, collections, and Makefile book list."""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "catalog.json"
TEX_ROOT = ROOT / "tex" / "books"
COLLECTIONS_ROOT = ROOT / "tex" / "collections"
MAKEFILE = ROOT / "Makefile"
REPORT = ROOT / "reports" / "tex-source-audit.json"

CJK_BACKSLASH = re.compile(r"[\u4e00-\u9fff]\\[\u4e00-\u9fff]")
ENV_TOKEN = re.compile(r"\\(begin|end)\{([A-Za-z*]+)\}")
INPUTBOOK_RE = re.compile(r"\\shulihuainputbook\{([^}]+)\}\{([^}]+)\}")


def strip_comments(text: str) -> str:
    lines = []
    for line in text.splitlines():
        lines.append(re.sub(r"(?<!\\)%.*", "", line))
    return "\n".join(lines)


def env_balance_errors(path: Path, text: str) -> list[str]:
    body = strip_comments(text)
    stack: list[tuple[str, int]] = []
    errors: list[str] = []
    for i, line in enumerate(body.splitlines(), 1):
        for kind, env in ENV_TOKEN.findall(line):
            if kind == "begin":
                stack.append((env, i))
                continue
            if not stack:
                errors.append(f"{path.name}:{i}: \\end{{{env}}} 没有对应的 \\begin")
                continue
            begin, at = stack.pop()
            if begin != env:
                errors.append(
                    f"{path.name}:{i}: \\end{{{env}}} 与 {at} 行的 \\begin{{{begin}}} 不配对"
                )
    for env, at in stack:
        errors.append(f"{path.name}:{at}: \\begin{{{env}}} 没有对应的 \\end")
    return errors


POST_FIG_EMPH = re.compile(r"\\end\{figure\}\s*\\emph\{图")
POST_FIG_QUOTE = re.compile(r"\\end\{figure\}\s*\\begin\{quote\}\s*图\s*[\d一二三四五六七八九十]")
HEAD_CMD = re.compile(r"\\(subsubsection|subsection|section|chapter|paragraph)\*?\{")
FONT_MACRO = re.compile(
    r"\\def\\(rm|tt|sc)\b|\\pgfmathsetmacro\{\\(rm|tt|sc)\}|\\foreach \\(rm|tt|sc)\b"
)


def closing_brace(text: str, start: int) -> int:
    depth = 1
    j = start
    n = len(text)
    while j < n and depth:
        ch = text[j]
        if ch == "\\" and j + 1 < n:
            j += 2
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        j += 1
    return j - 1


CARET_ESC = re.compile(r"\\\^\{\}\\\{")


def texorpdfstring_pdf_arg_ranges(text: str) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    needle = r"\texorpdfstring{"
    i = 0
    while True:
        j = text.find(needle, i)
        if j < 0:
            break
        first_open = j + len(r"\texorpdfstring")
        first_close = closing_brace(text, first_open + 1)
        k = first_close + 1
        while k < len(text) and text[k] in " \t\n":
            k += 1
        if k < len(text) and text[k] == "{":
            second_close = closing_brace(text, k + 1)
            ranges.append((k + 1, second_close))
            i = second_close + 1
        else:
            i = first_close + 1
    return ranges


def caret_escape_errors(path: Path, text: str) -> list[str]:
    skip = texorpdfstring_pdf_arg_ranges(text)
    errors: list[str] = []
    for match in CARET_ESC.finditer(text):
        pos = match.start()
        if any(start <= pos < end for start, end in skip):
            continue
        line = text.count("\n", 0, pos) + 1
        errors.append(
            f"{path.name}:{line}: 正文不得使用 \\^{{}}{{…}} 转义，应使用 ^{{…}}"
        )
        break
    return errors


def heading_newline_errors(path: Path, text: str) -> list[str]:
    errors: list[str] = []
    for match in HEAD_CMD.finditer(text):
        close = closing_brace(text, match.end())
        if close < match.end():
            continue
        if "\n" in text[match.end() : close]:
            line = text.count("\n", 0, match.start()) + 1
            errors.append(f"{path.name}:{line}: 标题命令参数不得含换行")
            break
    return errors


def scan_png_includes(path: Path, text: str) -> list[str]:
    errors: list[str] = []
    body = strip_comments(text)
    for i, line in enumerate(body.splitlines(), 1):
        if r"\includegraphics" not in line:
            continue
        if re.search(r"assets/|\.png\b", line, re.I):
            errors.append(f"{path.name}:{i}: 正文不得 \\includegraphics 扫描 PNG")
    return errors


def scan_figure_dup_labels(path: Path, text: str) -> list[str]:
    errors: list[str] = []
    body = strip_comments(text)
    if POST_FIG_EMPH.search(body):
        errors.append(f"{path.name}: \\end{{figure}} 后不得重复 \\emph{{图…}}")
    if POST_FIG_QUOTE.search(body):
        errors.append(f"{path.name}: \\end{{figure}} 后不得再用 quote 重复图号")
    return errors


def makefile_book_titles() -> list[str]:
    titles: list[str] = []
    in_books = False
    for line in MAKEFILE.read_text(encoding="utf-8").splitlines():
        if line.startswith("BOOKS :="):
            in_books = True
            continue
        if not in_books:
            continue
        stripped = line.strip()
        if not stripped or stripped.startswith("MATH_BOOKS"):
            break
        titles.append(stripped.rstrip("\\").strip())
    return titles


def collection_errors(catalog: dict[str, object]) -> list[str]:
    errors: list[str] = []
    collections = catalog.get("collections", [])
    if not isinstance(collections, list):
        return ["catalog.json collections 不是列表"]
    expected_files = {f"{item.get('title', '')}.tex" for item in collections if isinstance(item, dict)}
    actual_files = {path.name for path in COLLECTIONS_ROOT.glob("*.tex")}
    missing = sorted(expected_files - actual_files)
    extra = sorted(actual_files - expected_files)
    if missing:
        errors.append(f"缺少合订本：{missing}")
    if extra:
        errors.append(f"多余合订本：{extra}")
    for item in collections:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", ""))
        path = COLLECTIONS_ROOT / f"{title}.tex"
        if not path.is_file():
            continue
        found = [name for name, _prefix in INPUTBOOK_RE.findall(path.read_text(encoding="utf-8"))]
        expected = item.get("books", [])
        if found != expected:
            errors.append(f"{path.name}: 分册顺序与 catalog.json 不一致")
    return errors


def main() -> int:
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    books = catalog.get("books", [])
    errors: list[str] = []
    rows = []
    if len(books) != 17:
        errors.append(f"catalog.json 应有 17 册，实际 {len(books)}")
    expected = {item["title"] for item in books}
    actual = {path.stem for path in TEX_ROOT.glob("*.tex")}
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing:
        errors.append(f"缺少 TeX 源：{missing}")
    if extra:
        errors.append(f"多余 TeX 源：{extra}")
    for item in books:
        path = TEX_ROOT / f"{item['title']}.tex"
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        if r"\documentclass" in text or r"\begin{document}" in text:
            errors.append(f"{path.name}: 正文混入了版式（documentclass/document），样式应只在 tex/style/")
        if r"\tableofcontents" in text:
            errors.append(f"{path.name}: 正文不得含 \\tableofcontents，目录由 driver/合订本生成")
        if r"\chapter{目录}" in text:
            errors.append(f"{path.name}: 不得保留 OCR \\chapter{{目录}}")
        if r"\caption{图示（原PDF" in text or r"\caption{原PDF" in text:
            errors.append(f"{path.name}: 不得保留 OCR 占位 caption \\caption{{原PDF…}}")
        if "$$" in strip_comments(text):
            errors.append(f"{path.name}: 不得使用 $$（相邻行内数学会进入 display math）")
        if r"\textbackslash(" in text:
            errors.append(f"{path.name}: 表内数学不得写成 \\textbackslash(，应使用 \\(")
        errors.extend(caret_escape_errors(path, text))
        if FONT_MACRO.search(text):
            errors.append(f"{path.name}: 不得 \\def\\rm/\\tt/\\sc（与 LaTeX 字体命令冲突）")
        errors.extend(heading_newline_errors(path, text))
        if not text.strip():
            errors.append(f"{path.name}: 正文为空")
        for i, line in enumerate(text.splitlines(), 1):
            if CJK_BACKSLASH.search(line):
                errors.append(f"{path.name}:{i}: 汉字后的 \\ 会被当成控制序列")
                break
        errors.extend(env_balance_errors(path, text))
        errors.extend(scan_png_includes(path, text))
        errors.extend(scan_figure_dup_labels(path, text))
        rows.append({"title": item["title"], "bytes": path.stat().st_size})
    catalog_titles = [item["title"] for item in books]
    makefile_titles = makefile_book_titles()
    if makefile_titles != catalog_titles:
        errors.append("Makefile BOOKS 与 catalog.json 书目不一致")
    errors.extend(collection_errors(catalog))
    payload = {
        "schema_version": 1,
        "status": "PASS" if not errors else "FAIL",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {"books": len(rows), "errors": len(errors)},
        "books": rows,
        "errors": errors,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload["summary"], ensure_ascii=False))
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
