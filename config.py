"""
config.py -- Central configuration for the ADOA project.

Compares date columns using AI-suggested rules, detects missing data,
finds similar columns, and exports a consolidated CSV report.
"""

import os

# --- Project Paths ---------------------------------------------------------------
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(PROJECT_DIR, "output")
DRAFTS_DIR = os.path.join(OUTPUT_DIR, "drafts")
EXCELS_DIR = os.path.join(PROJECT_DIR, "Excels")

# --- Gemini AI -------------------------------------------------------------------
# Load API keys from .env file (keeps secrets out of source code)
def _load_env():
    """Load .env file into os.environ (no external dependency needed)."""
    env_path = os.path.join(PROJECT_DIR, ".env")
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ.setdefault(key.strip(), value.strip())

_load_env()

GEMINI_API_KEYS = [
    v for k, v in sorted(os.environ.items())
    if k.startswith("GEMINI_API_KEY_") and v
]
if not GEMINI_API_KEYS:
    print("[WARNING] No GEMINI_API_KEY_* found in .env -- AI features will use fallbacks.")
GEMINI_API_KEY = GEMINI_API_KEYS[0] if GEMINI_API_KEYS else ""  # backward compat alias
GEMINI_MODEL = "gemini-2.5-flash"

# --- Standardized Date Format ----------------------------------------------------
DATE_DISPLAY_FORMAT = "%Y-%m-%d %H:%M:%S"
DATE_ONLY_FORMAT = "%Y-%m-%d"

# --- Auto-Detection Patterns -----------------------------------------------------
# Substrings to match in column names (case-insensitive) for auto-detecting date columns
DATE_PATTERNS = [
    "date", "time", "created", "modified", "entry", "start", "end",
    "due", "expected", "actual", "timestamp", "datetime",
]

# Substrings to match in column names for ID-like columns
ID_PATTERNS = ["id", "no", "ticket", "number", "code", "key"]

# --- Default Comparison Rules (fallback when AI is unavailable) ------------------
# Each rule: col_a, col_b, rule (key), check_type (for generic handler), description
DEFAULT_COMPARISON_RULES = [
    {
        "col_a": "ENTRYDATETIME",
        "col_b": "MAINTENANCESTARTDATETIME",
        "rule": "START_BEFORE_ENTRY",
        "check_type": "A_BEFORE_B",
        "description": "Maintenance start should be before or equal to entry datetime",
    },
    {
        "col_a": "EXPECTEDDATEOFAVAILABILITY",
        "col_b": "ACTUALDATEOFAVAILABILITY",
        "rule": "EXPECTED_VS_ACTUAL_DATE",
        "check_type": "A_EQUALS_B_DATE",
        "description": "Expected and actual availability dates should match (date only, time ignored)",
    },
    {
        "col_a": "ACTUALDATEOFAVAILABILITY",
        "col_b": "CREATEDON",
        "rule": "CREATED_VS_ACTUAL",
        "check_type": "A_BEFORE_B",
        "description": "Check if details were filled (created) before or after work was completed (actual availability)",
    },
    {
        "col_a": "CREATEDON",
        "col_b": "MODIFIEDON",
        "rule": "MODIFIED_AFTER_CREATED",
        "check_type": "A_WITHIN_DAYS_B",
        "description": "Modified must be after created, and same day or within one day",
    },
    {
        "col_a": "MODIFIEDON",
        "col_b": "ACTUALDATEOFAVAILABILITY",
        "rule": "MODIFIED_AFTER_ACTUAL",
        "check_type": "A_AFTER_B",
        "description": "Modified date should be after actual date of availability",
    },
]

# --- Similarity Detection --------------------------------------------------------
SIMILARITY_THRESHOLD = 0.6

# --- Error Types (generic, AI-driven) --------------------------------------------
ERROR_TYPES = {
    "MISSING_DATE": "Missing date value (null/empty) in a detected date column",
    "MISSING_DATA": "Non-date column has missing/null value",
    "DATE_ORDER_ERROR": "Date column A should be before/after column B but is not",
    "DATE_MATCH_ERROR": "Two date columns should have matching dates but do not",
    "DATE_PROXIMITY_ERROR": "Two dates are further apart than expected",
    "SIMILAR_COLUMN_MISMATCH": "Two columns with similar data have different values",
}

# Critical non-date columns that should not be empty
CRITICAL_COLUMNS = [
    "SPMSTATUS",
    "TICKETNO",
    "ACTION",
    "STATION",
    "SPMNO",
]

# --- Output File Names -----------------------------------------------------------
CSV_REPORT_FILENAME = "mismatches.csv"
REPORT_FILENAME = "report_final.txt"
EMAIL_FILENAME = "email_final.txt"
SUMMARY_FILENAME = "pipeline_summary.txt"
DRAFT_REPORT_FILENAME = "report_draft.txt"
DRAFT_EMAIL_FILENAME = "email_draft.txt"

# --- Email Template --------------------------------------------------------------
EMAIL_TEMPLATE = """Dear sir/ma'am,

{body}

Regards"""
