#!/usr/bin/env python3
"""Audit the 17 Markdown comparison sources and their referenced assets."""
from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOOK_ROOT = ROOT / "books"
CATALOG = ROOT / "catalog.json"
REPORT = ROOT / "reports" / "source-audit.json"
BOOK_GLOB = "* - 数理化自学丛书编委会.md"
IMAGE_RE = re.compile(
    r"!\[(?P<alt>[^\]\n]*)\]\((?P<path>assets/[^)\s]+)(?:\s+[\"'][^\"']*[\"'])?\)"
)
H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.M)
HEADING_RE = re.compile(r"^(#{1,6})\s+\S", re.M)
KNOWN_MISSING_RE = re.compile(
    r"\[OCR 原始产物第 (49|50|55|56) 页仅含整页图像标签，raw 中未提供可恢复的文字内容。\]"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    books = catalog.get("books", [])
    if len(books) != 17:
        errors.append(f"catalog.json 应有 17 册，实际 {len(books)}")

    listed_files = [item.get("file", "") for item in books]
    listed_ids = [item.get("identifier", "") for item in books]
    if len(set(listed_files)) != len(listed_files):
        errors.append("catalog.json 存在重复文件名")
    if len(set(listed_ids)) != len(listed_ids):
        errors.append("catalog.json 存在重复 identifier")

    actual_books = sorted(path.relative_to(ROOT).as_posix() for path in BOOK_ROOT.glob(BOOK_GLOB))
    if set(actual_books) != set(listed_files):
        errors.append(
            "对照 Markdown 与 catalog.json 不一致："
            f"未登记={sorted(set(actual_books) - set(listed_files))}，"
            f"缺文件={sorted(set(listed_files) - set(actual_books))}"
        )

    references: list[tuple[str, str]] = []
    markdown_rows: list[dict[str, object]] = []
    known_missing_pages: list[dict[str, object]] = []
    for item in books:
        filename = item.get("file", "")
        path = ROOT / filename
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            errors.append(f"{filename}: 不是合法 UTF-8：{exc}")
            continue

        h1s = H1_RE.findall(text)
        if h1s != [item.get("title")]:
            errors.append(f"{filename}: H1 应唯一且为 {item.get('title')!r}，实际 {h1s!r}")

        levels = [len(match.group(1)) for match in HEADING_RE.finditer(text)]
        for previous, current in zip(levels, levels[1:]):
            if current > previous + 1:
                errors.append(f"{filename}: 标题层级从 H{previous} 跳到 H{current}")
                break

        if text.count("<!--") != text.count("-->"):
            errors.append(f"{filename}: HTML 注释未配对")

        image_matches = list(IMAGE_RE.finditer(text))
        raw_image_starts = text.count("![")
        if len(image_matches) != raw_image_starts:
            errors.append(
                f"{filename}: Markdown 图片语法疑似损坏，"
                f"图片起始符 {raw_image_starts}，可解析引用 {len(image_matches)}"
            )
        empty_alt = [match.group("path") for match in image_matches if not match.group("alt").strip()]
        if empty_alt:
            errors.append(f"{filename}: 存在 {len(empty_alt)} 个空图片替代文本")

        for match in image_matches:
            ref = match.group("path")
            references.append((filename, ref))
            if not (path.parent / ref).is_file():
                errors.append(f"{filename}: 缺少图片 {ref}")

        for match in KNOWN_MISSING_RE.finditer(text):
            known_missing_pages.append({"book": filename, "page": int(match.group(1))})

        markdown_rows.append(
            {
                "file": filename,
                "title": item.get("title"),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
                "headings": len(levels),
                "image_references": len(image_matches),
                "html_comments": text.count("<!--"),
            }
        )

    asset_root = BOOK_ROOT / "assets"
    asset_files = sorted(path for path in asset_root.rglob("*") if path.is_file())
    referenced_assets = {ref for _, ref in references}
    actual_assets = {path.relative_to(BOOK_ROOT).as_posix() for path in asset_files}
    orphaned = sorted(actual_assets - referenced_assets)
    if orphaned:
        errors.append(f"存在 {len(orphaned)} 个未引用资源，示例：{orphaned[:10]}")

    expected_missing: list[int] = []
    actual_missing = sorted(row["page"] for row in known_missing_pages)
    if actual_missing != expected_missing:
        warnings.append(f"《立体几何》待恢复缺页标记变化：{actual_missing}")

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "status": "PASS" if not errors else "FAIL",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "books": len(markdown_rows),
            "asset_files": len(asset_files),
            "image_references": len(references),
            "unique_referenced_assets": len(referenced_assets),
            "missing_assets": sum(
                1
                for filename, ref in references
                if not ((ROOT / filename).parent / ref).is_file()
            ),
            "orphaned_assets": len(orphaned),
            "unrecovered_source_page_markers": len(known_missing_pages),
            "errors": len(errors),
            "warnings": len(warnings),
        },
        "unrecovered_source_page_markers": known_missing_pages,
        "markdown": markdown_rows,
        "errors": errors,
        "warnings": warnings,
    }
    REPORT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload["summary"], ensure_ascii=False))
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
