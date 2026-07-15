from __future__ import annotations

import argparse
import csv
import hashlib
import re
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from src.config import (
    ARCHIVE_DIR,
    CURRENT_FEED,
    DOWNLOADS_DIR,
    DOWNLOAD_GLOBS,
    IMPORT_LOG,
)


DATE_PATTERN = re.compile(
    r"(?P<month>\d{2})-(?P<day>\d{2})-(?P<year>\d{4})-mlb-season-pbp-feed\.xlsx$",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True)
class Candidate:
    path: Path
    feed_date: datetime
    modified_at: float


def file_sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def parse_feed_date(path: Path) -> datetime | None:
    match = DATE_PATTERN.search(path.name)
    if not match:
        return None
    try:
        return datetime(
            int(match.group("year")),
            int(match.group("month")),
            int(match.group("day")),
        )
    except ValueError:
        return None


def find_candidates(downloads_dir: Path) -> list[Candidate]:
    paths: set[Path] = set()
    for pattern in DOWNLOAD_GLOBS:
        paths.update(downloads_dir.glob(pattern))

    candidates: list[Candidate] = []
    for path in paths:
        if not path.is_file():
            continue
        feed_date = parse_feed_date(path)
        if feed_date is None:
            continue
        candidates.append(
            Candidate(
                path=path,
                feed_date=feed_date,
                modified_at=path.stat().st_mtime,
            )
        )

    return sorted(
        candidates,
        key=lambda c: (c.feed_date, c.modified_at),
        reverse=True,
    )


def append_log(
    *,
    status: str,
    source: Path | None,
    archive: Path | None,
    current: Path,
    source_hash: str | None,
    message: str,
) -> None:
    IMPORT_LOG.parent.mkdir(parents=True, exist_ok=True)
    exists = IMPORT_LOG.exists()
    with IMPORT_LOG.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "run_timestamp",
                "status",
                "source_file",
                "archive_file",
                "current_file",
                "source_sha256",
                "message",
            ],
        )
        if not exists:
            writer.writeheader()
        writer.writerow(
            {
                "run_timestamp": datetime.now().isoformat(timespec="seconds"),
                "status": status,
                "source_file": str(source) if source else "",
                "archive_file": str(archive) if archive else "",
                "current_file": str(current),
                "source_sha256": source_hash or "",
                "message": message,
            }
        )


def sync_latest(downloads_dir: Path, force: bool = False) -> tuple[Path, bool]:
    downloads_dir = downloads_dir.expanduser().resolve()
    if not downloads_dir.exists():
        raise FileNotFoundError(f"Downloads folder not found: {downloads_dir}")

    candidates = find_candidates(downloads_dir)
    if not candidates:
        patterns = ", ".join(DOWNLOAD_GLOBS)
        raise FileNotFoundError(
            f"No dated MLB play-by-play workbook found in {downloads_dir}. "
            f"Expected a file such as 07-12-2026-mlb-season-pbp-feed.xlsx. "
            f"Patterns checked: {patterns}"
        )

    latest = candidates[0]
    source = latest.path
    source_hash = file_sha256(source)

    if CURRENT_FEED.exists() and not force:
        current_hash = file_sha256(CURRENT_FEED)
        if source_hash == current_hash:
            message = f"Current file already matches {source.name}; no copy required."
            append_log(
                status="NO_CHANGE",
                source=source,
                archive=None,
                current=CURRENT_FEED,
                source_hash=source_hash,
                message=message,
            )
            print(message)
            return CURRENT_FEED, False

    archive_dir = ARCHIVE_DIR / f"{latest.feed_date:%Y}"
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_path = archive_dir / source.name

    if archive_path.exists():
        if file_sha256(archive_path) != source_hash:
            timestamp = datetime.now().strftime("%H%M%S")
            archive_path = archive_dir / f"{source.stem}-{timestamp}{source.suffix}"
    shutil.copy2(source, archive_path)

    CURRENT_FEED.parent.mkdir(parents=True, exist_ok=True)
    temporary = CURRENT_FEED.with_suffix(".xlsx.tmp")
    shutil.copy2(source, temporary)
    temporary.replace(CURRENT_FEED)

    message = (
        f"Copied {source.name} to {CURRENT_FEED.name} and archived it at "
        f"{archive_path.relative_to(ARCHIVE_DIR.parent)}."
    )
    append_log(
        status="COPIED",
        source=source,
        archive=archive_path,
        current=CURRENT_FEED,
        source_hash=source_hash,
        message=message,
    )
    print(message)
    return CURRENT_FEED, True


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Find the newest dated MLB play-by-play Excel feed in Downloads, "
            "archive it, and copy it to data/current/mlb_pbp_current.xlsx."
        )
    )
    parser.add_argument(
        "--downloads",
        type=Path,
        default=DOWNLOADS_DIR,
        help="Downloads directory to search. Defaults to ~/Downloads.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Copy and archive even when the newest file matches the current file.",
    )
    args = parser.parse_args()

    try:
        sync_latest(args.downloads, force=args.force)
        return 0
    except Exception as exc:
        append_log(
            status="FAILED",
            source=None,
            archive=None,
            current=CURRENT_FEED,
            source_hash=None,
            message=str(exc),
        )
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
