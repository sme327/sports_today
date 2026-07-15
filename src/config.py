from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

DATA_DIR = PROJECT_ROOT / "data"
CURRENT_DIR = DATA_DIR / "current"
ARCHIVE_DIR = DATA_DIR / "archive"
INCOMING_DIR = DATA_DIR / "incoming"
LOG_DIR = PROJECT_ROOT / "logs"
DATABASE_DIR = PROJECT_ROOT / "database"

CURRENT_FEED = CURRENT_DIR / "mlb_pbp_current.xlsx"
DB_PATH = DATABASE_DIR / "sportshub.db"
IMPORT_LOG = LOG_DIR / "mlb_import_history.csv"

DOWNLOADS_DIR = Path.home() / "Downloads"

# The vendor's current naming pattern:
# 07-12-2026-mlb-season-pbp-feed.xlsx
DOWNLOAD_GLOBS = (
    "*-mlb-season-pbp-feed.xlsx",
    "*mlb*season*pbp*feed*.xlsx",
)
