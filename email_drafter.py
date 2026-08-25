"""
email_drafter.py -- Email draft generation module.

Creates a professional email draft with a paragraph explaining
where issues are arising, plus summary tables of errors and missing data.
"""

import os
from config import OUTPUT_DIR, EMAIL_DRAFT_FILENAME, EMAIL_TEMPLATE, ERROR_TYPES, DATE_COLUMNS

# Fixed column width for all tables
COL_W = 58


def generate_email_draft(errors, kpis):
    """
    Generate an email draft with a summary paragraph and error table.
    """
    print("\n" + "=" * 80)
    print("GENERATING EMAIL DRAFT")
    print("=" * 80)

    dq = kpis.get("data_quality", {})
    avail = kpis.get("availability", {})
    breakdown = kpis.get("error_breakdown", {})
    total_errors = sum(breakdown.values())
    missing_summary = kpis.get("missing_data_summary", {})
    date_completeness = kpis.get("date_completeness", {})
    total_rows = dq.get("total_rows", 48)

    # Identify which columns have the most issues
    column_counts = {}
    for err in errors:
        col = err.get("column", "Unknown")
        column_counts[col] = column_counts.get(col, 0) + 1
    top_columns = sorted(column_counts.items(), key=lambda x: -x[1])[:5]
    top_col_names = ", ".join([c[0] for c in top_columns])

    # Identify most prevalent error types
    top_errors = sorted(breakdown.items(), key=lambda x: -x[1])[:3]
    top_error_names = ", ".join([e[0].replace("_", " ").title() for e in top_errors])

    # --- Build the paragraph ---
    paragraph = (
        f"This email is regarding the automated data quality analysis "
        f"conducted on the SPM Equipment Availability dataset. "
        f"The dataset contains {dq.get('total_rows', 'N/A')} records across "
        f"{dq.get('total_columns', 'N/A')} columns, with an overall data fill rate "
        f"of {dq.get('fill_rate_pct', 'N/A')}%.\n"
        f"\n"
        f"The analysis checked 6 required date columns (ENTRYDATETIME, "
        f"MAINTENANCESTARTDATETIME, EXPECTEDDATEOFAVAILABILITY, "
        f"ACTUALDATEOFAVAILABILITY, CREATEDON, MODIFIEDON) for missing values "
        f"and applied 5 comparison rules to validate data consistency. "
        f"A full file scan was also performed across all columns to identify "
        f"any other missing data.\n"
        f"\n"
        f"A total of {total_errors} errors and mismatches were detected. "
        f"The primary issues are arising in the following areas: {top_error_names}. "
        f"The columns most affected are: {top_col_names}."
    )

    if avail:
        paragraph += (
            f"\n\n"
            f"Regarding expected vs actual availability dates (date only, time ignored), "
            f"{avail.get('match_pct', 'N/A')}% of records have matching dates, "
            f"while {avail.get('dates_not_matching', 0)} records show a date mismatch."
        )

    # Count total missing across all scanned columns
    total_missing_data = sum(missing_summary.values())
    total_missing_dates = sum(
        date_completeness.get(c, {}).get("missing", 0) for c in DATE_COLUMNS
    )
    if total_missing_data > 0 or total_missing_dates > 0:
        paragraph += (
            f"\n\n"
            f"The full file scan found {total_missing_dates} missing date values "
            f"and {total_missing_data} missing non-date values across the dataset. "
            f"The missing data breakdown is provided in the table below."
        )

    paragraph += (
        f"\n\n"
        f"Please find the summary tables below for your reference. "
        f"A detailed CSV report and full error report with row-by-row details "
        f"have also been generated and are available in the output folder."
    )

    # --- Missing Data Table ---
    table_lines = []

    has_missing = False
    for c in DATE_COLUMNS:
        if date_completeness.get(c, {}).get("missing", 0) > 0:
            has_missing = True
            break
    if not has_missing and missing_summary:
        has_missing = True

    if has_missing:
        table_lines.append("")
        table_lines.append("Missing Data Summary (Full File Scan):")
        table_lines.append("")
        table_lines.append(f"  {'Column':<{COL_W}s}  {'Missing':>7s}  {'Total':>5s}  {'% Missing':>9s}")
        table_lines.append(f"  {'-'*COL_W}  {'-'*7}  {'-'*5}  {'-'*9}")

        for col in DATE_COLUMNS:
            dc = date_completeness.get(col, {})
            miss = dc.get("missing", 0)
            if miss > 0:
                pct = round((miss / total_rows) * 100, 1)
                table_lines.append(f"  {col:<{COL_W}s}  {miss:>7d}  {total_rows:>5d}  {pct:>8.1f}%")

        for col, cnt in sorted(missing_summary.items(), key=lambda x: -x[1]):
            pct = round((cnt / total_rows) * 100, 1)
            table_lines.append(f"  {col:<{COL_W}s}  {cnt:>7d}  {total_rows:>5d}  {pct:>8.1f}%")

        table_lines.append("")

    # --- Error summary table ---
    table_lines.append("Error/Mismatch Summary:")
    table_lines.append("")
    table_lines.append(f"  {'Error Type':<{COL_W}s}  {'Count':>6s}  Description")
    table_lines.append(f"  {'-'*COL_W}  {'-'*6}  {'-'*40}")

    for etype, count in sorted(breakdown.items(), key=lambda x: -x[1]):
        desc = ERROR_TYPES.get(etype, "")
        table_lines.append(f"  {etype:<{COL_W}s}  {count:>6d}  {desc}")

    table_lines.append(f"  {'-'*COL_W}  {'-'*6}")
    table_lines.append(f"  {'TOTAL':<{COL_W}s}  {total_errors:>6d}")
    table_lines.append("")

    # --- Top affected columns ---
    table_lines.append("Top Affected Columns:")
    table_lines.append("")
    table_lines.append(f"  {'Column':<{COL_W}s}  {'Errors':>6s}")
    table_lines.append(f"  {'-'*COL_W}  {'-'*6}")
    for col, cnt in top_columns:
        table_lines.append(f"  {col:<{COL_W}s}  {cnt:>6d}")
    table_lines.append("")

    body = paragraph + "\n" + "\n".join(table_lines)
    email_draft = EMAIL_TEMPLATE.format(body=body)

    # Save to file
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    filepath = os.path.join(OUTPUT_DIR, EMAIL_DRAFT_FILENAME)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(email_draft)
    print(f"[EMAIL] Email draft saved to: {filepath}")

    return email_draft


if __name__ == "__main__":
    from reader import read_excel
    from standardizer import standardize
    from comparator import MismatchDetector

    df = read_excel()
    df, date_cols, parse_errors = standardize(df)
    detector = MismatchDetector(df, date_cols, parse_errors)
    errors, kpis = detector.run_all_checks()
    draft = generate_email_draft(errors, kpis)
    print("\n" + draft)
