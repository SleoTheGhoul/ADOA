"""
report_generator.py -- Error report generation module.

Generates a clean, readable plain-text report with errors grouped by row.
"""

import os
from collections import OrderedDict
from config import OUTPUT_DIR, REPORT_FILENAME, ERROR_TYPES, DATE_COMPARISON_RULES, DATE_COLUMNS

# Fixed column width for tables
COL_W = 58
LINE = "=" * 90
THIN = "-" * 90


def _section(title):
    """Return a formatted section header."""
    return f"\n{'_' * 90}\n\n  {title}\n{'_' * 90}\n"


def generate_report(df, errors, kpis, ai_analysis=None):
    """
    Generate a structured, readable error report with errors grouped by row.
    ai_analysis: optional string from Gemini AI inserted before the row detail section.
    """
    print("\n" + "=" * 80)
    print("GENERATING ERROR REPORT")
    print("=" * 80)

    lines = []

    # ===================== HEADER =====================
    lines.append(LINE)
    lines.append("")
    lines.append("    ADOA  --  ERROR & MISMATCH REPORT")
    lines.append("    SPM Equipment Availability Data Analysis")
    lines.append("")
    lines.append(LINE)

    # ===================== DATA OVERVIEW =====================
    dq = kpis.get("data_quality", {})
    lines.append(_section("1.  DATA OVERVIEW"))
    lines.append(f"    Total Rows           :  {df.shape[0]}")
    lines.append(f"    Total Columns        :  {df.shape[1]}")
    lines.append(f"    Total Cells          :  {dq.get('total_cells', 'N/A')}")
    lines.append(f"    Null Cells           :  {dq.get('null_cells', 'N/A')}")
    lines.append(f"    Data Fill Rate       :  {dq.get('fill_rate_pct', 'N/A')}%")

    avail = kpis.get("availability", {})
    if avail:
        lines.append("")
        lines.append("    --- Availability (date only, time ignored) ---")
        lines.append(f"    Records compared     :  {avail.get('total_records_with_both_dates', 'N/A')}")
        lines.append(f"    Dates matching       :  {avail.get('dates_matching', 'N/A')}")
        lines.append(f"    Dates not matching   :  {avail.get('dates_not_matching', 'N/A')}")
        lines.append(f"    Match percentage     :  {avail.get('match_pct', 'N/A')}%")

    # ===================== COMPARISON RULES =====================
    lines.append(_section("2.  COMPARISON RULES APPLIED"))
    for i, rule in enumerate(DATE_COMPARISON_RULES, 1):
        lines.append(f"    Rule {i}:  {rule['rule']}")
        lines.append(f"             {rule['col_a']}  vs  {rule['col_b']}")
        lines.append(f"             {rule['description']}")
        lines.append("")

    # ===================== MISSING DATA SUMMARY =====================
    missing_summary = kpis.get("missing_data_summary", {})
    date_completeness = kpis.get("date_completeness", {})
    total_rows = df.shape[0]

    COLUMN_EXPLANATIONS = {
        "REASONIFBREAKDOWN": "Root cause of breakdown",
        "TYPEOFMAINTENANCE": "Maintenance category",
        "DETAILSOFMAINTENANCE": "Maintenance specifics",
        "ACTIONTAKEN": "Corrective measures applied",
        "STATION": "Equipment location",
        "SPMNO": "Equipment identifier",
        "CONTROLROOM": "Monitoring station",
        "EQUIPMENT": "Asset being maintained",
        "NULLVOID": "Cancelled/invalid flag",
    }

    lines.append(_section("3.  MISSING DATA SUMMARY  (Full File Scan)"))
    lines.append("")
    lines.append(f"    {'Column':<35s}  {'Missing':>7s} / {'Total':<5s}  {'%':>7s}   What is it?")
    lines.append(f"    {'-'*35}  {'-'*15}  {'-'*7}   {'-'*30}")

    # Date columns
    for col in DATE_COLUMNS:
        dc = date_completeness.get(col, {})
        miss = dc.get("missing", 0)
        if miss > 0:
            pct = round((miss / total_rows) * 100, 1)
            lines.append(f"    {col:<35s}  {miss:>7d} / {total_rows:<5d}  {pct:>6.1f}%   Required date column")

    # Non-date columns
    for col, cnt in sorted(missing_summary.items(), key=lambda x: -x[1]):
        pct = round((cnt / total_rows) * 100, 1)
        explanation = COLUMN_EXPLANATIONS.get(col, "Data field")
        lines.append(f"    {col:<35s}  {cnt:>7d} / {total_rows:<5d}  {pct:>6.1f}%   {explanation}")

    # ===================== ERROR SUMMARY =====================
    breakdown = kpis.get("error_breakdown", {})
    total_errors = sum(breakdown.values())

    lines.append(_section("4.  ERROR SUMMARY"))
    lines.append("")
    lines.append(f"    {'Error Type':<30s}  {'Count':>6s}   Description")
    lines.append(f"    {'-'*30}  {'-'*6}   {'-'*45}")

    for etype, count in sorted(breakdown.items(), key=lambda x: -x[1]):
        desc = ERROR_TYPES.get(etype, "")
        lines.append(f"    {etype:<30s}  {count:>6d}   {desc}")

    lines.append(f"    {'-'*30}  {'-'*6}")
    lines.append(f"    {'TOTAL':<30s}  {total_errors:>6d}")

    # ===================== AI ANALYSIS =====================
    lines.append(_section("5.  AI ANALYSIS  (Gemini-Generated)"))
    if ai_analysis:
        # Indent each line for consistent report style
        for ai_line in ai_analysis.splitlines():
            lines.append(f"    {ai_line}")
    else:
        lines.append("    AI analysis was not available for this run.")
        lines.append("    Check your API key or network connection and re-run the pipeline.")

    # ===================== DETAILED ERRORS BY ROW =====================
    grouped = OrderedDict()
    for err in sorted(errors, key=lambda e: (e.get("row", 0), e.get("column", ""))):
        row = err.get("row", 0)
        if row not in grouped:
            grouped[row] = {
                "ticket": err.get("ticket", "N/A"),
                "id": err.get("id", "N/A"),
                "errors": [],
            }
        grouped[row]["errors"].append(err)

    lines.append(_section(f"6.  DETAILED ERRORS BY ROW  ({len(grouped)} rows, {total_errors} errors)"))

    for row_num, data in grouped.items():
        ticket = data["ticket"]
        record_id = data["id"]
        err_list = data["errors"]

        # Separate errors by type for readability
        date_errors = [e for e in err_list if e["error_type"] in (
            "MISSING_DATE", "START_BEFORE_ENTRY", "DATE_MISMATCH",
            "CREATED_BEFORE_ACTUAL", "CREATED_AFTER_ACTUAL",
            "MODIFIED_BEFORE_CREATED", "MODIFIED_TOO_LATE",
            "MODIFIED_BEFORE_ACTUAL",
        )]
        data_errors = [e for e in err_list if e["error_type"] in ("MISSING_DATA",)]
        other_errors = [e for e in err_list if e not in date_errors and e not in data_errors]

        lines.append("")
        lines.append(f"    +{'-'*84}+")
        lines.append(f"    |  Row {row_num:<4}   ID: {record_id:<10}   Ticket: {ticket:<25}  Errors: {len(err_list):<4} |")
        lines.append(f"    +{'-'*84}+")

        if date_errors:
            lines.append(f"      Date/Comparison Issues ({len(date_errors)}):")
            for e in date_errors:
                col = e.get("column", "")
                etype = e.get("error_type", "")
                expected = str(e.get("expected", ""))
                actual = str(e.get("actual", ""))
                lines.append(f"        * [{etype}]  {col}")
                lines.append(f"          Expected : {expected}")
                lines.append(f"          Actual   : {actual}")

        if data_errors:
            missing_cols = [e.get("column", "") for e in data_errors]
            lines.append(f"      Missing Data ({len(data_errors)}):")
            lines.append(f"        Columns: {', '.join(missing_cols)}")

        if other_errors:
            lines.append(f"      Other Issues ({len(other_errors)}):")
            for e in other_errors:
                col = e.get("column", "")
                etype = e.get("error_type", "")
                lines.append(f"        * [{etype}]  {col}")
                lines.append(f"          {e.get('expected', '')} vs {e.get('actual', '')}")

    # ===================== FOOTER =====================
    lines.append("")
    lines.append(LINE)
    lines.append(f"  END OF REPORT  --  {len(grouped)} rows  |  {total_errors} total errors")
    lines.append(LINE)

    report_text = "\n".join(lines)

    # Save to file
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    filepath = os.path.join(OUTPUT_DIR, REPORT_FILENAME)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(report_text)
    print(f"[REPORT] Report saved to: {filepath}")
    print(f"[REPORT] {len(grouped)} rows with {total_errors} errors")

    return report_text


if __name__ == "__main__":
    from reader import read_excel
    from standardizer import standardize
    from comparator import MismatchDetector

    df = read_excel()
    df, date_cols, parse_errors = standardize(df)
    detector = MismatchDetector(df, date_cols, parse_errors)
    errors, kpis = detector.run_all_checks()
    report = generate_report(df, errors, kpis)
    print("\n" + report)
