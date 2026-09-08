#!/usr/bin/env python3
"""Audit the 17 canonical TeX sources on the tex-maintenance branch."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "catalog.json"
TEX_ROOT = ROOT / "tex" / "books"
REPORT = ROOT / "reports" / "tex-source-audit.json"


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
        if r"\begin{document}" not in text or r"\end{document}" not in text:
            errors.append(f"{path.name}: 缺少 document 环境")
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
