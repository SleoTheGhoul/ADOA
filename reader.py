"""
reader.py -- Excel file reader module.

Reads .xls/.xlsx files from the project directory,
loads all sheets, and provides data preview functions.
"""

import os
import glob
import pandas as pd
from config import PROJECT_DIR


def find_excel_file(directory=None):
    """
    Auto-detect the first Excel file (.xlsx or .xls) in the given directory.
    
    Args:
        directory: Path to search. Defaults to PROJECT_DIR.
    
    Returns:
        str: Full path to the Excel file.
    
    Raises:
        FileNotFoundError: If no Excel file is found.
    """
    if directory is None:
        directory = PROJECT_DIR

    patterns = [
        os.path.join(directory, "*.xlsx"),
        os.path.join(directory, "*.xls"),
    ]

    for pattern in patterns:
        files = glob.glob(pattern)
        if files:
            print(f"[READER] Found Excel file: {os.path.basename(files[0])}")
            return files[0]

    raise FileNotFoundError(
        f"No Excel file (.xlsx or .xls) found in: {directory}"
    )


def find_all_excel_files(directory):
    """
    Find ALL Excel files (.xlsx and .xls) in the given directory.

    Args:
        directory: Path to search.

    Returns:
        list: List of full paths to Excel files, sorted alphabetically.
    """
    files = []
    for ext in ("*.xlsx", "*.xls"):
        files.extend(glob.glob(os.path.join(directory, ext)))

    # Deduplicate and sort
    files = sorted(set(files))
    if files:
        print(f"[READER] Found {len(files)} Excel file(s) in: {directory}")
        for f in files:
            print(f"  -> {os.path.basename(f)}")
    else:
        print(f"[READER] No Excel files found in: {directory}")

    return files


def read_excel(file_path=None, sheet_name=0):
    """
    Read an Excel file and return a DataFrame.
    
    Args:
        file_path: Path to the Excel file. Auto-detects if None.
        sheet_name: Sheet name or index to read. Default is first sheet (0).
    
    Returns:
        pd.DataFrame: The loaded data.
    """
    if file_path is None:
        file_path = find_excel_file()

    print(f"[READER] Reading file: {os.path.basename(file_path)}")

    # Determine engine based on extension
    ext = os.path.splitext(file_path)[1].lower()
    engine = "xlrd" if ext == ".xls" else "openpyxl"

    df = pd.read_excel(file_path, sheet_name=sheet_name, engine=engine)

    print(f"[READER] Loaded {df.shape[0]} rows x {df.shape[1]} columns")
    return df


def get_all_sheets(file_path=None):
    """
    Get a list of all sheet names in the Excel file.
    
    Args:
        file_path: Path to the Excel file. Auto-detects if None.
    
    Returns:
        list: Sheet names.
    """
    if file_path is None:
        file_path = find_excel_file()

    ext = os.path.splitext(file_path)[1].lower()
    engine = "xlrd" if ext == ".xls" else "openpyxl"

    xls = pd.ExcelFile(file_path, engine=engine)
    return xls.sheet_names


def read_all_sheets(file_path=None):
    """
    Read all sheets from an Excel file.
    
    Args:
        file_path: Path to the Excel file. Auto-detects if None.
    
    Returns:
        dict: {sheet_name: pd.DataFrame}
    """
    if file_path is None:
        file_path = find_excel_file()

    sheets = get_all_sheets(file_path)
    result = {}

    for sheet in sheets:
        print(f"[READER] Reading sheet: '{sheet}'")
        result[sheet] = read_excel(file_path, sheet_name=sheet)

    return result


def print_data_preview(df, num_rows=5):
    """
    Print a formatted preview of the DataFrame.
    
    Args:
        df: The DataFrame to preview.
        num_rows: Number of rows to show.
    """
    print("\n" + "=" * 80)
    print(f"DATA PREVIEW -- {df.shape[0]} rows x {df.shape[1]} columns")
    print("=" * 80)

    print("\n-- Columns --")
    for i, col in enumerate(df.columns):
        dtype = df[col].dtype
        nulls = df[col].isnull().sum()
        null_pct = (nulls / len(df)) * 100
        print(f"  [{i:2d}] {col:<35s} dtype={str(dtype):<15s} nulls={nulls:3d} ({null_pct:.1f}%)")

    print(f"\n-- First {num_rows} Rows --")
    # Only show a subset of important columns for readability
    important_cols = [
        c for c in df.columns
        if c not in ("EDIT", "NULLANDVOIDTICKETS")
    ]
    display_df = df[important_cols].head(num_rows)
    print(display_df.to_string(max_colwidth=40))

    print(f"\n-- Last 3 Rows --")
    print(df[important_cols].tail(3).to_string(max_colwidth=40))
    print("=" * 80)


def print_column(df, column_name):
    """
    Print all values of a specific column.
    
    Args:
        df: The DataFrame.
        column_name: Column name to print.
    """
    if column_name not in df.columns:
        print(f"[ERROR] Column '{column_name}' not found.")
        print(f"  Available columns: {list(df.columns)}")
        return

    print(f"\n-- Column: {column_name} --")
    print(f"  dtype: {df[column_name].dtype}")
    print(f"  nulls: {df[column_name].isnull().sum()} / {len(df)}")
    print(f"  unique: {df[column_name].nunique()}")
    print()
    for i, val in enumerate(df[column_name]):
        print(f"  Row {i:3d}: {val}")


def print_row(df, row_index):
    """
    Print all values of a specific row.
    
    Args:
        df: The DataFrame.
        row_index: Row index to print.
    """
    if row_index < 0 or row_index >= len(df):
        print(f"[ERROR] Row index {row_index} out of range (0-{len(df)-1}).")
        return

    print(f"\n-- Row {row_index} --")
    row = df.iloc[row_index]
    for col in df.columns:
        print(f"  {col:<35s}: {row[col]}")


if __name__ == "__main__":
    # Quick test
    df = read_excel()
    print_data_preview(df)
