#!/usr/bin/env python3
"""Build PDF files from canonical TeX sources with XeLaTeX / CTeX."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "catalog.json"
STYLE_PREAMBLE = ROOT / "tex" / "style" / "preamble.tex"
STYLE_DRIVER = ROOT / "tex" / "style" / "driver.tex"
COVER_TEMPLATE = ROOT / "tex" / "cover.tex"
BUILD_DIR = ROOT / ".build" / "pdf"
DEFAULT_OUTPUT = ROOT / "dist"
REPORT = ROOT / "reports" / "pdf-build.json"

AUTHOR = "数理化自学丛书编委会"
LANGUAGE = "zh-CN"
FATAL_LOG = re.compile(
    r"^! (?:Emergency stop|Fatal [Ee]rror|Unable to load picture|"
    r"I can't find file|LaTeX Error: File `)",
    re.M,
)


class BuildError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_pdf_library():
    try:
        from PyPDF2 import PdfReader, PdfWriter  # type: ignore
    except ImportError:
        try:
            from pypdf import PdfReader, PdfWriter  # type: ignore
        except ImportError as exc:
            raise BuildError(
                "合订 PDF 需要 PyPDF2 或 pypdf：python3 -m pip install PyPDF2"
            ) from exc
    return PdfReader, PdfWriter


def load_catalog() -> dict:
    payload = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    if len(payload.get("books", [])) != 17:
        raise BuildError("catalog.json 必须登记 17 册")
    if len(payload.get("collections", [])) != 3:
        raise BuildError("catalog.json 必须登记 3 个合订本")
    return payload


def xelatex_version() -> str | None:
    executable = shutil.which("xelatex")
    if executable is None:
        return None
    proc = subprocess.run([executable, "--version"], text=True, capture_output=True, check=True)
    return proc.stdout.splitlines()[0]


def volume_pdf_name(book: dict) -> str:
    return f"{Path(book['file']).stem}.pdf"


def collection_pdf_names(collection: dict) -> tuple[str, str]:
    return f"{collection['title']}.pdf", f"{collection['stem']}.pdf"


def _pdf_obj(value):
    from PyPDF2.generic import IndirectObject

    if isinstance(value, IndirectObject):
        return value.get_object()
    return value


def pdf_font_names(reader) -> set[str]:
    names: set[str] = set()

    def walk(font) -> None:
        font = _pdf_obj(font)
        if not hasattr(font, "get"):
            return
        for key in ("/BaseFont", "/FontName"):
            if key in font:
                names.add(str(font[key]))
        descriptor = font.get("/FontDescriptor")
        if descriptor is not None:
            descriptor = _pdf_obj(descriptor)
            if "/FontName" in descriptor:
                names.add(str(descriptor["/FontName"]))
        descendants = font.get("/DescendantFonts")
        if descendants is not None:
            for child in _pdf_obj(descendants):
                walk(child)

    for page in reader.pages[:12]:
        resources = _pdf_obj(page.get("/Resources"))
        if not resources:
            continue
        fonts = _pdf_obj(resources.get("/Font")) or {}
        for font in fonts.values():
            walk(font)
    return names


def outline_count(reader) -> int:
    outline = getattr(reader, "outline", None) or []
    return len(outline)


def validate_pdf(path: Path, title: str, *, require_outline: bool = True) -> dict[str, object]:
    errors: list[str] = []
    if not path.is_file():
        return {"status": "FAIL", "errors": ["输出不存在"], "pages": 0, "bytes": 0}
    data = path.read_bytes()
    if not data.startswith(b"%PDF-"):
        errors.append("PDF 签名错误")
    if b"%%EOF" not in data[-8192:]:
        errors.append("PDF 缺少末尾 EOF")
    pages = 0
    outlines = 0
    metadata_title = None
    fonts: list[str] = []
    try:
        PdfReader, _PdfWriter = load_pdf_library()
    except BuildError:
        PdfReader = None  # type: ignore
    if PdfReader is not None:
        try:
            reader = PdfReader(str(path))
            pages = len(reader.pages)
            if pages < 1:
                errors.append("页数为 0")
            outlines = outline_count(reader)
            if require_outline and outlines < 1:
                root = _pdf_obj(reader.trailer.get("/Root"))
                if root is None or root.get("/Outlines") is None:
                    errors.append("缺少 PDF 书签")
                else:
                    outlines = 1
            fonts = sorted(pdf_font_names(reader))
            if not any("Fandol" in name for name in fonts):
                errors.append(f"未嵌入 Fandol 中文字体：{fonts[:8]}")
            meta = reader.metadata or {}
            metadata_title = meta.get("/Title")
            if metadata_title and title not in str(metadata_title):
                errors.append(f"PDF 标题为 {metadata_title!r}，应包含 {title!r}")
        except Exception as exc:  # noqa: BLE001 - validation must report reader failures
            errors.append(f"PDF 解析失败：{exc}")
    elif path.stat().st_size < 1024:
        errors.append("PDF 过小")
    return {
        "status": "PASS" if not errors else "FAIL",
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
        "pages": pages,
        "outline_items": outlines,
        "fonts": fonts,
        "metadata_title": metadata_title,
        "errors": errors,
    }


def run_xelatex(source_tex: Path, work: Path, epoch: int) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["SOURCE_DATE_EPOCH"] = str(epoch)
    env["FORCE_SOURCE_DATE"] = "1"
    env["TZ"] = "UTC"
    rel_out = os.path.relpath(work, ROOT)
    rel_tex = os.path.relpath(source_tex, ROOT)
    command = [
        "xelatex",
        "-interaction=nonstopmode",
        "-file-line-error",
        f"-output-directory={rel_out}",
        rel_tex,
    ]
    last = subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True)
    last = subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True)
    last = subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True)
    return last


def tex_source_path(book: dict) -> Path:
    return ROOT / "tex" / "books" / f"{book['title']}.tex"


def write_driver(book: dict, destination: Path) -> None:
    content = tex_source_path(book)
    if not content.is_file():
        raise BuildError(f"TeX 正文不存在：{content}")
    text = STYLE_DRIVER.read_text(encoding="utf-8")
    text = text.replace("BOOKTITLE", book["title"])
    text = text.replace("BOOKAUTHOR", AUTHOR)
    text = text.replace("BOOKCONTENT", content.relative_to(ROOT).as_posix())
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding="utf-8")


def build_one(book: dict, output_dir: Path, epoch: int) -> tuple[str, dict[str, object]]:
    work = BUILD_DIR / "volumes" / Path(book["file"]).stem
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True, exist_ok=True)
    driver = work / "book.tex"
    write_driver(book, driver)
    source_sha = sha256(tex_source_path(book))
    latex_proc = run_xelatex(driver, work, epoch)
    pdf_candidate = work / "book.pdf"
    log_path = work / "book.log"
    log_text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.is_file() else ""
    tex_errors = [line for line in log_text.splitlines() if line.startswith("! ")]
    if not pdf_candidate.is_file() or FATAL_LOG.search(log_text):
        log_tail = "\n".join(log_text.splitlines()[-40:])
        raise BuildError(
            f"{book['title']}: XeLaTeX 失败：\n{latex_proc.stderr[-2000:]}\n{log_tail}"
        )
    output = output_dir / volume_pdf_name(book)
    output_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(pdf_candidate, output)
    validation = validate_pdf(output, book["title"])
    row: dict[str, object] = {
        "kind": "volume",
        "source": tex_source_path(book).relative_to(ROOT).as_posix(),
        "source_sha256": source_sha,
        "output": output.relative_to(ROOT).as_posix() if output.is_relative_to(ROOT) else str(output),
        "xelatex_errors": tex_errors,
        "validation": validation,
    }
    return book["file"], row


def build_cover(collection: dict, work: Path, epoch: int) -> Path:
    tex = COVER_TEMPLATE.read_text(encoding="utf-8")
    tex = tex.replace("COVER_TITLE", collection["title"]).replace("COVER_AUTHOR", AUTHOR)
    source = work / "cover.tex"
    source.write_text(tex, encoding="utf-8")
    proc = run_xelatex(source, work, epoch)
    pdf = work / "cover.pdf"
    if proc.returncode != 0 or not pdf.is_file():
        raise BuildError(f"{collection['title']}: 封面编译失败：\n{proc.stderr[-2000:]}")
    return pdf


def build_collection(
    collection: dict,
    books_by_title: dict[str, dict],
    output_dir: Path,
    epoch: int,
) -> tuple[str, dict[str, object]]:
    PdfReader, PdfWriter = load_pdf_library()
    work = BUILD_DIR / "collections" / collection["stem"]
    work.mkdir(parents=True, exist_ok=True)
    cover = build_cover(collection, work, epoch)
    writer = PdfWriter()
    writer.append(str(cover), import_outline=False)
    missing: list[str] = []
    members: list[dict[str, object]] = []
    for title in collection["books"]:
        book = books_by_title.get(title)
        if book is None:
            missing.append(title)
            continue
        volume_path = output_dir / volume_pdf_name(book)
        if not volume_path.is_file():
            missing.append(title)
            continue
        writer.append(str(volume_path), outline_item=title, import_outline=True)
        members.append({"title": title, "file": volume_path.name, "pages": len(PdfReader(str(volume_path)).pages)})
    if missing:
        raise BuildError(f"{collection['title']}: 缺少分册 PDF：{missing}")
    writer.add_metadata(
        {
            "/Title": collection["title"],
            "/Author": AUTHOR,
            "/Lang": LANGUAGE,
            "/Producer": "XeLaTeX",
        }
    )
    chinese_name, ascii_name = collection_pdf_names(collection)
    primary = output_dir / chinese_name
    output_dir.mkdir(parents=True, exist_ok=True)
    with primary.open("wb") as handle:
        writer.write(handle)
    alias = output_dir / ascii_name
    if alias.resolve() != primary.resolve():
        shutil.copy2(primary, alias)
    validation = validate_pdf(primary, collection["title"])
    alias_validation = validate_pdf(alias, collection["title"])
    if alias_validation["status"] != "PASS":
        validation["status"] = "FAIL"
        validation["errors"] = list(validation.get("errors") or []) + [
            f"ASCII 副本校验失败：{alias_validation.get('errors')}"
        ]
    row = {
        "kind": "collection",
        "source": collection["stem"],
        "output": primary.relative_to(ROOT).as_posix() if primary.is_relative_to(ROOT) else str(primary),
        "alias": alias.relative_to(ROOT).as_posix() if alias.is_relative_to(ROOT) else str(alias),
        "members": members,
        "validation": validation,
    }
    return collection["stem"], row


def select_books(books: list[dict], selectors: list[str]) -> list[dict]:
    if not selectors:
        return books
    selected: list[dict] = []
    for selector in selectors:
        matches = [
            book
            for book in books
            if selector in {book["title"], book["file"], Path(book["file"]).stem}
        ]
        if len(matches) != 1:
            raise BuildError(f"书目选择器必须唯一匹配：{selector!r}，实际 {len(matches)}")
        if matches[0] not in selected:
            selected.append(matches[0])
    return selected


def select_collections(collections: list[dict], selectors: list[str]) -> list[dict]:
    if not selectors:
        return collections
    selected: list[dict] = []
    for selector in selectors:
        matches = [
            item
            for item in collections
            if selector in {item["title"], item["stem"]}
        ]
        if len(matches) != 1:
            raise BuildError(f"合订选择器必须唯一匹配：{selector!r}，实际 {len(matches)}")
        if matches[0] not in selected:
            selected.append(matches[0])
    return selected


def write_report(payload: dict) -> None:
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book", action="append", default=[], help="按题名、源文件名或文件 stem 构建分册；可重复")
    parser.add_argument("--collection", action="append", default=[], help="按合订题名或 stem 构建合订本；可重复")
    parser.add_argument("--jobs", type=int, default=min(2, os.cpu_count() or 1))
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--verify-only", action="store_true", help="只验证已有 PDF，不重新构建")
    parser.add_argument("--skip-collections", action="store_true", help="只构建或校验 17 册分册")
    parser.add_argument("--from-tex", action="store_true", help="已废弃：本分支始终从 TeX 源构建")
    args = parser.parse_args()

    if shutil.which("xelatex") is None and not args.verify_only:
        print("ERROR: 未找到 xelatex；请安装 TeX Live / TinyTeX 后运行 make tex-deps", file=sys.stderr)
        return 2
    if not STYLE_PREAMBLE.is_file() or not STYLE_DRIVER.is_file():
        print("ERROR: 缺少 tex/style/preamble.tex 或 tex/style/driver.tex", file=sys.stderr)
        return 2

    catalog = load_catalog()
    books = catalog["books"]
    collections = catalog["collections"]
    selected_books = select_books(books, args.book)
    if args.book and not args.collection:
        selected_collections: list[dict] = []
    elif args.skip_collections and not args.collection:
        selected_collections = []
    else:
        selected_collections = select_collections(collections, args.collection)
        if args.collection and not args.book:
            titles = [title for item in selected_collections for title in item["books"]]
            selected_books = select_books(books, titles)

    epoch = int(os.environ.get("SOURCE_DATE_EPOCH", catalog["source_date_epoch"]))
    output_dir = args.output_dir.resolve()
    rows: dict[str, dict[str, object]] = {}

    if args.verify_only:
        for book in selected_books:
            output = output_dir / volume_pdf_name(book)
            rows[book["file"]] = {"kind": "volume", "validation": validate_pdf(output, book["title"])}
        for collection in selected_collections:
            chinese_name, _ascii_name = collection_pdf_names(collection)
            output = output_dir / chinese_name
            rows[collection["stem"]] = {
                "kind": "collection",
                "validation": validate_pdf(output, collection["title"]),
            }
    else:
        BUILD_DIR.mkdir(parents=True, exist_ok=True)
        with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as executor:
            futures = {executor.submit(build_one, book, output_dir, epoch): book for book in selected_books}
            for future in as_completed(futures):
                book = futures[future]
                try:
                    name, row = future.result()
                except Exception as exc:  # noqa: BLE001 - per-book failure is recorded
                    name = book["file"]
                    row = {"kind": "volume", "validation": {"status": "FAIL", "errors": [str(exc)]}}
                rows[name] = row
                print(f"{name}: {row['validation']['status']}")

        books_by_title = {book["title"]: book for book in books}
        volume_failed = {
            book["title"]
            for book in selected_books
            if rows.get(book["file"], {}).get("validation", {}).get("status") != "PASS"
        }
        for collection in selected_collections:
            needed = set(collection["books"])
            if needed & volume_failed:
                rows[collection["stem"]] = {
                    "kind": "collection",
                    "validation": {
                        "status": "FAIL",
                        "errors": [f"分册失败，跳过合订：{sorted(needed & volume_failed)}"],
                    },
                }
                print(f"{collection['stem']}: FAIL")
                continue
            try:
                name, row = build_collection(collection, books_by_title, output_dir, epoch)
            except Exception as exc:  # noqa: BLE001 - per-collection failure is recorded
                name = collection["stem"]
                row = {"kind": "collection", "validation": {"status": "FAIL", "errors": [str(exc)]}}
            rows[name] = row
            print(f"{name}: {row['validation']['status']}")

    ordered_keys = [book["file"] for book in selected_books] + [item["stem"] for item in selected_collections]
    ordered_rows = {key: rows[key] for key in ordered_keys if key in rows}
    passed = sum(row["validation"]["status"] == "PASS" for row in ordered_rows.values())
    payload = {
        "schema_version": 1,
        "status": "PASS" if ordered_rows and passed == len(ordered_rows) else "FAIL",
        "mode": "verify-only" if args.verify_only else "build",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_date_epoch": epoch,
        "xelatex": xelatex_version(),
        "summary": {
            "targets": len(ordered_rows),
            "passed": passed,
            "failed": len(ordered_rows) - passed,
            "volumes": sum(1 for row in ordered_rows.values() if row.get("kind") == "volume"),
            "collections": sum(1 for row in ordered_rows.values() if row.get("kind") == "collection"),
        },
        "targets": ordered_rows,
    }
    write_report(payload)
    print(json.dumps(payload["summary"], ensure_ascii=False))
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
