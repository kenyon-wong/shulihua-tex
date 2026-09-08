#!/usr/bin/env python3
"""First-pass figure inventory for scanned PNGs still cited from tex/books.

Tracks are not final. Confidence is deliberately conservative.
Writes docs/figures-inventory.tsv. Does not modify books/assets or tex/books.
"""
from __future__ import annotations

import re
import struct
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEX_DIR = ROOT / "tex" / "books"
ASSETS = ROOT / "books" / "assets"
OUT = ROOT / "docs" / "figures-inventory.tsv"

# Order is the stable book sort used by the inventory.
BOOK_BY_DIR: dict[str, str] = {
    "algebra-1": "代数（第一册）",
    "algebra-2": "代数（第二册）",
    "algebra-3": "代数（第三册）",
    "algebra-4": "代数（第四册）",
    "plane-trigonometry": "平面三角",
    "plane-geometry-1": "平面几何（第一册）",
    "plane-geometry-2": "平面几何（第二册）",
    "analytic-geometry": "平面解析几何",
    "solid-geometry": "立体几何",
    "chemistry-1": "化学（第一册）",
    "chemistry-2": "化学（第二册）",
    "chemistry-3": "化学（第三册）",
    "chemistry-4": "化学（第四册）",
    "physics-1": "物理（第一册）",
    "physics-2": "物理（第二册）",
    "physics-3": "物理（第三册）",
    "physics-4": "物理（第四册）",
}
BOOK_ORDER = {name: i for i, name in enumerate(BOOK_BY_DIR.values())}

COLUMNS = [
    "path",
    "book",
    "asset_dir",
    "page",
    "track",
    "confidence",
    "reason",
    "alt",
    "tex_refs",
    "width",
    "height",
    "bytes",
    "white",
    "black",
    "status",
]

PAGE_RE = re.compile(r"^(?:fig|table)-p(\d+)")
PNG_SIG = b"\x89PNG\r\n\x1a\n"

SKETCH_WORDS = (
    "皮球",
    "木球",
    "汽车",
    "吊车",
    "桥梁",
    "电线杆",
    "写生",
    "木刻",
    "素描",
    "速写",
)
GEOM_TERMS = (
    "三角形",
    "四边形",
    "平行四边",
    "正方形",
    "矩形",
    "菱形",
    "梯形",
    "直线",
    "切线",
    "割线",
    "圆弧",
    "圆周",
    "圆心",
    "半径",
    "直径",
    "坐标",
    "曲线",
    "函数",
    "方程",
    "抛物",
    "椭圆",
    "双曲",
    "棱柱",
    "棱锥",
    "圆柱",
    "圆锥",
    "多面体",
    "截面",
    "球体",
    "圆",
    "角",
)


def sanitize(value: object) -> str:
    text = "" if value is None else str(value)
    return text.replace("\t", " ").replace("\r", " ").replace("\n", " ")


def unescape_alt(text: str) -> str:
    if not text:
        return ""
    replacements = (
        (r"\textbackslash ", "\\"),
        (r"\textbackslash", "\\"),
        (r"\textgreater{}", ">"),
        (r"\textless{}", "<"),
        (r"\textgreater", ">"),
        (r"\textless", "<"),
        (r"\^{}", "^"),
        (r"\{", "{"),
        (r"\}", "}"),
        (r"\_", "_"),
        (r"\&", "&"),
        (r"\%", "%"),
        (r"\#", "#"),
        (r"\$", "$"),
        (r"\ ", " "),
    )
    for src, dst in replacements:
        text = text.replace(src, dst)
    text = text.replace("\t", " ").replace("\r", " ").replace("\n", " ")
    return " ".join(text.split())


def extract_alt(options: str) -> str:
    match = re.search(r"\balt\s*=\s*", options)
    if not match:
        return ""
    k = match.end()
    if k >= len(options):
        return ""
    if options[k] != "{":
        rest = re.match(r"[^,\]]*", options[k:])
        return unescape_alt(rest.group(0) if rest else "")
    k += 1
    start = k
    depth = 1
    while k < len(options) and depth:
        if options[k] == "{":
            depth += 1
        elif options[k] == "}":
            depth -= 1
            if depth == 0:
                break
        k += 1
    return unescape_alt(options[start:k])


def iter_includegraphics(text: str):
    key = r"\includegraphics"
    n = len(text)
    i = 0
    while True:
        j = text.find(key, i)
        if j < 0:
            return
        line = text.count("\n", 0, j) + 1
        k = j + len(key)
        if k < n and text[k] == "*":
            k += 1
        while k < n and text[k].isspace():
            k += 1
        options = ""
        if k < n and text[k] == "[":
            k += 1
            start = k
            depth = 0
            while k < n:
                ch = text[k]
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth = max(0, depth - 1)
                elif ch == "]" and depth == 0:
                    break
                k += 1
            options = text[start:k]
            if k < n and text[k] == "]":
                k += 1
        while k < n and text[k].isspace():
            k += 1
        path = ""
        if k < n and text[k] == "{":
            k += 1
            start = k
            depth = 1
            while k < n and depth:
                if text[k] == "{":
                    depth += 1
                elif text[k] == "}":
                    depth -= 1
                    if depth == 0:
                        break
                k += 1
            path = text[start:k].strip()
            i = k + 1
        else:
            i = k + 1
        yield line, options, path


def normalize_png_path(raw_path: str) -> str | None:
    path = raw_path.strip().replace("\\", "/")
    if path.startswith("./"):
        path = path[2:]
    if path.startswith("books/assets/") and path.lower().endswith(".png"):
        return path
    if path.startswith("assets/") and path.lower().endswith(".png"):
        return "books/" + path
    return None


def page_from_name(filename: str) -> str:
    match = PAGE_RE.match(filename)
    if not match:
        return ""
    return str(int(match.group(1)))


def is_object_sketch(alt: str) -> bool:
    if not alt:
        return False
    compact = re.sub(r"\s+", "", alt)
    cleaned = re.sub(r"^图[0-9]+(?:[.·\-−—][0-9]+)*", "", compact)
    cleaned = re.sub(r"^[\(（][A-Za-z0-9]+[\)）]", "", cleaned)
    cleaned = cleaned.strip("：:、，,。．.")
    if not cleaned:
        return False
    tmp = cleaned.replace("皮球", "").replace("木球", "")
    for term in GEOM_TERMS:
        if term in tmp:
            return False
    if cleaned in {"床", "木床", "铁床"}:
        return True
    if cleaned.endswith("床") and len(cleaned) <= 4 and "机床" not in cleaned:
        return True
    for word in SKETCH_WORDS:
        if word in cleaned and len(cleaned) <= max(10, len(word) + 3):
            return True
    return False


def paeth(left: int, up: int, up_left: int) -> int:
    estimate = left + up - up_left
    pa = abs(estimate - left)
    pb = abs(estimate - up)
    pc = abs(estimate - up_left)
    if pa <= pb and pa <= pc:
        return left
    if pb <= pc:
        return up
    return up_left


def _unfilter_rows(raw: bytes, height: int, row_bytes: int, bpp: int) -> list[bytes]:
    stride = row_bytes + 1
    if len(raw) < height * stride:
        raise ValueError(f"IDAT shorter than expected ({len(raw)} < {height * stride})")
    rows: list[bytes] = []
    prev = bytearray(row_bytes)
    offset = 0
    for _ in range(height):
        filter_type = raw[offset]
        scan = bytearray(raw[offset + 1 : offset + 1 + row_bytes])
        offset += stride
        if filter_type == 0:
            recon = scan
        elif filter_type == 1:
            for i in range(row_bytes):
                left = scan[i - bpp] if i >= bpp else 0
                scan[i] = (scan[i] + left) & 0xFF
            recon = scan
        elif filter_type == 2:
            for i in range(row_bytes):
                scan[i] = (scan[i] + prev[i]) & 0xFF
            recon = scan
        elif filter_type == 3:
            for i in range(row_bytes):
                left = scan[i - bpp] if i >= bpp else 0
                scan[i] = (scan[i] + ((left + prev[i]) // 2)) & 0xFF
            recon = scan
        elif filter_type == 4:
            for i in range(row_bytes):
                left = scan[i - bpp] if i >= bpp else 0
                up = prev[i]
                up_left = prev[i - bpp] if i >= bpp else 0
                scan[i] = (scan[i] + paeth(left, up, up_left)) & 0xFF
            recon = scan
        else:
            raise ValueError(f"unsupported PNG filter {filter_type}")
        prev = recon
        rows.append(bytes(recon))
    return rows


def _luma_at(row: bytes, x: int, bitdepth: int, color: int) -> int:
    if color == 0 and bitdepth == 1:
        byte = row[x // 8]
        bit = (byte >> (7 - (x % 8))) & 1
        return 255 if bit else 0
    if color == 0 and bitdepth == 8:
        return row[x]
    if color == 0 and bitdepth == 16:
        return row[x * 2]
    if color == 2 and bitdepth == 8:
        i = x * 3
        r, g, b = row[i], row[i + 1], row[i + 2]
        return (54 * r + 183 * g + 19 * b) >> 8
    if color == 2 and bitdepth == 16:
        i = x * 6
        r, g, b = row[i], row[i + 2], row[i + 4]
        return (54 * r + 183 * g + 19 * b) >> 8
    if color == 4 and bitdepth == 8:
        return row[x * 2]
    if color == 6 and bitdepth == 8:
        i = x * 4
        r, g, b = row[i], row[i + 1], row[i + 2]
        return (54 * r + 183 * g + 19 * b) >> 8
    raise ValueError(f"unsupported PNG color/bitdepth {color}/{bitdepth}")


def png_stats(path: Path) -> tuple[int, int, float, float, bool]:
    data = path.read_bytes()
    if not data.startswith(PNG_SIG):
        raise ValueError("not a PNG")
    pos = 8
    width = height = bitdepth = color = interlace = None
    idat: list[bytes] = []
    while pos + 12 <= len(data):
        length = struct.unpack(">I", data[pos : pos + 4])[0]
        typ = data[pos + 4 : pos + 8]
        chunk = data[pos + 8 : pos + 8 + length]
        pos += 12 + length
        if typ == b"IHDR":
            width, height, bitdepth, color, _comp, _filt, interlace = struct.unpack(
                ">IIBBBBB", chunk
            )
        elif typ == b"IDAT":
            idat.append(chunk)
        elif typ == b"IEND":
            break
    if width is None or bitdepth is None or color is None:
        raise ValueError("missing IHDR")
    if interlace:
        raise ValueError("interlaced PNG not supported")
    channels = {0: 1, 2: 3, 4: 2, 6: 4}.get(color)
    if channels is None:
        raise ValueError(f"unsupported color type {color}")
    bits_per_pixel = bitdepth * channels
    row_bytes = (width * bits_per_pixel + 7) // 8
    bpp = max(1, bits_per_pixel // 8)
    raw = zlib.decompress(b"".join(idat))
    rows = _unfilter_rows(raw, height, row_bytes, bpp)

    # Grid sample. Full decode is only used to pick sample rows cheaply.
    area = width * height
    step = 1
    if area > 400000:
        step = max(2, int((area / 120000) ** 0.5))

    whites = blacks = mids = samples = 0
    flips = pairs = 0
    # 16px blocks: stipple is a mixed, noisy cell, not a thin stroke on white.
    block = 16
    bw = (width + block - 1) // block
    bh = (height + block - 1) // block
    b_black = [0] * (bw * bh)
    b_n = [0] * (bw * bh)
    b_flip = [0] * (bw * bh)
    b_pairs = [0] * (bw * bh)

    for y in range(0, height, step):
        row = rows[y]
        by = min(bh - 1, y // block)
        last = None
        last_bx = None
        for x in range(0, width, step):
            value = _luma_at(row, x, bitdepth, color)
            samples += 1
            if value >= 235:
                whites += 1
            elif value <= 25:
                blacks += 1
            elif 40 <= value <= 220:
                mids += 1
            bx = min(bw - 1, x // block)
            idx = by * bw + bx
            b_n[idx] += 1
            if value <= 25:
                b_black[idx] += 1
            if last is not None and last_bx == bx:
                pairs += 1
                b_pairs[idx] += 1
                if abs(value - last) >= 40:
                    flips += 1
                    b_flip[idx] += 1
            last = value
            last_bx = bx

    if samples == 0:
        raise ValueError("empty image")
    white = whites / samples
    black = blacks / samples
    mid_frac = mids / samples
    flip_frac = (flips / pairs) if pairs else 0.0

    stipple = used = 0
    for i, count in enumerate(b_n):
        if count < 12:
            continue
        used += 1
        black_frac = b_black[i] / count
        cell_flip = (b_flip[i] / b_pairs[i]) if b_pairs[i] else 0.0
        if 0.22 <= black_frac <= 0.78 and cell_flip >= 0.28:
            stipple += 1
    stipple_frac = (stipple / used) if used else 0.0

    # Thin line drawings have edge flips but few mixed noisy blocks.
    # Gray-paper scans are mid-gray yet locally smooth, so they stay off P.
    if bitdepth == 1 and color == 0:
        halftone = stipple >= 6 and stipple_frac >= 0.10 and black >= 0.08
    else:
        halftone = mid_frac >= 0.20 and flip_frac >= 0.22
    return width, height, white, black, halftone



def classify(
    filename: str,
    alt: str,
    width: int | None,
    height: int | None,
    white: float | None,
    black: float | None,
    halftone: bool,
) -> tuple[str, str, str]:
    if filename.startswith("table-"):
        return "T", "high", "文件名是表"
    if "原始OCR" in alt or "原始 OCR" in alt:
        return "T", "high", "alt 标明文字块"
    if is_object_sketch(alt):
        return "R", "medium", "alt 是实物写生词"
    if white is not None and black is not None:
        if white >= 0.90 and black <= 0.08 and not halftone:
            return "T", "medium", "高留白线稿"
        if halftone:
            return "P", "medium", "疑似网纹或照片"
        area = (width or 0) * (height or 0)
        if area > 400000 and white < 0.90:
            return "V", "low", "较大线稿或零件图，待对照 raw"
        if white >= 0.85:
            return "T", "low", "初分待对照 raw 改轨"
        return "V", "low", "初分待对照 raw 改轨"
    return "V", "low", "初分待对照 raw 改轨"


def collect_tex_refs() -> tuple[dict[str, list[tuple[str, int, str]]], list[str]]:
    refs: dict[str, list[tuple[str, int, str]]] = {}
    warnings: list[str] = []
    for tex_path in sorted(TEX_DIR.glob("*.tex")):
        text = tex_path.read_text(encoding="utf-8")
        rel = tex_path.relative_to(ROOT).as_posix()
        for line, options, raw_path in iter_includegraphics(text):
            if not raw_path:
                warnings.append(f"{rel}:{line}: includegraphics 没有路径")
                continue
            normalized = normalize_png_path(raw_path)
            if normalized is None:
                warnings.append(f"{rel}:{line}: 非 assets PNG 引用 {raw_path}")
                continue
            alt = extract_alt(options)
            refs.setdefault(normalized, []).append((rel, line, alt))
    return refs, warnings


def join_alts(alts: list[str]) -> str:
    unique: list[str] = []
    for alt in alts:
        if alt and alt not in unique:
            unique.append(alt)
    return " | ".join(unique)


def join_refs(items: list[tuple[str, int, str]]) -> str:
    ordered = sorted(items, key=lambda item: (item[0], item[1]))
    return ";".join(f"{rel}:{line}" for rel, line, _alt in ordered)


def main() -> int:
    refs, warnings = collect_tex_refs()
    png_paths = sorted(p.relative_to(ROOT).as_posix() for p in ASSETS.rglob("*.png"))
    all_paths = sorted(set(png_paths) | set(refs))

    rows: list[dict[str, object]] = []
    decode_errors = 0
    for rel in all_paths:
        path = ROOT / rel
        filename = Path(rel).name
        asset_dir = Path(rel).parent.name
        book = BOOK_BY_DIR.get(asset_dir, "")
        if not book:
            warnings.append(f"{rel}: 未知 asset_dir {asset_dir}")
        items = refs.get(rel, [])
        alt = join_alts([item[2] for item in items])
        tex_refs = join_refs(items) if items else ""
        width = height = file_bytes = None
        white = black = None
        halftone = False
        if path.is_file():
            file_bytes = path.stat().st_size
            try:
                width, height, white, black, halftone = png_stats(path)
            except Exception as exc:  # noqa: BLE001 - inventory should still emit the row
                decode_errors += 1
                warnings.append(f"{rel}: PNG 统计失败 {exc}")
        else:
            warnings.append(f"{rel}: 引用了不存在的 PNG")
        track, confidence, reason = classify(
            filename, alt, width, height, white, black, halftone
        )
        page = page_from_name(filename)
        rows.append(
            {
                "path": rel,
                "book": book,
                "asset_dir": asset_dir,
                "page": page,
                "track": track,
                "confidence": confidence,
                "reason": reason,
                "alt": alt,
                "tex_refs": tex_refs,
                "width": "" if width is None else width,
                "height": "" if height is None else height,
                "bytes": "" if file_bytes is None else file_bytes,
                "white": "" if white is None else f"{white:.3f}",
                "black": "" if black is None else f"{black:.3f}",
                "status": "pending",
            }
        )

    def sort_key(row: dict[str, object]) -> tuple:
        book = str(row["book"])
        page_raw = str(row["page"])
        page_num = int(page_raw) if page_raw else 10**9
        return (BOOK_ORDER.get(book, 999), book, page_num, str(row["path"]))

    rows.sort(key=sort_key)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("\t".join(COLUMNS) + "\n")
        for row in rows:
            handle.write("\t".join(sanitize(row[col]) for col in COLUMNS) + "\n")

    referenced = sum(1 for row in rows if row["tex_refs"])
    tracks: dict[str, int] = {}
    confs: dict[str, int] = {}
    for row in rows:
        tracks[str(row["track"])] = tracks.get(str(row["track"]), 0) + 1
        confs[str(row["confidence"])] = confs.get(str(row["confidence"]), 0) + 1

    print(f"wrote {OUT.relative_to(ROOT)} rows={len(rows)}")
    print(f"referenced={referenced} unreferenced={len(rows) - referenced}")
    print("tracks " + " ".join(f"{k}={tracks.get(k, 0)}" for k in ("T", "V", "R", "P")))
    print("confidence " + " ".join(f"{k}={confs.get(k, 0)}" for k in ("high", "medium", "low")))
    print(f"decode_errors={decode_errors} warnings={len(warnings)}")
    for warn in warnings[:20]:
        print(f"WARN {warn}", file=sys.stderr)
    if len(warnings) > 20:
        print(f"WARN ... {len(warnings) - 20} more", file=sys.stderr)

    wanted = {
        "books/assets/plane-geometry-1/fig-p0011-01.png",
        "books/assets/plane-geometry-1/fig-p0166-02.png",
    }
    for row in rows:
        if row["path"] in wanted:
            print("EXAMPLE\t" + "\t".join(sanitize(row[col]) for col in COLUMNS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
