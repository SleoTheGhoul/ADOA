"""
comparator.py -- KPI comparison and mismatch detection module.

Compares date columns using 5 specific rules, detects missing data,
finds similar columns, and exports a consolidated CSV report.
"""

import os
import pandas as pd
import numpy as np
from collections import OrderedDict
from config import (
    DEFAULT_COMPARISON_RULES,
    CRITICAL_COLUMNS,
    ERROR_TYPES,
    SIMILARITY_THRESHOLD,
    ID_PATTERNS,
    OUTPUT_DIR,
    CSV_REPORT_FILENAME,
)


class MismatchDetector:
    """Detects mismatches, missing data, and anomalies in the DataFrame."""

    def __init__(self, df, date_columns, parse_errors=None, comparison_rules=None):
        self.df = df
        self.date_columns = date_columns
        self.parse_errors = parse_errors or []
        # Use provided rules, or filter defaults to columns that exist
        if comparison_rules:
            self.comparison_rules = comparison_rules
        else:
            self.comparison_rules = [
                r for r in DEFAULT_COMPARISON_RULES
                if r["col_a"] in df.columns and r["col_b"] in df.columns
            ]
        self.errors = []
        self.kpis = {}

        # Auto-detect the best ID and ticket columns from this dataset
        self._id_col = self._find_best_column(["id", "equipment_id", "record_id", "spmno", "key"])
        self._ticket_col = self._find_best_column(["ticket", "ticketno", "ticket_no", "ticket_number"])

        if self._id_col:
            print(f"[COMPARATOR] Using '{self._id_col}' as record identifier.")
        if self._ticket_col:
            print(f"[COMPARATOR] Using '{self._ticket_col}' as ticket identifier.")

    def _find_best_column(self, preferred_patterns):
        """
        Auto-detect the best column matching the given patterns.
        Checks exact matches first, then substring matches using ID_PATTERNS.
        Returns the column name or None.
        """
        col_upper = {c.upper(): c for c in self.df.columns}

        # Pass 1: Exact match on preferred names
        for pattern in preferred_patterns:
            if pattern.upper() in col_upper:
                return col_upper[pattern.upper()]

        # Pass 2: Substring match on preferred patterns
        for pattern in preferred_patterns:
            for col_name in self.df.columns:
                if pattern in col_name.lower():
                    return col_name

        # Pass 3: Substring match on generic ID_PATTERNS from config
        for pattern in ID_PATTERNS:
            for col_name in self.df.columns:
                if pattern in col_name.lower() and col_name not in self.date_columns:
                    return col_name

        return None

    def run_all_checks(self):
        """Run all detection checks and return results."""
        print("\n" + "=" * 80)
        print("RUNNING MISMATCH DETECTION & KPI ANALYSIS")
        print("=" * 80)

        self._check_missing_dates()
        self._check_date_comparisons()
        self._check_all_missing_data()
        self._check_similar_columns()
        self._compute_kpis()

        print(f"\n[COMPARATOR] Total errors/mismatches detected: {len(self.errors)}")
        return self.errors, self.kpis

    # -----------------------------------------------------------------
    # Rule: Missing dates in the 6 required date columns
    # -----------------------------------------------------------------
    def _check_missing_dates(self):
        """Check for missing/null values in the 6 required date columns only."""
        print("\n-- Checking Missing Dates (6 required columns) --")
        count = 0
        for col in self.date_columns:
            if col not in self.df.columns:
                continue
            null_mask = self.df[col].isnull()
            null_rows = self.df.index[null_mask].tolist()
            for row_idx in null_rows:
                self.errors.append({
                    "row": row_idx + 2,
                    "column": col,
                    "error_type": "MISSING_DATE",
                    "expected": "A valid date",
                    "actual": "NULL / Empty",
                    "description": f"Missing date in '{col}' at row {row_idx + 2}",
                    "ticket": self._get_ticket(row_idx),
                    "id": self._get_id(row_idx),
                })
                count += 1
        print(f"  Found {count} missing date values across {len(self.date_columns)} columns.")

    # -----------------------------------------------------------------
    # 5 Date Comparison Rules
    # -----------------------------------------------------------------
    def _check_date_comparisons(self):
        """Run all 5 date comparison rules."""
        print("\n-- Running Date Comparison Rules --")

        for rule_def in self.comparison_rules:
            col_a = rule_def["col_a"]
            col_b = rule_def["col_b"]
            rule = rule_def["rule"]
            desc = rule_def["description"]

            if col_a not in self.df.columns or col_b not in self.df.columns:
                print(f"  [!] Skipping rule '{rule}': column(s) not found.")
                continue

            print(f"  Rule: {rule}")
            print(f"    {col_a} vs {col_b}")
            mismatch_count = 0

            for idx in range(len(self.df)):
                val_a = self.df[col_a].iloc[idx]
                val_b = self.df[col_b].iloc[idx]

                # Skip if either is null
                if pd.isna(val_a) or pd.isna(val_b):
                    continue

                error = self._apply_rule(rule, col_a, col_b, val_a, val_b, idx)
                if error:
                    self.errors.append(error)
                    mismatch_count += 1

            print(f"    -> {mismatch_count} issues found.")

    def _apply_rule(self, rule, col_a, col_b, val_a, val_b, idx):
        """
        Apply a comparison rule using generic check_type dispatch.
        All rules are AI-driven — no hardcoded column-specific logic.
        Returns an error dict or None.
        """
        row_num = idx + 2
        ticket = self._get_ticket(idx)
        record_id = self._get_id(idx)

        # Look up the check_type from the rule definition
        check_type = None
        description = ""
        for rule_def in self.comparison_rules:
            if rule_def["rule"] == rule:
                check_type = rule_def.get("check_type")
                description = rule_def.get("description", "")
                break

        if not check_type:
            return None

        # --- A_BEFORE_B: col_a should be chronologically before col_b ---
        if check_type == "A_BEFORE_B":
            if val_a > val_b:
                return {
                    "row": row_num,
                    "column": f"{col_a} vs {col_b}",
                    "error_type": "DATE_ORDER_ERROR",
                    "expected": f"{col_a} should be before {col_b}",
                    "actual": f"{col_a}={val_a}, {col_b}={val_b}",
                    "description": description or f"{col_a} is after {col_b}",
                    "ticket": ticket,
                    "id": record_id,
                }

        # --- A_AFTER_B: col_a should be chronologically after col_b ---
        elif check_type == "A_AFTER_B":
            if val_a < val_b:
                return {
                    "row": row_num,
                    "column": f"{col_a} vs {col_b}",
                    "error_type": "DATE_ORDER_ERROR",
                    "expected": f"{col_a} should be after {col_b}",
                    "actual": f"{col_a}={val_a}, {col_b}={val_b}",
                    "description": description or f"{col_a} is before {col_b}",
                    "ticket": ticket,
                    "id": record_id,
                }

        # --- A_EQUALS_B_DATE: dates should match (time ignored) ---
        elif check_type == "A_EQUALS_B_DATE":
            date_a = val_a.date() if hasattr(val_a, 'date') else val_a
            date_b = val_b.date() if hasattr(val_b, 'date') else val_b
            if date_a != date_b:
                return {
                    "row": row_num,
                    "column": f"{col_a} vs {col_b}",
                    "error_type": "DATE_MATCH_ERROR",
                    "expected": f"{col_a} date should equal {col_b} date",
                    "actual": f"{col_a}={date_a}, {col_b}={date_b}",
                    "description": description or "Dates do not match (time ignored)",
                    "ticket": ticket,
                    "id": record_id,
                }

        # --- A_WITHIN_DAYS_B: dates should be within N days of each other ---
        elif check_type == "A_WITHIN_DAYS_B":
            diff_days = abs((val_a - val_b).total_seconds()) / 86400
            if diff_days > 1.0:
                return {
                    "row": row_num,
                    "column": f"{col_a} vs {col_b}",
                    "error_type": "DATE_PROXIMITY_ERROR",
                    "expected": f"{col_a} within 1 day of {col_b}",
                    "actual": f"{col_a}={val_a}, {col_b}={val_b} ({diff_days:.1f} days apart)",
                    "description": description or f"Dates are {diff_days:.1f} days apart",
                    "ticket": ticket,
                    "id": record_id,
                }

        # --- A_BEFORE_OR_EQUAL_B: col_a <= col_b ---
        elif check_type == "A_BEFORE_OR_EQUAL_B":
            if val_a > val_b:
                return {
                    "row": row_num,
                    "column": f"{col_a} vs {col_b}",
                    "error_type": "DATE_ORDER_ERROR",
                    "expected": f"{col_a} should be before or equal to {col_b}",
                    "actual": f"{col_a}={val_a}, {col_b}={val_b}",
                    "description": description or f"{col_a} is after {col_b}",
                    "ticket": ticket,
                    "id": record_id,
                }

        # --- A_AFTER_OR_EQUAL_B: col_a >= col_b ---
        elif check_type == "A_AFTER_OR_EQUAL_B":
            if val_a < val_b:
                return {
                    "row": row_num,
                    "column": f"{col_a} vs {col_b}",
                    "error_type": "DATE_ORDER_ERROR",
                    "expected": f"{col_a} should be after or equal to {col_b}",
                    "actual": f"{col_a}={val_a}, {col_b}={val_b}",
                    "description": description or f"{col_a} is before {col_b}",
                    "ticket": ticket,
                    "id": record_id,
                }

        return None


    # -----------------------------------------------------------------
    # Full file scan -- check ALL columns for missing data
    # -----------------------------------------------------------------
    def _check_all_missing_data(self):
        """Scan every column in the file for missing/null values."""
        print("\n-- Full File Scan: Checking ALL Columns for Missing Data --")

        # Columns already checked by _check_missing_dates (skip duplicates)
        skip_cols = set(self.date_columns)

        # Explanation for why each column matters
        COLUMN_EXPLANATIONS = {
            "SPMSTATUS": "SPM status indicates current state of the ticket",
            "TICKETNO": "Ticket number is the primary identifier for tracking",
            "ACTION": "Action describes what maintenance was performed",
            "STATION": "Station identifies the location of the equipment",
            "SPMNO": "SPM number uniquely identifies the equipment",
            "REASONIFBREAKDOWN": "Reason for breakdown explains the root cause",
            "TYPEOFMAINTENANCE": "Type of maintenance categorizes the work done",
            "DETAILSOFMAINTENANCE": "Details provide specifics of maintenance performed",
            "ACTIONTAKEN": "Action taken describes the corrective measures applied",
            "CONTROLROOM": "Control room identifies the monitoring station",
            "EQUIPMENT": "Equipment identifies the specific asset maintained",
            "NULLVOID": "Null/void flag indicates cancelled or invalid tickets",
            "MODIFIEDBY": "Modified by tracks who last updated the record",
            "HOSTADDRESS": "Host address identifies the system origin",
            "STATUS": "Status indicates current record state",
            "ID": "Record ID is the unique database identifier",
        }

        total_missing = 0
        col_summary = {}

        for col in self.df.columns:
            if col in skip_cols:
                continue

            null_mask = self.df[col].isnull()
            null_count = null_mask.sum()

            if null_count == 0:
                continue

            col_summary[col] = null_count
            explanation = COLUMN_EXPLANATIONS.get(col, f"Data field '{col}'")

            null_rows = self.df.index[null_mask].tolist()
            for row_idx in null_rows:
                self.errors.append({
                    "row": row_idx + 2,
                    "column": col,
                    "error_type": "MISSING_DATA",
                    "expected": "A value",
                    "actual": "NULL / Empty",
                    "description": f"{explanation} -- missing at row {row_idx + 2}",
                    "ticket": self._get_ticket(row_idx),
                    "id": self._get_id(row_idx),
                })
                total_missing += 1

        print(f"  Found {total_missing} missing values across {len(col_summary)} columns:")
        for col, cnt in sorted(col_summary.items(), key=lambda x: -x[1]):
            pct = round((cnt / len(self.df)) * 100, 1)
            print(f"    {col:<40s}: {cnt:>3d} / {len(self.df)}  ({pct}% missing)")

        # Store for report/email use
        self.missing_data_summary = col_summary

    # -----------------------------------------------------------------
    # Similar column detection
    # -----------------------------------------------------------------
    def _check_similar_columns(self):
        """Find pairs of columns with similar data and flag mismatches."""
        print("\n-- Checking Similar Columns --")
        cols = [c for c in self.df.columns if c not in ("EDIT", "NULLANDVOIDTICKETS")]
        checked = set()
        similar_pairs = []

        # Build set of columns already in comparison rules
        rule_cols = set()
        for r in self.comparison_rules:
            rule_cols.add((r["col_a"], r["col_b"]))
            rule_cols.add((r["col_b"], r["col_a"]))

        for i, col_a in enumerate(cols):
            for j, col_b in enumerate(cols):
                if i >= j:
                    continue
                pair_key = (col_a, col_b)
                if pair_key in checked:
                    continue
                checked.add(pair_key)

                if self.df[col_a].dtype != self.df[col_b].dtype:
                    continue

                if pair_key in rule_cols or (col_b, col_a) in rule_cols:
                    continue

                both_valid = self.df[col_a].notna() & self.df[col_b].notna()
                if both_valid.sum() == 0:
                    continue

                matching = (self.df.loc[both_valid, col_a] == self.df.loc[both_valid, col_b]).sum()
                similarity = matching / both_valid.sum()

                if similarity >= SIMILARITY_THRESHOLD and similarity < 1.0:
                    similar_pairs.append((col_a, col_b, similarity))
                    mismatch_mask = both_valid & (self.df[col_a] != self.df[col_b])
                    mismatch_rows = self.df.index[mismatch_mask].tolist()
                    for row_idx in mismatch_rows:
                        self.errors.append({
                            "row": row_idx + 2,
                            "column": f"{col_a} vs {col_b}",
                            "error_type": "SIMILAR_COLUMN_MISMATCH",
                            "expected": str(self.df[col_a].iloc[row_idx]),
                            "actual": str(self.df[col_b].iloc[row_idx]),
                            "description": f"Similar columns ({similarity:.0%} match) have different values",
                            "ticket": self._get_ticket(row_idx),
                            "id": self._get_id(row_idx),
                        })

        if similar_pairs:
            print(f"  Found {len(similar_pairs)} similar column pairs:")
            for a, b, sim in similar_pairs:
                print(f"    {a} <-> {b} ({sim:.0%} similar)")
        else:
            print("  No similar column pairs detected.")

    # -----------------------------------------------------------------
    # KPI computation
    # -----------------------------------------------------------------
    def _compute_kpis(self):
        """Compute KPIs from the data."""
        print("\n-- Computing KPIs --")

        # 1. Date completeness per date column
        date_completeness = {}
        for col in self.date_columns:
            if col not in self.df.columns:
                continue
            total = len(self.df)
            valid = self.df[col].notna().sum()
            date_completeness[col] = {
                "total": total,
                "valid": int(valid),
                "missing": int(total - valid),
                "completeness_pct": round((valid / total) * 100, 1),
            }

        # 2. Availability KPI (expected vs actual — date only)
        exp_col = "EXPECTEDDATEOFAVAILABILITY"
        act_col = "ACTUALDATEOFAVAILABILITY"
        availability_kpi = {}
        if exp_col in self.df.columns and act_col in self.df.columns:
            both_valid = self.df[exp_col].notna() & self.df[act_col].notna()
            if both_valid.sum() > 0:
                exp_dates = self.df.loc[both_valid, exp_col].dt.date
                act_dates = self.df.loc[both_valid, act_col].dt.date
                matching = (exp_dates == act_dates).sum()
                not_matching = (exp_dates != act_dates).sum()

                availability_kpi = {
                    "total_records_with_both_dates": int(both_valid.sum()),
                    "dates_matching": int(matching),
                    "dates_not_matching": int(not_matching),
                    "match_pct": round((matching / both_valid.sum()) * 100, 1),
                }

        # 3. Overall data quality
        total_cells = self.df.shape[0] * self.df.shape[1]
        null_cells = int(self.df.isnull().sum().sum())
        data_quality = {
            "total_rows": self.df.shape[0],
            "total_columns": self.df.shape[1],
            "total_cells": total_cells,
            "null_cells": null_cells,
            "fill_rate_pct": round(((total_cells - null_cells) / total_cells) * 100, 1),
        }

        # 4. Error breakdown by type
        error_breakdown = {}
        for err in self.errors:
            etype = err["error_type"]
            error_breakdown[etype] = error_breakdown.get(etype, 0) + 1

        # 5. Status distribution
        status_dist = {}
        if "SPMSTATUS" in self.df.columns:
            status_dist = self.df["SPMSTATUS"].value_counts().to_dict()

        self.kpis = {
            "date_completeness": date_completeness,
            "availability": availability_kpi,
            "data_quality": data_quality,
            "error_breakdown": error_breakdown,
            "status_distribution": status_dist,
            "missing_data_summary": getattr(self, "missing_data_summary", {}),
        }

        # Print summary
        print(f"  Data Quality: {data_quality['fill_rate_pct']}% fill rate")
        print(f"  Total errors: {len(self.errors)}")
        for etype, cnt in error_breakdown.items():
            print(f"    {etype}: {cnt}")
        if availability_kpi:
            print(f"  Availability date match: {availability_kpi['match_pct']}%")

    # -----------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------
    def _get_ticket(self, row_idx):
        if self._ticket_col and row_idx < len(self.df):
            return str(self.df[self._ticket_col].iloc[row_idx])
        return "N/A"

    def _get_id(self, row_idx):
        if self._id_col and row_idx < len(self.df):
            return str(self.df[self._id_col].iloc[row_idx])
        return "N/A"


# =====================================================================
# CSV Export (grouped by row)
# =====================================================================
def export_csv_report(errors, output_dir=None):
    """
    Export all errors to a CSV file, grouped by row number.
    Each row appears once with all its errors consolidated.
    """
    if output_dir is None:
        output_dir = OUTPUT_DIR

    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, CSV_REPORT_FILENAME)

    if not errors:
        print("[COMPARATOR] No errors to export.")
        df = pd.DataFrame(columns=[
            "row", "id", "ticket", "error_count", "columns_affected", "error_types", "details"
        ])
    else:
        grouped = OrderedDict()
        for err in sorted(errors, key=lambda e: e.get("row", 0)):
            row = err.get("row", 0)
            if row not in grouped:
                grouped[row] = {
                    "row": row,
                    "id": err.get("id", "N/A"),
                    "ticket": err.get("ticket", "N/A"),
                    "columns": [],
                    "error_types": [],
                    "details": [],
                }
            grouped[row]["columns"].append(str(err.get("column", "")))
            grouped[row]["error_types"].append(str(err.get("error_type", "")))
            detail = f"{err.get('column','')}: {err.get('error_type','')} (expected={err.get('expected','')}, actual={err.get('actual','')})"
            grouped[row]["details"].append(detail)

        rows = []
        for row_num, data in grouped.items():
            rows.append({
                "row": data["row"],
                "id": data["id"],
                "ticket": data["ticket"],
                "error_count": len(data["columns"]),
                "columns_affected": " | ".join(data["columns"]),
                "error_types": " | ".join(data["error_types"]),
                "details": " | ".join(data["details"]),
            })
        df = pd.DataFrame(rows)

    df.to_csv(filepath, index=False)
    print(f"\n[COMPARATOR] CSV report saved to: {filepath}")
    print(f"  Total rows: {len(df)} (consolidated from {len(errors)} errors)")
    return filepath


if __name__ == "__main__":
    from reader import read_excel
    from standardizer import standardize

    df = read_excel()
    df, date_cols, parse_errors = standardize(df)

    detector = MismatchDetector(df, date_cols, parse_errors)
    errors, kpis = detector.run_all_checks()
    csv_path = export_csv_report(errors)

    print(f"\nKPIs: {kpis}")
