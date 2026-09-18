#!/usr/bin/env python3
"""对照 TeX 正文与上游 Markdown：章节目次、图号连续性与图号连接符体例。

本脚本只产生 WARN 信号（advisory，默认不改变退出码）：Markdown 是上游 OCR
产物，本身有错漏，内容裁判以 raw/ 扫描为准。

检查项：
  1. 章节目次：tex \\chapter/\\section/\\subsection 标题序列 vs books/*.md
     的 ##/###/#### 序列（忽略 md 独有的前置节）。
  2. 图号重号/跳号：按册提取 \\caption{图X·Y（Z）}，按章检查编号重复与跳号。
     每条结论用 md 的三类证据定性（图注行、图 alt、正文引用）：
       - 原书跳号 / 原书重号：md 同样缺失或同样重号，属原书面貌，不计入 findings；
       - tex 缺图注 / tex 多出图注 / tex 丢子号：md 证据与 tex 相悖，待修复；
       - 待对 raw：md 证据不足，需对照 raw/ 印刷页裁决。
     md 图注行的体例随册而异（*图N·M* / > 图N·M / ![图N·M](…)），三类都采集。
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
TEX_HEAD_RE = re.compile(r"\\(chapter|section|subsection)\*?(?:\[([^\]]*)\])?\s*\{")
CAPTION_FIG_RE = re.compile(
    r"\\caption\{图\s*(\d+)\s*([·.\-])\s*(\d+)\s*(?:[（(]([^）)]{1,12})[）)])?"
)
REF_FIG_RE = re.compile(r"图\s*(\d+)\s*([·.\-])\s*(\d+)")
MD_FIG_RE = re.compile(r"图\s*(\d+)\s*([·.\-])\s*(\d+)")
# md 图注行：*图N·M…* / **图N·M…** / > 图N·M…；图 alt 单独识别。
MD_CAP_LINE_RE = re.compile(r"^(?:\*{1,2}|> ?)图")
MD_IMG_RE = re.compile(r"^!\[([^\]]*)\]")
MD_SUB_RE = re.compile(r"[（(]([^）)]{1,12})[）)]")
MD_ONLY_FRONT_MATTER = {"目录"}
LEVELS = (
    ("chapter", "##", "chapter"),
    ("section", "###", "section"),
    ("subsection", "####", "subsection"),
)

FULLWIDTH_DIGITS = str.maketrans("０１２３４５６７８９．", "0123456789.")

VERDICT_ORIGINAL = ("原书重号", "原书跳号")


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
    title = title.replace("~", "～")
    title = re.sub(r"\s+", "", title)
    return title


def tex_headings(path: Path) -> dict[str, list[str]]:
    text = strip_comments(path.read_text(encoding="utf-8"))
    levels: dict[str, list[str]] = {name: [] for name, _h, _t in LEVELS}
    for match in TEX_HEAD_RE.finditer(text):
        if match.group(2) is not None:
            title = match.group(2)
        else:
            close = closing_brace(text, match.end())
            if close < match.end():
                continue
            title = text[match.end() : close]
        levels[match.group(1)].append(normalize_title(title))
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


def md_fig_signals(path: Path):
    """按行采集 md 图证据：图注行、图 alt、正文引用，连接符归一为 (章,号)。"""
    caps: Counter = Counter()
    imgs: Counter = Counter()
    refs: Counter = Counter()
    subs: dict[tuple[int, int], set[str]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.translate(FULLWIDTH_DIGITS).strip()
        if not line:
            continue
        img = MD_IMG_RE.match(line)
        if img:
            for m in MD_FIG_RE.finditer(img.group(1)):
                imgs[(int(m.group(1)), int(m.group(3)))] += 1
            continue
        if MD_CAP_LINE_RE.match(line):
            for m in MD_FIG_RE.finditer(line):
                key = (int(m.group(1)), int(m.group(3)))
                caps[key] += 1
                sm = MD_SUB_RE.search(line[m.end() : m.end() + 14])
                if sm:
                    subs.setdefault(key, set()).add(sm.group(1))
            continue
        for m in MD_FIG_RE.finditer(line):
            refs[(int(m.group(1)), int(m.group(3)))] += 1
    return caps, imgs, refs, subs


def figure_audit(path: Path, title: str, md_path: Path) -> dict:
    text = strip_comments(path.read_text(encoding="utf-8"))
    captions = list(CAPTION_FIG_RE.finditer(text))

    caption_connectors = Counter(m.group(2) for m in captions)
    dominant, _count = (
        caption_connectors.most_common(1)[0] if caption_connectors else ("·", 0)
    )

    md_caps, md_imgs, md_refs, md_subs = md_fig_signals(md_path)

    per_chapter: dict[int, set[int]] = {}
    dup_counts: Counter = Counter()
    for m in captions:
        chap, fig = int(m.group(1)), int(m.group(3))
        sub = (m.group(4) or "").strip()
        per_chapter.setdefault(chap, set()).add(fig)
        dup_counts[(chap, fig, sub)] += 1

    duplicates: list[dict] = []
    for (chap, fig, sub), n in sorted(dup_counts.items()):
        if n < 2:
            continue
        mc, mi = md_caps[(chap, fig)], md_imgs[(chap, fig)]
        label = f"图{chap}{dominant}{fig}" + (f"（{sub}）" if sub else "")
        if sub:
            verdict = "原书重号" if mc >= n else "待对 raw"
        elif len(md_subs.get((chap, fig), ())) >= n:
            # md 图注带子号而 tex 是重号裸图注：转换丢了（1）（2）。
            verdict = "tex 丢子号"
        elif mc >= n:
            verdict = "原书重号"
        elif mc >= 1 or 0 < mi < n:
            verdict = "tex 多出图注"
        else:
            verdict = "待对 raw"
        duplicates.append({
            "fig": label,
            "tex_count": n,
            "md_captions": mc,
            "md_images": mi,
            "md_refs": md_refs[(chap, fig)],
            "verdict": verdict,
        })

    gaps: list[dict] = []
    for chap, figs in per_chapter.items():
        lo, hi = min(figs), max(figs)
        for g in sorted(set(range(lo, hi + 1)) - figs):
            mc, mi = md_caps[(chap, g)], md_imgs[(chap, g)]
            gaps.append({
                "fig": f"图{chap}{dominant}{g}",
                "range": f"{lo}–{hi}",
                "md_captions": mc,
                "md_images": mi,
                "md_refs": md_refs[(chap, g)],
                "verdict": "tex 缺图注" if (mc or mi) else "原书跳号",
            })
    gaps.sort(key=lambda r: (int(REF_NUM_RE.match(r["fig"]).group(1)),
                             int(REF_NUM_RE.match(r["fig"]).group(2))))

    ref_connectors = Counter(m.group(2) for m in REF_FIG_RE.finditer(text))
    ref_anomalies: list[str] = []
    for m in REF_FIG_RE.finditer(text):
        if m.group(2) != dominant:
            line = text.count("\n", 0, m.start()) + 1
            ref_anomalies.append(f"{path.name}:{line}: “{m.group(0)}” 连接符应为 {dominant!r}")

    return {
        "captions": len(captions),
        "caption_connectors": dict(caption_connectors),
        "duplicates": duplicates,
        "gaps": gaps,
        "ref_connector_anomalies": ref_anomalies,
        "ref_connectors": dict(ref_connectors),
    }


REF_NUM_RE = re.compile(r"图(\d+).(\d+)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true", help="有任何 WARN 时退出码 1")
    args = parser.parse_args()

    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    books = catalog.get("books", [])
    rows = []
    total_findings = 0
    verdict_tallies: Counter = Counter()
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
        figs = figure_audit(tex_path, title, md_path)
        heading_count = sum(len(ops) for ops in level_ops.values())
        fig_defects = sum(
            1 for r in figs["duplicates"] + figs["gaps"]
            if r["verdict"] not in VERDICT_ORIGINAL
        )
        for r in figs["duplicates"] + figs["gaps"]:
            verdict_tallies[r["verdict"]] += 1
        findings = (
            heading_count
            + fig_defects
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
        "schema_version": 2,
        "status": "OK" if not total_findings else "WARN",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "books": len(rows),
            "findings": total_findings,
            "verdict_tallies": dict(verdict_tallies),
        },
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
            figs = row["figures"]
            for label, items in (("图号重复", figs["duplicates"]), ("图号跳号", figs["gaps"])):
                defects = [r for r in items if r["verdict"] not in VERDICT_ORIGINAL]
                originals = len(items) - len(defects)
                if originals:
                    print(f"  {label}：{originals} 处原书面貌（md 一致，已不计入 findings）", file=sys.stderr)
                for r in defects[:8]:
                    ev = f"md图注={r['md_captions']} 图={r['md_images']} 引用={r['md_refs']}"
                    print(f"  {label}[{r['verdict']}]：{r['fig']}（{ev}）", file=sys.stderr)
                if len(defects) > 8:
                    print(f"  … 其余 {len(defects) - 8} 条见报告", file=sys.stderr)
            for a in figs["ref_connector_anomalies"][:10]:
                print(f"  {a}", file=sys.stderr)
            if len(figs["ref_connector_anomalies"]) > 10:
                print(f"  … 其余 {len(figs['ref_connector_anomalies']) - 10} 处连接符异常见报告", file=sys.stderr)
        else:
            print(f"OK    {row['title']}")
    print(json.dumps(payload["summary"], ensure_ascii=False))
    if args.strict and total_findings:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
