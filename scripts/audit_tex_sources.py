#!/usr/bin/env python3
"""Audit the 17 canonical TeX sources on the tex-maintenance branch."""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "catalog.json"
TEX_ROOT = ROOT / "tex" / "books"
REPORT = ROOT / "reports" / "tex-source-audit.json"

CJK_BACKSLASH = re.compile(r"[\u4e00-\u9fff]\\[\u4e00-\u9fff]")
ENV_TOKEN = re.compile(r"\\(begin|end)\{([A-Za-z*]+)\}")


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
        if not text.strip():
            errors.append(f"{path.name}: 正文为空")
        for i, line in enumerate(text.splitlines(), 1):
            if CJK_BACKSLASH.search(line):
                errors.append(f"{path.name}:{i}: 汉字后的 \\ 会被当成控制序列")
                break
        errors.extend(env_balance_errors(path, text))
        rows.append({"title": item["title"], "bytes": path.stat().st_size})
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
