#!/usr/bin/env python3
"""Audit repository portability and GitHub push readiness."""
from __future__ import annotations

import ast
import json
import os
import re
import struct
import subprocess
import sys
import unicodedata
import zlib
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports" / "repository-audit.json"
CATALOG = ROOT / "catalog.json"
BOOK_GLOB = "* - 数理化自学丛书编委会.md"
GITHUB_MAX_FILE = 100 * 1024 * 1024
GITHUB_WARNING_FILE = 50 * 1024 * 1024
WINDOWS_RESERVED = {
    "con", "prn", "aux", "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}
REQUIRED = {
    ".editorconfig",
    ".gitattributes",
    ".gitignore",
    "AGENTS.md",
    "CHANGELOG.md",
    "Makefile",
    "README.md",
    "catalog.json",
    "docs/KNOWN_ISSUES.md",
    "docs/MAINTENANCE.md",
    "docs/PRIVACY.md",
    "reports/.gitkeep",
    "scripts/audit_pdfs.py",
    "scripts/audit_privacy.py",
    "scripts/audit_repository.py",
    "scripts/audit_sources.py",
    "scripts/audit_tex_sources.py",
    "tex/cover.tex",
    "tex/packages.txt",
    "tex/style/preamble.tex",
    "tex/style/driver.tex",
    "raw/README.md",
    "raw/SHA256SUMS.txt",
}
LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")


def git_bytes(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=ROOT, stderr=subprocess.DEVNULL)


def candidates() -> list[Path]:
    raw = git_bytes("ls-files", "--cached", "--others", "--exclude-standard", "-z")
    return [ROOT / value.decode("utf-8") for value in raw.split(b"\0") if value]


def record(errors: list[str], message: str) -> None:
    errors.append(message)


def check_png(path: Path, errors: list[str]) -> tuple[int, int]:
    data = path.read_bytes()
    relative = path.relative_to(ROOT).as_posix()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        record(errors, f"PNG 签名错误：{relative}")
        return 0, 0
    offset = 8
    width = height = 0
    saw_iend = False
    while offset + 12 <= len(data):
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        chunk_type = data[offset + 4 : offset + 8]
        payload_start = offset + 8
        payload_end = payload_start + length
        crc_end = payload_end + 4
        if crc_end > len(data):
            record(errors, f"PNG 块截断：{relative}")
            return width, height
        expected_crc = struct.unpack(">I", data[payload_end:crc_end])[0]
        actual_crc = zlib.crc32(chunk_type)
        actual_crc = zlib.crc32(data[payload_start:payload_end], actual_crc) & 0xFFFFFFFF
        if actual_crc != expected_crc:
            record(errors, f"PNG CRC 错误：{relative}")
            return width, height
        if chunk_type == b"IHDR":
            if length != 13:
                record(errors, f"PNG IHDR 长度错误：{relative}")
            else:
                width, height = struct.unpack(">II", data[payload_start : payload_start + 8])
        offset = crc_end
        if chunk_type == b"IEND":
            saw_iend = True
            break
    if not saw_iend:
        record(errors, f"PNG 缺少 IEND：{relative}")
    if width <= 0 or height <= 0:
        record(errors, f"PNG 尺寸无效：{relative}")
    return width, height


def check_pdf(path: Path, errors: list[str]) -> None:
    data = path.read_bytes()
    relative = path.relative_to(ROOT).as_posix()
    if not data.startswith(b"%PDF-"):
        record(errors, f"PDF 签名错误：{relative}")
    if b"%%EOF" not in data[-4096:]:
        record(errors, f"PDF 缺少末尾 EOF：{relative}")


def check_markdown_links(errors: list[str]) -> int:
    checked = 0
    documents = [ROOT / "README.md", *sorted((ROOT / "docs").glob("*.md"))]
    for document in documents:
        text = document.read_text(encoding="utf-8")
        for match in LINK_RE.finditer(text):
            value = match.group(1).strip()
            if " " in value and not value.startswith("<"):
                value = value.split(" ", 1)[0]
            value = value.strip("<>")
            parts = urlsplit(value)
            if parts.scheme or parts.netloc or not parts.path:
                continue
            checked += 1
            target = (document.parent / unquote(parts.path)).resolve()
            try:
                target.relative_to(ROOT)
            except ValueError:
                record(errors, f"文档链接越出仓库：{document.relative_to(ROOT)} -> {value}")
                continue
            if not target.exists():
                record(errors, f"文档链接不存在：{document.relative_to(ROOT)} -> {value}")
    return checked


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []
    paths = candidates()
    relative_paths = [path.relative_to(ROOT).as_posix() for path in paths]
    path_set = set(relative_paths)

    missing_required = sorted(REQUIRED - path_set)
    if missing_required:
        record(errors, f"缺少必需仓库文件：{missing_required}")

    root_books = list(ROOT.glob(BOOK_GLOB))
    if root_books:
        record(errors, f"根目录存在 {len(root_books)} 个单册 Markdown")

    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    books = catalog.get("books", [])
    listed_books = [item.get("file", "") for item in books]
    actual_books = sorted(path.relative_to(ROOT).as_posix() for path in (ROOT / "books").glob(BOOK_GLOB))
    if len(books) != 17 or set(listed_books) != set(actual_books):
        record(errors, "catalog.json 与 books/ 中的 17 册 Markdown 不一致")
    identifiers = [item.get("identifier", "") for item in books]
    if len(set(identifiers)) != len(identifiers):
        record(errors, "catalog.json 存在重复 EPUB identifier")
    raw_pdfs = sorted((ROOT / "raw").glob("*.pdf"))
    expected_raw_names = {
        f"{item.get('title', '')} - 数理化自学丛书编委会.pdf" for item in books
    }
    if len(raw_pdfs) != 17 or {path.name for path in raw_pdfs} != expected_raw_names:
        record(errors, "raw/ 中的17册 PDF 与 catalog.json 书目不一致")

    collisions: dict[str, list[str]] = defaultdict(list)
    non_nfc: list[str] = []
    windows_incompatible: list[str] = []
    max_path_chars = 0
    max_segment_bytes = 0
    for relative in relative_paths:
        normalized = unicodedata.normalize("NFC", relative)
        collisions[normalized.casefold()].append(relative)
        if normalized != relative:
            non_nfc.append(relative)
        max_path_chars = max(max_path_chars, len(relative))
        for segment in Path(relative).parts:
            max_segment_bytes = max(max_segment_bytes, len(segment.encode("utf-8")))
            stem = segment.split(".", 1)[0].casefold()
            if (
                stem in WINDOWS_RESERVED
                or segment.endswith((" ", "."))
                or any(character in segment for character in '<>:"\\|?*')
            ):
                windows_incompatible.append(relative)
    duplicate_paths = [values for values in collisions.values() if len(values) > 1]
    if duplicate_paths:
        record(errors, f"存在 Unicode/大小写路径冲突：{duplicate_paths[:5]}")
    if non_nfc:
        record(errors, f"存在非 NFC 文件名：{non_nfc[:10]}")
    if windows_incompatible:
        record(errors, f"存在 Windows 不兼容路径：{sorted(set(windows_incompatible))[:10]}")
    if max_segment_bytes > 255:
        record(errors, f"路径分段超过 255 字节：{max_segment_bytes}")

    text_files = 0
    png_files = 0
    pdf_files = 0
    executable_files: list[str] = []
    largest_file = 0
    total_bytes = 0
    for path, relative in zip(paths, relative_paths):
        if path.is_symlink():
            record(errors, f"仓库候选中存在符号链接：{relative}")
            continue
        if not path.is_file():
            record(errors, f"仓库候选不是普通文件：{relative}")
            continue
        size = path.stat().st_size
        largest_file = max(largest_file, size)
        total_bytes += size
        if size > GITHUB_MAX_FILE:
            record(errors, f"文件超过 GitHub 100 MiB 限制：{relative}")
        elif size > GITHUB_WARNING_FILE:
            warnings.append(f"文件超过 50 MiB：{relative}")
        if os.access(path, os.X_OK):
            executable_files.append(relative)
        if path.suffix.casefold() == ".png":
            png_files += 1
            check_png(path, errors)
            continue
        if path.suffix.casefold() == ".pdf":
            pdf_files += 1
            check_pdf(path, errors)
            continue
        data = path.read_bytes()
        if b"\x00" in data:
            record(errors, f"非 PNG 候选包含 NUL：{relative}")
            continue
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            record(errors, f"文本不是 UTF-8：{relative}")
            continue
        text_files += 1
        if data.startswith(b"\xef\xbb\xbf"):
            record(errors, f"文本含 UTF-8 BOM：{relative}")
        if b"\r\n" in data or b"\r" in data:
            record(errors, f"文本不是纯 LF 换行：{relative}")
        if data and not data.endswith(b"\n"):
            record(errors, f"文本缺少末尾换行：{relative}")
        if path.suffix == ".py":
            try:
                ast.parse(text, filename=relative)
            except SyntaxError as exc:
                record(errors, f"Python 语法错误：{relative}:{exc.lineno}")

    allowed_executable = {
        "scripts/audit_pdfs.py",
        "scripts/audit_privacy.py",
        "scripts/audit_repository.py",
        "scripts/audit_sources.py",
        "scripts/audit_tex_sources.py",
    }
    unexpected_executable = sorted(set(executable_files) - allowed_executable)
    if unexpected_executable:
        record(errors, f"存在意外可执行文件：{unexpected_executable}")

    ignored_checks = {
        ".build": ROOT / ".build",
        "dist": ROOT / "dist",
        "reports_json": ROOT / "reports" / "privacy-audit.json",
        "pycache": ROOT / "scripts" / "__pycache__",
    }
    for label, path in ignored_checks.items():
        proc = subprocess.run(
            ["git", "check-ignore", "-q", str(path.relative_to(ROOT))], cwd=ROOT, check=False
        )
        if proc.returncode != 0:
            record(errors, f"生成物未被 .gitignore 排除：{label}")

    linked_documents = check_markdown_links(errors)
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    rights_notice = "权利说明" in readme and "版权" in readme
    if not rights_notice:
        record(errors, "README 缺少明确权利说明")
    license_files = [name for name in path_set if Path(name).name.casefold().startswith("license")]
    if license_files:
        warnings.append("检测到 LICENSE；请确认没有对原著内容授予无权授予的许可")

    payload = {
        "schema_version": 1,
        "status": "PASS" if not errors else "FAIL",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "push_candidates": len(paths),
            "text_files": text_files,
            "png_files": png_files,
            "pdf_files": pdf_files,
            "total_bytes": total_bytes,
            "largest_file_bytes": largest_file,
            "files_over_50_mib": sum(path.stat().st_size > GITHUB_WARNING_FILE for path in paths if path.is_file()),
            "root_book_markdown": len(root_books),
            "catalog_books": len(books),
            "relative_doc_links_checked": linked_documents,
            "unicode_casefold_collisions": len(duplicate_paths),
            "non_nfc_paths": len(non_nfc),
            "windows_incompatible_paths": len(set(windows_incompatible)),
            "max_path_chars": max_path_chars,
            "max_segment_bytes": max_segment_bytes,
            "license_files": len(license_files),
            "rights_notice": rights_notice,
            "errors": len(errors),
            "warnings": len(warnings),
        },
        "errors": errors,
        "warnings": warnings,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload["summary"], ensure_ascii=False))
    if errors:
        for error in errors[:50]:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
