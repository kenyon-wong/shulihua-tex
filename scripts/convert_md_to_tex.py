#!/usr/bin/env python3
"""Convert canonical Markdown books into maintainable TeX sources under tex/books/."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_pdfs import (  # noqa: E402
    BuildError,
    load_catalog,
    pandoc_markdown_to_tex,
    prepare_source,
    select_books,
    tex_source_path,
)

TEX_BOOKS = ROOT / "tex" / "books"
MANIFEST = ROOT / "tex" / "manifest.json"


def convert_one(book: dict, work_root: Path) -> dict[str, object]:
    source = ROOT / book["file"]
    if not source.is_file():
        raise BuildError(f"Markdown 源不存在：{source}")
    work = work_root / book["title"]
    work.mkdir(parents=True, exist_ok=True)
    clean = work / "source.md"
    comments, math_spans, source_sha = prepare_source(source, clean, book["title"])
    tex_path = tex_source_path(book)
    tex_path.parent.mkdir(parents=True, exist_ok=True)
    proc = pandoc_markdown_to_tex(clean, tex_path, book)
    if proc.returncode != 0:
        raise BuildError(f"{book['title']}: Pandoc 失败：\n{proc.stderr}")
    text = tex_path.read_text(encoding="utf-8")
    if r"\begin{document}" not in text or r"\end{document}" not in text:
        raise BuildError(f"{book['title']}: 生成的 TeX 缺少 document 环境")
    return {
        "title": book["title"],
        "markdown": book["file"],
        "tex": tex_path.relative_to(ROOT).as_posix(),
        "bytes": tex_path.stat().st_size,
        "source_sha256": source_sha,
        "comments_stripped": comments,
        "math_spans": math_spans,
        "pandoc_warnings": [line for line in proc.stderr.splitlines() if line.strip()],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book", action="append", default=[], help="按题名转换；可重复。默认全部 17 册")
    args = parser.parse_args()
    catalog = load_catalog()
    books = select_books(catalog["books"], args.book)
    work_root = ROOT / ".build" / "md-to-tex"
    work_root.mkdir(parents=True, exist_ok=True)
    rows = []
    errors = []
    for book in books:
        try:
            row = convert_one(book, work_root)
            rows.append(row)
            print(f"{book['title']}: OK {row['tex']}")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{book['title']}: {exc}")
            print(f"{book['title']}: FAIL {exc}", file=sys.stderr)
    payload = {
        "schema_version": 1,
        "status": "PASS" if not errors else "FAIL",
        "converted": len(rows),
        "failed": len(errors),
        "books": rows,
        "errors": errors,
    }
    MANIFEST.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"converted": len(rows), "failed": len(errors), "status": payload["status"]}, ensure_ascii=False))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
