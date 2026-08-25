"""
standardizer.py -- Data standardization module.

Standardizes column names, auto-detects and parses date columns,
and cleans string values.
"""

import pandas as pd
import numpy as np
from config import DATE_DISPLAY_FORMAT, DATE_PATTERNS


def detect_date_columns(df):
    """
    Auto-detect date columns by dtype and column name patterns.
    Returns a list of column names that are (or should be) datetime.
    """
    date_cols = []
    for col in df.columns:
        # Already datetime dtype -> definitely a date column
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            if col not in date_cols:
                date_cols.append(col)
            continue

        # Check if column name matches any date pattern
        col_lower = col.lower()
        if any(pat in col_lower for pat in DATE_PATTERNS):
            # Try parsing a sample -- if >50% succeed, treat as date column
            sample = df[col].dropna().head(50)
            if len(sample) > 0:
                parsed = pd.to_datetime(sample, errors="coerce", dayfirst=True)
                success_rate = parsed.notna().sum() / len(sample)
                if success_rate > 0.5:
                    if col not in date_cols:
                        date_cols.append(col)

    return date_cols


def standardize_column_names(df):
    """Uppercase, strip whitespace, replace spaces with underscores."""
    original = list(df.columns)
    df.columns = [str(c).strip().upper().replace(" ", "_") for c in df.columns]
    changed = sum(1 for a, b in zip(original, df.columns) if a != b)
    if changed > 0:
        print(f"[STANDARDIZER] Renamed {changed} column(s) to uppercase/cleaned format.")
    else:
        print("[STANDARDIZER] Column names already standardized.")
    return df


def parse_date_columns(df, date_columns):
    """Convert detected date columns to datetime."""
    parse_errors = []
    for col in date_columns:
        if col not in df.columns:
            continue
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            print(f"[STANDARDIZER] '{col}' is already datetime -- OK.")
            continue
        before_nulls = df[col].isnull().sum()
        df[col] = pd.to_datetime(df[col], errors="coerce", dayfirst=True)
        after_nulls = df[col].isnull().sum()
        new_nulls = after_nulls - before_nulls
        if new_nulls > 0:
            print(f"[STANDARDIZER] '{col}': {new_nulls} value(s) could not be parsed as dates.")
            parse_errors.append({"column": col, "failed_count": new_nulls})
        else:
            print(f"[STANDARDIZER] '{col}' parsed to datetime successfully.")
    return df, parse_errors


def standardize_date_format(df, date_columns):
    """Floor datetimes to second precision and standardize display format."""
    for col in date_columns:
        if col not in df.columns:
            continue
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            df[col] = df[col].dt.floor("s")
            print(f"[STANDARDIZER] Standardized '{col}' to format: {DATE_DISPLAY_FORMAT}")
    return df


def strip_string_columns(df, date_columns):
    """Strip whitespace from string columns and convert empty strings to NaN."""
    string_cols = [c for c in df.columns if c not in date_columns and df[c].dtype == "object"]
    for col in string_cols:
        df[col] = df[col].apply(
            lambda x: np.nan if (isinstance(x, str) and x.strip().lower() in ["", "nan", "none", "null"])
            else (x.strip() if isinstance(x, str) else x)
        )
    if string_cols:
        print(f"[STANDARDIZER] Stripped whitespace from {len(string_cols)} string columns.")
    return df


def standardize(df):
    """
    Main standardization entry point.
    Returns: (standardized_df, detected_date_columns, parse_errors)
    """
    print("\n" + "=" * 80)
    print("STANDARDIZING DATA")
    print("=" * 80)

    # Step 1: Clean column names
    df = standardize_column_names(df)

    # Step 2: Auto-detect date columns
    date_columns = detect_date_columns(df)
    print(f"[STANDARDIZER] Auto-detected {len(date_columns)} date column(s): {date_columns}")

    # Step 3: Parse date columns
    df, parse_errors = parse_date_columns(df, date_columns)

    # Step 4: Standardize date formats
    df = standardize_date_format(df, date_columns)

    # Step 5: Clean string columns
    df = strip_string_columns(df, date_columns)

    print(f"\n[STANDARDIZER] Done. Using {len(date_columns)} date columns. {len(parse_errors)} parse errors found.")
    return df, date_columns, parse_errors
