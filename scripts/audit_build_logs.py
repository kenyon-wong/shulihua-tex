#!/usr/bin/env python3
"""审计 .build/pdf 下的 XeLaTeX 构建日志：排版溢出、缺字、未定义引用。

分级（可用参数覆盖）：
  - Overfull < 2pt            忽略（只计数）
  - 2pt ≤ Overfull < 10pt     警告
  - Overfull ≥ 10pt           错误
  - Missing character / nullfont / 未定义引用 / 重复标签   错误

日志陈旧（早于对应 TeX 源）时降级为警告并提示重新构建。
报告写入 reports/build-log-audit.json；有错误时退出码 1。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD_ROOT = ROOT / ".build" / "pdf"
REPORT = ROOT / "reports" / "build-log-audit.json"
BOOKS_ROOT = ROOT / "tex" / "books"
STYLE_ROOT = ROOT / "tex" / "style"

DEFAULT_WARN_PT = 2.0
DEFAULT_ERROR_PT = 10.0

OVERFULL_RE = re.compile(
    r"Overfull \\([hv])box \(([\d.]+)pt too (wide|high)\)"
)
LOCATOR_RE = re.compile(
    r"(?:at lines (\d+)--(\d+)|detected at line (\d+))"
)
MISSING_CHAR_RE = re.compile(
    r"Missing character: There is no (.) \(\"?([0-9A-F]+)\"?\) in font ([^\s!]+)!"
)
UNDEF_REF_RE = re.compile(r"Reference `([^']+)' on page \d+ undefined")
UNDEF_SUMMARY_RE = re.compile(r"LaTeX Warning: There were undefined references")
MULTIDEF_RE = re.compile(r"Label `([^']+)' multiply defined")
SAME_DEST_RE = re.compile(r"destination with the same identifier \((?:name\{)?([^\)}]+)\)?")
RERUN_RE = re.compile(r"Label\(s\) may have changed\. Rerun")
INPUTBOOK_RE = re.compile(r"\\shulihuainputbook\{([^}]+)\}")
COLLECTIONS_ROOT = ROOT / "tex" / "collections"


def classify_log(name: str) -> str:
    if name == "covers":
        return "cover"
    if (BOOKS_ROOT / f"{name}.tex").is_file():
        return "volume"
    return "collection"


def newest_mtime(paths: list[Path]) -> float | None:
    times = [p.stat().st_mtime for p in paths if p.is_file()]
    return max(times) if times else None


def staleness_refs(name: str, kind: str) -> list[Path]:
    if kind == "volume":
        paths = [BOOKS_ROOT / f"{name}.tex"]
    elif kind == "collection":
        col = COLLECTIONS_ROOT / f"{name}.tex"
        paths = [col]
        if col.is_file():
            text = col.read_text(encoding="utf-8")
            for book in INPUTBOOK_RE.findall(text):
                paths.append(BOOKS_ROOT / f"{book}.tex")
    else:
        paths = []
    paths.extend(STYLE_ROOT.glob("*.tex"))
    paths.extend(STYLE_ROOT.glob("*.sty"))
    return paths


def parse_log(path: Path, kind: str, warn_pt: float, error_pt: float) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    errors: list[str] = []
    warnings: list[str] = []
    over_counts = {"ignored": 0, "warn": 0, "error": 0}

    for match in OVERFULL_RE.finditer(text):
        pt = float(match.group(2))
        # TeX 日志按 79 字符换行，定位短语可能落在下一行。
        window = text[match.end() : match.end() + 160]
        loc = LOCATOR_RE.search(window)
        where = f"line {loc.group(3)}" if loc and loc.group(3) else (
            f"lines {loc.group(1)}--{loc.group(2)}" if loc else "（无行号）"
        )
        entry = f"Overfull \\{match.group(1)}box {pt:.2f}pt @ {where}"
        if kind == "collection":
            entry += "（合订本日志，行号相对分册源）"
        if pt >= error_pt:
            over_counts["error"] += 1
            errors.append(entry)
        elif pt >= warn_pt:
            over_counts["warn"] += 1
            warnings.append(entry)
        else:
            over_counts["ignored"] += 1

    for match in MISSING_CHAR_RE.finditer(text):
        ch, code, font = match.group(1), match.group(2), match.group(3)
        label = "nullfont" if font == "nullfont" else font
        errors.append(f"Missing character U+{code} “{ch}” in font {label}")

    refs = sorted({m.group(1) for m in UNDEF_REF_RE.finditer(text)})
    if refs:
        errors.append(f"未定义引用 {len(refs)} 处：" + "、".join(refs[:8]))
    elif UNDEF_SUMMARY_RE.search(text):
        errors.append("存在未定义引用（详见日志）")

    for match in MULTIDEF_RE.finditer(text):
        errors.append(f"重复标签 `{match.group(1)}'")
    for match in SAME_DEST_RE.finditer(text):
        errors.append(f"hyperref 重复锚点 {match.group(1)}")
        break
    if RERUN_RE.search(text):
        warnings.append("Label(s) may have changed——需要重跑一次 XeLaTeX")

    return {
        "overfull": over_counts,
        "errors": errors,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--warn-pt", type=float, default=DEFAULT_WARN_PT)
    parser.add_argument("--error-pt", type=float, default=DEFAULT_ERROR_PT)
    args = parser.parse_args()

    if not BUILD_ROOT.is_dir():
        print("ERROR: 未找到 .build/pdf，请先 make pdf", file=sys.stderr)
        return 1

    logs = sorted(
        p for p in BUILD_ROOT.glob("*/*.log")
        if classify_log(p.parent.name) != "cover"
    )
    if not logs:
        print("ERROR: .build/pdf 下没有日志，请先 make pdf", file=sys.stderr)
        return 1

    rows = []
    total_errors = 0
    total_warnings = 0
    for path in logs:
        name = path.parent.name
        kind = classify_log(name)
        result = parse_log(path, kind, args.warn_pt, args.error_pt)
        newest = newest_mtime(staleness_refs(name, kind))
        stale = newest is not None and path.stat().st_mtime < newest
        stale_note = "日志早于 TeX 源，请重新构建" if stale else ""
        row_errors = list(result["errors"])
        row_warnings = list(result["warnings"])
        if stale:
            row_warnings.append(stale_note)
        total_errors += len(row_errors)
        total_warnings += len(row_warnings)
        rows.append({
            "log": name,
            "kind": kind,
            "stale": stale,
            "overfull": result["overfull"],
            "errors": row_errors,
            "warnings": row_warnings,
        })

    payload = {
        "schema_version": 1,
        "status": "PASS" if not total_errors else "FAIL",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "thresholds": {"warn_pt": args.warn_pt, "error_pt": args.error_pt},
        "summary": {"logs": len(rows), "errors": total_errors, "warnings": total_warnings},
        "logs": rows,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    for row in rows:
        over = row["overfull"]
        flag = "FAIL" if row["errors"] else ("WARN" if row["warnings"] else "PASS")
        print(
            f"{flag}  {row['log']}  overfull err/warn/ign="
            f"{over['error']}/{over['warn']}/{over['ignored']}"
            f"  errors={len(row['errors'])} warnings={len(row['warnings'])}"
        )
    print(json.dumps(payload["summary"], ensure_ascii=False))
    if total_errors:
        for row in rows:
            for err in row["errors"]:
                print(f"ERROR: {row['log']}: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
