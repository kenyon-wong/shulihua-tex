#!/usr/bin/env python3
"""Audit Git push candidates and generated books for local or secret information."""
from __future__ import annotations

import argparse
import json
import os
import re
import socket
import struct
import subprocess
import sys
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports" / "privacy-audit.json"

TEXT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "posix_user_home_path",
        re.compile(r"(?<![\w/])/(?:home|Users)/[A-Za-z0-9._-]+(?:/[^\s<>\"']*)?", re.I),
    ),
    (
        "mounted_windows_user_path",
        re.compile(r"(?<![\w/])/mnt/[a-z]/Users/[A-Za-z0-9._-]+(?:/[^\s<>\"']*)?", re.I),
    ),
    (
        "windows_user_path",
        re.compile(
            r"(?<![A-Za-z0-9])[A-Za-z]:[\\/](?:Users|Documents and Settings)[\\/]"
            r"[^\\/\s<>\"']+(?:[\\/][^\s<>\"']*)?",
            re.I,
        ),
    ),
    (
        "wsl_unc_path",
        re.compile(r"\\\\wsl(?:\.localhost)?\\[^\s<>\"']+", re.I),
    ),
    (
        "email_address",
        re.compile(r"(?<![\w.+-])[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}(?![\w.-])", re.I),
    ),
    (
        "private_or_loopback_ipv4",
        re.compile(
            r"(?<!\d)(?:127\.0\.0\.1|10\.(?:\d{1,3}\.){2}\d{1,3}|"
            r"192\.168\.(?:\d{1,3}\.)\d{1,3}|"
            r"172\.(?:1[6-9]|2\d|3[01])\.(?:\d{1,3}\.)\d{1,3})(?!\d)"
        ),
    ),
    (
        "localhost_name",
        re.compile(r"(?<![\w.-])" + "local" + "host" + r"(?![\w.-])", re.I),
    ),
    ("aws_access_key", re.compile(r"(?<![A-Z0-9])(?:AKIA|ASIA)[0-9A-Z]{16}(?![A-Z0-9])")),
    (
        "github_token",
        re.compile(
            r"(?<![A-Za-z0-9_])(?:ghp_[A-Za-z0-9]{30,}|"
            r"github_pat_[A-Za-z0-9_]{30,})(?![A-Za-z0-9_])"
        ),
    ),
    (
        "openai_api_key",
        re.compile(r"(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{20,}(?![A-Za-z0-9_-])"),
    ),
    (
        "slack_token",
        re.compile(r"(?<![A-Za-z0-9-])xox[baprs]-[A-Za-z0-9-]{10,}(?![A-Za-z0-9-])"),
    ),
    (
        "private_key_block",
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    ),
    (
        "credential_assignment",
        re.compile(
            r"(?:api[_-]?key|access[_-]?key|secret[_-]?key|client[_-]?secret|"
            r"password|passwd|session[_-]?token)[ \t]*[:=][ \t]*[\"']?[^\s\"']{8,}",
            re.I,
        ),
    ),
    (
        "credential_in_url",
        re.compile(r"https?://[^\s/@:]+:[^\s/@]+@", re.I),
    ),
    ("possible_cn_phone", re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")),
    ("possible_cn_id", re.compile(r"(?<!\d)\d{17}[0-9Xx](?!\d)")),
)

SENSITIVE_NAMES = {
    ".env",
    ".env.local",
    ".env.production",
    "credentials",
    "credentials.json",
    "cookies.txt",
    "id_rsa",
    "id_ed25519",
    "known_hosts",
}
SENSITIVE_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".kdbx"}
SENSITIVE_PARTS = {".ssh", ".aws", ".gnupg"}
PRIVACY_PNG_CHUNKS = {"tEXt", "zTXt", "iTXt", "eXIf", "tIME"}


def git_bytes(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=ROOT, stderr=subprocess.DEVNULL)


def push_candidates() -> list[Path]:
    raw = git_bytes("ls-files", "--cached", "--others", "--exclude-standard", "-z")
    return [ROOT / value.decode("utf-8") for value in raw.split(b"\0") if value]


def local_identifiers() -> set[str]:
    values = {
        os.environ.get("USER", ""),
        os.environ.get("USERNAME", ""),
        Path.home().name,
        socket.gethostname(),
    }
    windows_users = Path("/mnt/c/Users")
    if windows_users.is_dir():
        ignored = {"all users", "default", "default user", "public", "desktop.ini"}
        try:
            values.update(path.name for path in windows_users.iterdir() if path.name.lower() not in ignored)
        except OSError:
            pass
    return {value for value in values if len(value) >= 4}


def line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def record(findings: list[dict[str, object]], kind: str, source: str, line: int | None = None) -> None:
    row: dict[str, object] = {"type": kind, "source": source}
    if line is not None:
        row["line"] = line
    findings.append(row)


def scan_text(text: str, source: str, findings: list[dict[str, object]], identifiers: set[str]) -> None:
    for kind, pattern in TEXT_PATTERNS:
        for match in pattern.finditer(text):
            record(findings, kind, source, line_number(text, match.start()))
    lowered = text.casefold()
    for value in identifiers:
        pattern = re.compile(rf"(?<![\w.-]){re.escape(value.casefold())}(?![\w.-])")
        for match in pattern.finditer(lowered):
            record(findings, "local_user_or_host_identifier", source, line_number(text, match.start()))


def scan_candidate_names(paths: list[Path], findings: list[dict[str, object]], identifiers: set[str]) -> None:
    for path in paths:
        relative = path.relative_to(ROOT).as_posix()
        lowered_parts = {part.casefold() for part in path.relative_to(ROOT).parts}
        if path.name.casefold() in SENSITIVE_NAMES:
            record(findings, "sensitive_filename", relative)
        if path.suffix.casefold() in SENSITIVE_SUFFIXES:
            record(findings, "sensitive_file_extension", relative)
        if lowered_parts & SENSITIVE_PARTS:
            record(findings, "sensitive_directory", relative)
        for value in identifiers:
            if value.casefold() in relative.casefold():
                record(findings, "local_identifier_in_filename", relative)


def scan_png(path: Path, findings: list[dict[str, object]], chunk_counts: Counter[str]) -> None:
    relative = path.relative_to(ROOT).as_posix()
    data = path.read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        record(findings, "invalid_png_signature", relative)
        return
    offset = 8
    saw_iend = False
    while offset + 12 <= len(data):
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        chunk_type = data[offset + 4 : offset + 8].decode("ascii", errors="replace")
        end = offset + 12 + length
        if end > len(data):
            record(findings, "truncated_png_chunk", relative)
            return
        chunk_counts[chunk_type] += 1
        if chunk_type in PRIVACY_PNG_CHUNKS:
            record(findings, f"png_metadata_chunk_{chunk_type}", relative)
        offset = end
        if chunk_type == "IEND":
            saw_iend = True
            break
    if not saw_iend:
        record(findings, "png_missing_iend", relative)


def scan_epubs(findings: list[dict[str, object]], identifiers: set[str]) -> tuple[int, int]:
    epub_count = 0
    entry_count = 0
    for path in sorted((ROOT / "dist").glob("*.epub")):
        epub_count += 1
        try:
            with zipfile.ZipFile(path) as archive:
                for name in archive.namelist():
                    entry_count += 1
                    suffix = Path(name).suffix.casefold()
                    if suffix not in {".xhtml", ".html", ".xml", ".opf", ".ncx", ".css", ".txt"}:
                        continue
                    data = archive.read(name)
                    try:
                        text = data.decode("utf-8")
                    except UnicodeDecodeError:
                        record(findings, "non_utf8_epub_text_entry", f"dist/{path.name}!/{name}")
                        continue
                    scan_text(text, f"dist/{path.name}!/{name}", findings, identifiers)
        except (OSError, zipfile.BadZipFile) as exc:
            record(findings, f"unreadable_epub_{type(exc).__name__}", f"dist/{path.name}")
    return epub_count, entry_count


def scan_commit_identities(findings: list[dict[str, object]]) -> int:
    try:
        commits = git_bytes("rev-list", "--all").decode("ascii").splitlines()
    except subprocess.CalledProcessError:
        return 0
    if not commits:
        return 0
    emails = git_bytes("log", "--all", "--format=%ae%n%ce").decode("utf-8", errors="replace").splitlines()
    for email in sorted(set(value.strip() for value in emails if value.strip())):
        if not email.lower().endswith("@users.noreply.github.com"):
            record(findings, "non_noreply_email_in_git_history", ".git history")
    patch = git_bytes("log", "-p", "--all", "--pretty=format:").decode("utf-8", errors="replace")
    scan_text(patch, ".git history patches", findings, set())
    return len(commits)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-generated", action="store_true", help="不扫描 dist/ 中的 EPUB")
    args = parser.parse_args()

    findings: list[dict[str, object]] = []
    warnings: list[str] = []
    identifiers = local_identifiers()
    paths = push_candidates()
    scan_candidate_names(paths, findings, identifiers)

    text_files = 0
    png_files = 0
    pdf_files = 0
    png_chunks: Counter[str] = Counter()
    symlinks = 0
    for path in paths:
        relative = path.relative_to(ROOT).as_posix()
        if path.is_symlink():
            symlinks += 1
            target = os.readlink(path)
            if os.path.isabs(target):
                record(findings, "absolute_symlink_target", relative)
            continue
        if not path.is_file():
            record(findings, "non_regular_push_candidate", relative)
            continue
        if path.suffix.casefold() == ".png":
            png_files += 1
            scan_png(path, findings, png_chunks)
            continue
        if path.suffix.casefold() == ".pdf":
            pdf_files += 1
            data = path.read_bytes()
            if not data.startswith(b"%PDF-") or b"%%EOF" not in data[-4096:]:
                record(findings, "invalid_pdf_container", relative)
            # PDF objects、XMP、附件与主动内容由 make pdf-audit 的结构化门禁检查。
            continue
        data = path.read_bytes()
        if b"\x00" in data:
            warnings.append(f"未解析的二进制候选文件：{relative}")
            continue
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            record(findings, "non_utf8_text_candidate", relative)
            continue
        text_files += 1
        scan_text(text, relative, findings, identifiers)

    epub_count = 0
    epub_entries = 0
    if not args.skip_generated:
        epub_count, epub_entries = scan_epubs(findings, identifiers)

    commit_count = scan_commit_identities(findings)
    remote_lines = subprocess.run(
        ["git", "remote", "-v"], cwd=ROOT, text=True, capture_output=True, check=False
    ).stdout.splitlines()
    remote_names: set[str] = set()
    for remote in remote_lines:
        parts = remote.split()
        if len(parts) >= 2:
            remote_names.add(parts[0])
            parsed = urlsplit(parts[1])
            if parsed.password:
                record(findings, "credential_in_git_remote", ".git/config")

    payload = {
        "schema_version": 1,
        "status": "PASS" if not findings else "FAIL",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "Git push candidates plus generated EPUB text entries",
        "summary": {
            "push_candidates": len(paths),
            "text_files_scanned": text_files,
            "png_files_scanned": png_files,
            "pdf_files_scanned": pdf_files,
            "png_chunk_types": dict(sorted(png_chunks.items())),
            "symlinks": symlinks,
            "generated_epubs_scanned": epub_count,
            "generated_epub_entries_seen": epub_entries,
            "git_commits_scanned": commit_count,
            "git_remotes": len(remote_names),
            "local_identifiers_checked": len(identifiers),
            "findings": len(findings),
            "warnings": len(warnings),
        },
        "findings": findings,
        "warnings": warnings,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload["summary"], ensure_ascii=False))
    if findings:
        for row in findings[:50]:
            location = f":{row['line']}" if "line" in row else ""
            print(f"ERROR: {row['type']} at {row['source']}{location}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
