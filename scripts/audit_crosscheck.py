#!/usr/bin/env python3
"""对照 TeX 正文与上游 Markdown：章节目次、图号连续性与图号连接符体例。

本脚本只产生 WARN 信号（advisory，默认不改变退出码）：Markdown 是上游 OCR
产物，本身有错漏，内容裁判以 raw/ 扫描为准。跳号、重号、标题不一致都需
对照 raw/ 印刷页后再决定是否修改。

检查项：
  1. 章节目次：tex \\chapter/\\section/\\subsection 标题序列 vs books/*.md
     的 ##/###/#### 序列（忽略 md 独有的前置节）。
  2. 图号重号/跳号：按册提取 \\caption{图X·Y}，按章检查编号重复与跳号。
  3. 图号连接符：每册 caption 连接符应统一（一册一种）；正文引用的连接符
     与该册体例不一致时给出行号。

报告写入 reports/crosscheck-audit.json。
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "catalog.json"
TEX_ROOT = ROOT / "tex" / "books"
MD_ROOT = ROOT / "books"
REPORT = ROOT / "reports" / "crosscheck-audit.json"

MD_HEADING_RE = re.compile(r"^(#{2,4})\s+(.+?)\s*$")
TEX_HEAD_RE = re.compile(r"\\(chapter|section|subsection)\*?\{")
CAPTION_FIG_RE = re.compile(r"\\caption\{图\s*(\d+)\s*([·.\-])\s*(\d+)")
REF_FIG_RE = re.compile(r"图\s*(\d+)\s*([·.\-])\s*(\d+)")
MD_ONLY_FRONT_MATTER = {"目录"}
LEVELS = (
    ("chapter", "##", "chapter"),
    ("section", "###", "section"),
    ("subsection", "####", "subsection"),
)

FULLWIDTH_DIGITS = str.maketrans("０１２３４５６７８９．", "0123456789.")

# 已知例外：恢复区/原书即如此的编号缺口，避免每次都报。
# 书名 -> {(章号, 起始图号, 结束图号)}，闭区间。
KNOWN_FIG_GAPS: dict[str, set[tuple[int, int, int]]] = {
    # 《立体几何》原扫描缺页恢复区（见 docs/KNOWN_ISSUES.md），图号沿用原扫描上下文。
    "立体几何": set(),
}


def strip_comments(text: str) -> str:
    return "\n".join(re.sub(r"(?<!\\)%.*", "", line) for line in text.splitlines())


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


def normalize_title(raw: str) -> str:
    title = raw
    # 取 \texorpdfstring{A}{B} 的 A（标题里用于 PDF 书签降级）。
    m = re.match(r"^\\texorpdfstring\{(.*)\}\{.*\}$", title)
    if m:
        title = m.group(1)
    title = title.replace("\\*", "*")
    title = title.replace("\\$", "$")
    title = title.replace("\\&", "&").replace("\\%", "%")
    # md 脚注标记（如 §2·9酮[^ch2-15]）在 tex 标题里不存在。
    title = re.sub(r"\[\^[^\]]*\]", "", title)
    # LaTeX 引号 ``…'' 与中文引号等价；TeX 连字 --- 与中文破折号等价。
    title = title.replace("``", "“").replace("''", "”")
    title = re.sub(r"-{2,}", "——", title)
    title = title.translate(FULLWIDTH_DIGITS)
    title = title.replace("*", "")
    title = re.sub(r"\s+", "", title)
    return title


def tex_headings(path: Path) -> dict[str, list[str]]:
    text = strip_comments(path.read_text(encoding="utf-8"))
    levels: dict[str, list[str]] = {name: [] for name, _h, _t in LEVELS}
    for match in TEX_HEAD_RE.finditer(text):
        close = closing_brace(text, match.end())
        if close < match.end():
            continue
        levels[match.group(1)].append(normalize_title(text[match.end() : close]))
    return levels


def md_headings(path: Path) -> dict[str, list[str]]:
    levels: dict[str, list[str]] = {name: [] for name, _h, _t in LEVELS}
    marks = {hashes: name for name, hashes, _t in LEVELS}
    for line in path.read_text(encoding="utf-8").splitlines():
        m = MD_HEADING_RE.match(line)
        if not m:
            continue
        name = marks.get(m.group(1))
        if name is None:
            continue
        title = normalize_title(m.group(2))
        if title in MD_ONLY_FRONT_MATTER:
            continue
        levels[name].append(title)
    return levels


def align_level(md: list[str], tex: list[str]) -> list[dict]:
    ops: list[dict] = []
    matcher = difflib.SequenceMatcher(a=md, b=tex, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        ops.append({
            "tag": tag,
            "md_n": i2 - i1,
            "tex_n": j2 - j1,
            "md": md[i1:i2][:4],
            "tex": tex[j1:j2][:4],
        })
    return ops


def figure_audit(path: Path, title: str) -> dict:
    text = strip_comments(path.read_text(encoding="utf-8"))
    captions = list(CAPTION_FIG_RE.finditer(text))

    caption_connectors = Counter(m.group(2) for m in captions)
    duplicates: list[str] = []
    gaps: list[str] = []
    per_chapter: dict[int, list[int]] = {}
    order: list[tuple[int, int]] = []
    for m in captions:
        chap, fig = int(m.group(1)), int(m.group(3))
        order.append((chap, fig))
        per_chapter.setdefault(chap, []).append(fig)
    dominant, _count = (
        caption_connectors.most_common(1)[0] if caption_connectors else ("·", 0)
    )
    counts = Counter(order)
    duplicates = sorted(f"图{c}{dominant}{f}" for (c, f), n in counts.items() if n > 1)

    known = KNOWN_FIG_GAPS.get(title, set())
    for chap, figs in per_chapter.items():
        lo, hi = min(figs), max(figs)
        for g in sorted(set(range(lo, hi + 1)) - set(figs)):
            if any(chap == c and lo_g <= g <= hi_g for c, lo_g, hi_g in known):
                continue
            gaps.append(f"图{chap}{dominant}{g}（{lo}–{hi} 区间缺口）")

    ref_connectors = Counter(m.group(2) for m in REF_FIG_RE.finditer(text))
    ref_anomalies: list[str] = []
    for m in REF_FIG_RE.finditer(text):
        if m.group(2) != dominant:
            line = text.count("\n", 0, m.start()) + 1
            ref_anomalies.append(f"{path.name}:{line}: “{m.group(0)}” 连接符应为 {dominant!r}")

    return {
        "captions": len(captions),
        "caption_connectors": dict(caption_connectors),
        "duplicates": sorted(set(duplicates)),
        "gaps": gaps,
        "ref_connector_anomalies": ref_anomalies,
        "ref_connectors": dict(ref_connectors),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true", help="有任何 WARN 时退出码 1")
    args = parser.parse_args()

    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    books = catalog.get("books", [])
    rows = []
    total_findings = 0
    for item in books:
        title = item["title"]
        tex_path = TEX_ROOT / f"{title}.tex"
        md_path = MD_ROOT / f"{title} - 数理化自学丛书编委会.md"
        if not tex_path.is_file() or not md_path.is_file():
            rows.append({"title": title, "error": "缺少 tex 或 md 对照文件"})
            total_findings += 1
            continue
        md = md_headings(md_path)
        tex = tex_headings(tex_path)
        level_ops = {
            name: align_level(md[name], tex[name]) for name, _h, _t in LEVELS
        }
        figs = figure_audit(tex_path, title)
        heading_count = sum(len(ops) for ops in level_ops.values())
        findings = (
            heading_count
            + len(figs["duplicates"])
            + len(figs["gaps"])
            + len(figs["ref_connector_anomalies"])
        )
        total_findings += findings
        rows.append({
            "title": title,
            "headings": {
                "md": {name: len(md[name]) for name, _h, _t in LEVELS},
                "tex": {name: len(tex[name]) for name, _h, _t in LEVELS},
                "ops": level_ops,
                "structural": heading_count > 25,
            },
            "figures": figs,
            "findings": findings,
        })

    payload = {
        "schema_version": 1,
        "status": "OK" if not total_findings else "WARN",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {"books": len(rows), "findings": total_findings},
        "books": rows,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    for row in rows:
        if "error" in row:
            print(f"ERROR: {row['title']}: {row['error']}", file=sys.stderr)
            continue
        if row["findings"]:
            print(f"WARN  {row['title']}: {row['findings']} 处待核", file=sys.stderr)
            headings = row["headings"]
            if headings["structural"]:
                print("  标题体例与 md 存在系统性差异（>25 块），逐条对齐无意义，详见报告", file=sys.stderr)
            for name, _h, _t in LEVELS:
                for op in headings["ops"][name][:6]:
                    md_part = "、".join(op["md"][:3]) or "（无）"
                    tex_part = "、".join(op["tex"][:3]) or "（无）"
                    print(
                        f"  [{name}/{op['tag']}] md({op['md_n']})={md_part} | tex({op['tex_n']})={tex_part}",
                        file=sys.stderr,
                    )
            for d in row["figures"]["duplicates"]:
                print(f"  图号重复：{d}", file=sys.stderr)
            for g in row["figures"]["gaps"]:
                print(f"  图号跳号：{g}", file=sys.stderr)
            for a in row["figures"]["ref_connector_anomalies"][:10]:
                print(f"  {a}", file=sys.stderr)
            if len(row["figures"]["ref_connector_anomalies"]) > 10:
                print(f"  … 其余 {len(row['figures']['ref_connector_anomalies']) - 10} 处连接符异常见报告", file=sys.stderr)
        else:
            print(f"OK    {row['title']}")
    print(json.dumps(payload["summary"], ensure_ascii=False))
    if args.strict and total_findings:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
