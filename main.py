"""
main.py -- ADOA: Asset Data & Outage Analysis Tool

Entry point that orchestrates the full pipeline.
Supports two modes:
  --auto   : Process the single Excel file in the project root
  --batch  : Process ALL Excel files in the Excels/ folder

Pipeline steps (per file, per sheet):
  1. Read Excel data (all sheets)
  2. Standardize data + auto-detect date columns
  3. AI Column Analysis (suggest comparison rules)
  4. Detect mismatches & compute KPIs
  5. Generate CSV report
  6. AI Analysis (generate prose for report + email)
  7. Generate Final Report (report_final.txt)
  8. Generate Final Email (email_final.txt)
  9. Generate Pipeline Summary
"""

import sys
import os

# Ensure project directory is on path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from reader import read_excel, print_data_preview, print_column, print_row, find_excel_file, find_all_excel_files, get_all_sheets
from standardizer import standardize
from comparator import MismatchDetector, export_csv_report
from ai_engine import generate_ai_outputs, suggest_comparison_rules
from config import OUTPUT_DIR, EXCELS_DIR, REPORT_FILENAME, EMAIL_FILENAME, SUMMARY_FILENAME


# --- Global State (for interactive mode) -----------------------------------------
_df = None
_date_cols = None
_parse_errors = None
_errors = None
_kpis = None
_report_text = None
_email_draft = None
_comparison_rules = None


def _process_sheet(df, sheet_name, file_label, output_dir):
    """
    Process a single sheet (DataFrame) through the full pipeline.
    Returns (success, result_dict) or (False, None) on failure.
    """
    print(f"\n  --- Sheet: '{sheet_name}' ({df.shape[0]} rows x {df.shape[1]} cols) ---")

    # Step 2: Standardize + auto-detect date columns
    print("\n>> STEP 2/9: Standardizing Data & Detecting Date Columns...")
    df, date_cols, parse_errors = standardize(df)

    # Step 3: AI Column Analysis (suggest comparison rules)
    print("\n>> STEP 3/9: AI Column Analysis (Suggesting Comparison Rules)...")
    comparison_rules = suggest_comparison_rules(df, date_cols)

    # Step 4: Detect Mismatches & Compute KPIs
    print("\n>> STEP 4/9: Detecting Mismatches & Computing KPIs...")
    detector = MismatchDetector(df, date_cols, parse_errors, comparison_rules=comparison_rules)
    errors, kpis = detector.run_all_checks()

    # Step 5: CSV Report
    print("\n>> STEP 5/9: Generating CSV Report...")
    csv_path = export_csv_report(errors, output_dir=output_dir)

    # Step 6-8: AI Analysis + Final Report + Final Email
    print("\n>> STEP 6-8/9: Generating AI Analysis, Final Report & Email...")
    ai_results = generate_ai_outputs(
        df, errors, kpis, date_cols,
        comparison_rules=comparison_rules,
        output_dir=output_dir,
    )

    # Step 9: Pipeline Summary
    print("\n>> STEP 9/9: Generating Pipeline Summary...")
    _save_pipeline_summary(df, date_cols, comparison_rules, errors, kpis, output_dir)

    # --- Sheet Summary ---
    print("\n" + "-" * 60)
    print(f"  [{file_label} / {sheet_name}] COMPLETE")
    print(f"  [DATA]  {df.shape[0]} rows x {df.shape[1]} columns")
    print(f"  [DATE]  {len(date_cols)} date columns detected")
    print(f"  [RULE]  {len(comparison_rules)} AI-suggested rules applied")
    print(f"  [WARN]  Errors detected: {len(errors)}")
    print(f"  [KPI]   Data fill rate: {kpis['data_quality']['fill_rate_pct']}%")
    if kpis.get("availability"):
        print(f"  [OK]    Availability date match: {kpis['availability']['match_pct']}%")
    print(f"  [OUT]   Output dir: {output_dir}")
    print("-" * 60)

    return True, {
        "sheet": sheet_name,
        "df": df,
        "date_cols": date_cols,
        "errors": errors,
        "kpis": kpis,
        "comparison_rules": comparison_rules,
        "report_text": ai_results.get("report_full", ""),
        "email_draft": ai_results.get("email_full", ""),
    }


def process_single_file(file_path, output_dir=None):
    """
    Process a single Excel file through the full pipeline.
    Reads ALL sheets — each sheet gets its own analysis and output subfolder.
    Returns (success, result_dict) or (False, None) on failure.
    """
    if output_dir is None:
        output_dir = OUTPUT_DIR

    filename = os.path.basename(file_path)
    file_label = os.path.splitext(filename)[0]

    print("\n" + "+" + "=" * 78 + "+")
    print("|" + f" Processing: {filename} ".center(78) + "|")
    print("+" + "=" * 78 + "+")

    # Step 1: Discover sheets in the Excel file
    print(f"\n>> STEP 1/9: Reading '{filename}'...")
    try:
        sheet_names = get_all_sheets(file_path)
    except Exception as e:
        print(f"\n[ERROR] Failed to read '{filename}': {e}")
        return False, None

    print(f"[READER] Found {len(sheet_names)} sheet(s): {sheet_names}")

    # Process each sheet
    all_sheet_results = []
    last_result = None

    for sheet_idx, sheet_name in enumerate(sheet_names, 1):
        print(f"\n{'~' * 60}")
        print(f"  SHEET {sheet_idx}/{len(sheet_names)}: '{sheet_name}'")
        print(f"{'~' * 60}")

        try:
            df = read_excel(file_path, sheet_name=sheet_name)
        except Exception as e:
            print(f"[ERROR] Failed to read sheet '{sheet_name}': {e}")
            all_sheet_results.append({"sheet": sheet_name, "success": False})
            continue

        # Skip empty sheets
        if df.empty or df.shape[0] == 0:
            print(f"[SKIP] Sheet '{sheet_name}' is empty — skipping.")
            all_sheet_results.append({"sheet": sheet_name, "success": True, "skipped": True})
            continue

        # Determine output directory for this sheet
        if len(sheet_names) == 1:
            # Single sheet — output goes directly to the file's folder
            sheet_output_dir = output_dir
        else:
            # Multiple sheets — each gets a subfolder
            safe_sheet_name = sheet_name.replace(" ", "_").replace("/", "_")
            sheet_output_dir = os.path.join(output_dir, safe_sheet_name)

        success, result = _process_sheet(df, sheet_name, file_label, sheet_output_dir)
        all_sheet_results.append({"sheet": sheet_name, "success": success, "result": result})
        if success and result:
            last_result = result

    # Build combined result for callers
    if last_result:
        combined_result = {
            "file": filename,
            "sheets_processed": len(all_sheet_results),
            "df": last_result["df"],
            "date_cols": last_result["date_cols"],
            "errors": last_result["errors"],
            "kpis": last_result["kpis"],
            "comparison_rules": last_result["comparison_rules"],
            "report_text": last_result["report_text"],
            "email_draft": last_result["email_draft"],
        }
        return True, combined_result

    return False, None


def run_full_pipeline():
    """Execute the pipeline on the single Excel file in the project root."""
    global _df, _date_cols, _parse_errors, _errors, _kpis
    global _report_text, _email_draft, _comparison_rules

    print("\n" + "+" + "=" * 78 + "+")
    print("|" + " ADOA -- Asset Data & Outage Analysis Tool ".center(78) + "|")
    print("+" + "=" * 78 + "+")

    try:
        file_path = find_excel_file()
    except FileNotFoundError as e:
        print(f"\n[FATAL] {e}")
        print("Please place your Excel file (.xlsx or .xls) in the project directory.")
        return False

    success, result = process_single_file(file_path, output_dir=OUTPUT_DIR)
    if success and result:
        _df = result["df"]
        _date_cols = result["date_cols"]
        _errors = result["errors"]
        _kpis = result["kpis"]
        _comparison_rules = result["comparison_rules"]
        _report_text = result["report_text"]
        _email_draft = result["email_draft"]

    return success


def run_batch_pipeline():
    """Process ALL Excel files in the Excels/ folder."""

    print("\n" + "+" + "=" * 78 + "+")
    print("|" + " ADOA -- BATCH MODE ".center(78) + "|")
    print("|" + f" Scanning: {EXCELS_DIR} ".center(78) + "|")
    print("+" + "=" * 78 + "+")

    if not os.path.isdir(EXCELS_DIR):
        print(f"\n[FATAL] Excels directory not found: {EXCELS_DIR}")
        print("Please create an 'Excels' folder in the project directory and add Excel files.")
        return False

    excel_files = find_all_excel_files(EXCELS_DIR)
    if not excel_files:
        print("\n[FATAL] No Excel files found in the Excels/ folder.")
        return False

    print(f"\n{'=' * 60}")
    print(f"  BATCH: {len(excel_files)} file(s) to process")
    print(f"{'=' * 60}")

    results = []
    for i, file_path in enumerate(excel_files, 1):
        filename = os.path.basename(file_path)
        file_label = os.path.splitext(filename)[0]

        # Each file gets its own output subdirectory
        file_output_dir = os.path.join(OUTPUT_DIR, file_label)

        print(f"\n\n{'#' * 78}")
        print(f"  FILE {i}/{len(excel_files)}: {filename}")
        print(f"  Output: output/{file_label}/")
        print(f"{'#' * 78}")

        success, result = process_single_file(file_path, output_dir=file_output_dir)
        results.append({
            "file": filename,
            "success": success,
            "result": result,
        })

    # --- Batch Summary ---
    print("\n\n" + "+" + "=" * 78 + "+")
    print("|" + " BATCH PROCESSING COMPLETE ".center(78) + "|")
    print("+" + "=" * 78 + "+")

    for r in results:
        status = "OK" if r["success"] else "FAILED"
        if r["success"] and r["result"]:
            kpis = r["result"]["kpis"]
            errs = len(r["result"]["errors"])
            fill = kpis["data_quality"]["fill_rate_pct"]
            rules = len(r["result"]["comparison_rules"])
            print(f"  [{status}] {r['file']:<35s}  {errs:>3d} errors  |  {fill}% fill  |  {rules} rules")
        else:
            print(f"  [{status}] {r['file']}")

    succeeded = sum(1 for r in results if r["success"])
    print(f"\n  {succeeded}/{len(results)} files processed successfully")
    print(f"  Output folders in: {OUTPUT_DIR}")

    return succeeded == len(results)


def _save_pipeline_summary(df, date_cols, comparison_rules, errors, kpis, output_dir):
    """Save a pipeline summary to the output directory."""
    os.makedirs(output_dir, exist_ok=True)

    summary_lines = [
        "=" * 70,
        "  ADOA PIPELINE SUMMARY",
        "=" * 70,
        "",
        f"  Dataset:           {df.shape[0]} rows x {df.shape[1]} columns",
        f"  Date Columns:      {len(date_cols)} detected: {', '.join(date_cols)}",
        f"  Comparison Rules:  {len(comparison_rules)} AI-suggested",
        f"  Total Errors:      {len(errors)}",
        f"  Data Fill Rate:    {kpis['data_quality']['fill_rate_pct']}%",
    ]

    if kpis.get("availability"):
        avail = kpis["availability"]
        summary_lines.append(f"  Date Match Rate:   {avail['match_pct']}%")
        summary_lines.append(f"  Dates Matching:    {avail['dates_matching']}")
        summary_lines.append(f"  Dates Mismatched:  {avail['dates_not_matching']}")

    if kpis.get("error_breakdown"):
        summary_lines.append("")
        summary_lines.append("  Error Breakdown:")
        for etype, count in sorted(kpis["error_breakdown"].items(), key=lambda x: -x[1]):
            summary_lines.append(f"    {etype:<35s}: {count}")

    summary_lines.append("")
    summary_lines.append("  AI-Suggested Comparison Rules:")
    for i, rule in enumerate(comparison_rules, 1):
        summary_lines.append(
            f"    {i}. [{rule.get('check_type', 'N/A')}] "
            f"{rule.get('col_a', '')} vs {rule.get('col_b', '')}"
        )
        summary_lines.append(f"       {rule.get('description', '')}")

    summary_lines.append("")
    summary_lines.append("=" * 70)

    filepath = os.path.join(output_dir, SUMMARY_FILENAME)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(summary_lines))
    print(f"[SUMMARY] Pipeline summary saved to: {filepath}")


def show_menu():
    """Show interactive menu."""
    print("\n" + "-" * 50)
    print("  ADOA -- Interactive Menu")
    print("-" * 50)
    print("  1. Run Full Pipeline (single file)")
    print("  2. Run Batch Pipeline (Excels/ folder)")
    print("  3. Preview Raw Data")
    print("  4. Print Specific Column")
    print("  5. Print Specific Row")
    print("  6. Print Report")
    print("  7. Print Email Draft")
    print("  8. Print Error Summary")
    print("  0. Exit")
    print("-" * 50)


def interactive_mode():
    """Run the interactive menu loop."""
    global _df, _date_cols, _parse_errors, _errors, _kpis, _report_text, _email_draft

    while True:
        show_menu()
        choice = input("\n  Enter choice (0-8): ").strip()

        if choice == "1":
            run_full_pipeline()

        elif choice == "2":
            run_batch_pipeline()

        elif choice == "3":
            if _df is None:
                print("\n[INFO] No data loaded. Running reader first...")
                _df = read_excel()
                _df, _date_cols, _parse_errors = standardize(_df)
            print_data_preview(_df)

        elif choice == "4":
            if _df is None:
                print("\n[INFO] No data loaded. Running reader first...")
                _df = read_excel()
                _df, _date_cols, _parse_errors = standardize(_df)
            print(f"\n  Available columns: {list(_df.columns)}")
            col = input("  Enter column name: ").strip().upper()
            print_column(_df, col)

        elif choice == "5":
            if _df is None:
                print("\n[INFO] No data loaded. Running reader first...")
                _df = read_excel()
                _df, _date_cols, _parse_errors = standardize(_df)
            try:
                idx = int(input("  Enter row index (0-based): ").strip())
                print_row(_df, idx)
            except ValueError:
                print("[ERROR] Please enter a valid integer.")

        elif choice == "6":
            if _report_text:
                print("\n" + "=" * 80)
                print("FINAL REPORT")
                print("=" * 80)
                print(_report_text)
            else:
                print("\n[INFO] No report generated yet. Run the pipeline first (option 1 or 2).")

        elif choice == "7":
            if _email_draft:
                print("\n" + "=" * 80)
                print("FINAL EMAIL")
                print("=" * 80)
                print(_email_draft)
            else:
                print("\n[INFO] No email draft generated yet. Run the pipeline first (option 1 or 2).")

        elif choice == "8":
            if _errors is not None:
                print("\n" + "=" * 80)
                print(f"ERROR SUMMARY -- {len(_errors)} errors")
                print("=" * 80)
                if _kpis and "error_breakdown" in _kpis:
                    from config import ERROR_TYPES
                    for etype, count in _kpis["error_breakdown"].items():
                        desc = ERROR_TYPES.get(etype, "")
                        print(f"  {etype:<30s}: {count:4d}  -- {desc}")
                print(f"\n  First 20 errors:")
                for err in _errors[:20]:
                    print(f"    Row {err['row']:3d} | {err['error_type']:<25s} | {err['column']}")
                    print(f"           Expected: {str(err['expected'])[:60]}")
                    print(f"           Actual:   {str(err['actual'])[:60]}")
                    print()
            else:
                print("\n[INFO] No errors detected yet. Run the pipeline first (option 1 or 2).")

        elif choice == "0":
            print("\nGoodbye!")
            break

        else:
            print("\n[ERROR] Invalid choice. Please enter 0-8.")


def main():
    """Entry point."""
    if len(sys.argv) > 1:
        mode = sys.argv[1].lower()

        if mode == "--auto":
            # Batch mode: all files in Excels/
            run_batch_pipeline()

        elif mode == "--batch":
            # Batch mode: all files in Excels/ (alias)
            run_batch_pipeline()

        else:
            print(f"Unknown flag: {sys.argv[1]}")
            print("Usage: python main.py [--auto | --batch]")
            print("  --auto   Process ALL Excel files in the Excels/ folder")
            print("  --batch  Same as --auto")

    else:
        # Interactive mode
        interactive_mode()


if __name__ == "__main__":
    main()
