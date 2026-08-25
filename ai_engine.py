"""
ai_engine.py -- Gemini AI integration for ADOA.

Builds structured prompts from error data and KPIs,
calls the Gemini API with retry logic, and generates:
  - Executive summary and anomaly analysis
  - Root cause hypotheses
  - Investigation steps
  - Recommendations
  - Management email body

Also handles:
  - Dynamic column comparison rule suggestion via AI
  - Full report and email assembly with data tables
  - Fallback to defaults when API is unavailable

Falls back to plain-text defaults if the API is unavailable.
"""

import os
import json
import time
from collections import OrderedDict
from config import (
    GEMINI_API_KEYS, GEMINI_MODEL, OUTPUT_DIR,
    REPORT_FILENAME, EMAIL_FILENAME,
    DEFAULT_COMPARISON_RULES, ERROR_TYPES,
)

# Per-key retries before moving to next key
RETRIES_PER_KEY = 2
RETRY_WAIT_SECONDS = 5

# Table formatting
COL_W = 58
LINE = "=" * 90
THIN = "_" * 90


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _call_gemini(prompt, label=""):
    """
    Call Gemini API with multi-key fallback.
    Tries each API key in GEMINI_API_KEYS with retries before moving to the next.
    Flow: Key1 (2 tries) -> Key2 (2 tries) -> Key3 (2 tries) -> Key4 (2 tries) -> fail
    Returns (text, success_bool).
    """
    if not GEMINI_API_KEYS:
        print(f"[AI] No API keys configured.")
        return None, False

    try:
        from google import genai
    except ImportError:
        print("[AI] google-genai not installed. Run: pip install google-genai")
        return None, False

    total_keys = len(GEMINI_API_KEYS)

    for key_idx, api_key in enumerate(GEMINI_API_KEYS, 1):
        key_label = f"Key {key_idx}/{total_keys}"
        client = genai.Client(api_key=api_key)

        for attempt in range(RETRIES_PER_KEY):
            try:
                print(f"[AI] {label} | {key_label}, attempt {attempt + 1}/{RETRIES_PER_KEY}...")
                response = client.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=prompt,
                )
                text = response.text.strip()
                print(f"[AI] {label} generated successfully using {key_label}.")
                return text, True

            except Exception as e:
                err = str(e)
                if "429" in err or "RESOURCE_EXHAUSTED" in err:
                    if attempt < RETRIES_PER_KEY - 1:
                        print(f"[AI] {key_label} rate limited. Waiting {RETRY_WAIT_SECONDS}s before retry...")
                        time.sleep(RETRY_WAIT_SECONDS)
                    else:
                        print(f"[AI] {key_label} quota exhausted. Moving to next key...")
                        break
                elif "401" in err or "403" in err or "INVALID" in err or "PERMISSION" in err:
                    print(f"[AI] {key_label} is invalid or unauthorized. Moving to next key...")
                    break
                else:
                    print(f"[AI] {key_label} error: {e}")
                    if attempt < RETRIES_PER_KEY - 1:
                        print(f"[AI] Retrying in {RETRY_WAIT_SECONDS}s...")
                        time.sleep(RETRY_WAIT_SECONDS)
                    else:
                        print(f"[AI] {key_label} failed. Moving to next key...")
                        break

    print(f"[AI] All {total_keys} API keys exhausted. Using fallback.")
    return None, False


# ---------------------------------------------------------------------------
# Dynamic rule suggestion
# ---------------------------------------------------------------------------

def suggest_comparison_rules(df, date_columns):
    """
    Ask Gemini to suggest comparison rules based on ALL columns in the data.
    The AI always gets consulted — even if 0 date columns were detected.
    Falls back to DEFAULT_COMPARISON_RULES (filtered to existing columns) if AI fails.

    Returns: list of rule dicts with keys: col_a, col_b, rule, check_type, description
    """
    print("\n" + "-" * 60)
    print("AI COLUMN ANALYSIS -- Suggesting comparison rules")
    print("-" * 60)

    all_cols = list(df.columns)

    # Include sample data for context (date cols if any, otherwise first 5 cols)
    sample_data = ""
    try:
        preview_cols = date_columns if date_columns else all_cols[:5]
        sample = df[preview_cols].head(3).to_string()
        sample_data = f"\nSample data (first 3 rows):\n{sample}\n"
    except Exception:
        pass

    # Build prompt — different wording depending on whether date columns exist
    if date_columns and len(date_columns) >= 2:
        col_guidance = f"""Date columns detected: {date_columns}
All columns: {all_cols}
{sample_data}
Suggest 3-10 comparison rules as a JSON array. Each rule must have:
- "col_a": first date column name (must exist in the dataset)
- "col_b": second date column name (must exist in the dataset)
- "check_type": one of "A_BEFORE_B", "A_AFTER_B", "A_EQUALS_B_DATE", "A_WITHIN_DAYS_B", "A_BEFORE_OR_EQUAL_B", "A_AFTER_OR_EQUAL_B"
- "rule": a short UPPER_SNAKE_CASE name for the rule
- "description": one sentence explaining what the rule checks

Focus on logical business relationships between the date columns.
Return ONLY the JSON array, no other text."""

    elif date_columns and len(date_columns) == 1:
        col_guidance = f"""Only 1 date column was detected: {date_columns}
All columns in the dataset: {all_cols}
{sample_data}
Look at ALL columns in this dataset. Even with only one date column, suggest 1-5 comparison rules
if you see any logical relationships. For example, if a date column can be compared against other
fields that might contain dates, IDs, or statuses.

Each rule in the JSON array must have:
- "col_a": first column name (must exist in the dataset)
- "col_b": second column name (must exist in the dataset)
- "check_type": one of "A_BEFORE_B", "A_AFTER_B", "A_EQUALS_B_DATE", "A_WITHIN_DAYS_B", "A_BEFORE_OR_EQUAL_B", "A_AFTER_OR_EQUAL_B"
- "rule": a short UPPER_SNAKE_CASE name for the rule
- "description": one sentence explaining what the rule checks

If no meaningful date comparisons can be made, return an empty JSON array: []
Return ONLY the JSON array, no other text."""

    else:
        col_guidance = f"""No date columns were auto-detected in this dataset.
All columns: {all_cols}
{sample_data}
Look at all the columns above. Some may contain dates that were not auto-detected.
Suggest 0-5 comparison rules if you see any columns that appear to contain dates,
timestamps, or sequential IDs that could be compared.

Each rule in the JSON array must have:
- "col_a": first column name (must exist in the dataset)
- "col_b": second column name (must exist in the dataset)
- "check_type": one of "A_BEFORE_B", "A_AFTER_B", "A_EQUALS_B_DATE", "A_WITHIN_DAYS_B", "A_BEFORE_OR_EQUAL_B", "A_AFTER_OR_EQUAL_B"
- "rule": a short UPPER_SNAKE_CASE name for the rule
- "description": one sentence explaining what the rule checks

If no meaningful comparisons can be made, return an empty JSON array: []
Return ONLY the JSON array, no other text."""

    prompt = f"Given these columns from a dataset, suggest comparison rules.\n\n{col_guidance}"

    response_text, success = _call_gemini(prompt, label="Column Analysis")

    if success and response_text:
        try:
            # Parse JSON from response (handle markdown code blocks)
            json_text = response_text.strip()
            if json_text.startswith("```"):
                json_text = json_text.split("\n", 1)[1]
                json_text = json_text.rsplit("```", 1)[0]
            rules = json.loads(json_text)

            # Validate rules — columns must exist in the dataframe
            valid_check_types = (
                "A_BEFORE_B", "A_AFTER_B", "A_EQUALS_B_DATE",
                "A_WITHIN_DAYS_B", "A_BEFORE_OR_EQUAL_B", "A_AFTER_OR_EQUAL_B",
            )
            valid_rules = []
            for r in rules:
                if (r.get("col_a") in all_cols and
                    r.get("col_b") in all_cols and
                    r.get("check_type") in valid_check_types and
                    r.get("rule") and r.get("description")):
                    valid_rules.append(r)

            if valid_rules:
                print(f"[AI] Suggested {len(valid_rules)} comparison rules:")
                for r in valid_rules:
                    print(f"  {r['rule']}: {r['col_a']} vs {r['col_b']} ({r['check_type']})")
                return valid_rules
            else:
                print("[AI] AI returned no applicable rules for this dataset.")
                if not date_columns:
                    print("[AI] No date columns detected — skipping date comparison rules.")
                    return []
        except (json.JSONDecodeError, TypeError, KeyError) as e:
            print(f"[AI] Could not parse rule suggestions: {e}. Using defaults.")

    return _filter_default_rules(df)


def _filter_default_rules(df):
    """Return DEFAULT_COMPARISON_RULES filtered to columns that exist in the DataFrame."""
    filtered = [
        r for r in DEFAULT_COMPARISON_RULES
        if r["col_a"] in df.columns and r["col_b"] in df.columns
    ]
    if filtered:
        print(f"[AI] Using {len(filtered)} default rules (filtered to existing columns).")
    else:
        print("[AI] No default rules match the columns in this file.")
    return filtered


# ---------------------------------------------------------------------------
# Year distribution builder (for trend analysis)
# ---------------------------------------------------------------------------

def _build_year_distribution(df, errors, date_columns):
    """
    Build year-wise distribution of records and errors.
    Uses the first viable date column to determine the year of each row.
    Returns a list of formatted lines, or empty list if no date data.
    """
    import pandas as pd

    # Find the best date column (one with most non-null values)
    best_col = None
    best_count = 0
    for col in date_columns:
        if col in df.columns and pd.api.types.is_datetime64_any_dtype(df[col]):
            valid = df[col].notna().sum()
            if valid > best_count:
                best_count = valid
                best_col = col

    if not best_col or best_count == 0:
        return []

    # Count records per year
    years = df[best_col].dropna().dt.year
    year_record_counts = years.value_counts().sort_index().to_dict()

    if len(year_record_counts) < 1:
        return []

    # Count errors per year (map row number -> year)
    row_to_year = {}
    for idx in range(len(df)):
        val = df[best_col].iloc[idx]
        if pd.notna(val):
            row_to_year[idx + 2] = val.year  # row numbers are 1-indexed + header

    year_error_counts = {}
    for err in errors:
        row = err.get("row", 0)
        year = row_to_year.get(row)
        if year:
            year_error_counts[year] = year_error_counts.get(year, 0) + 1

    # Format
    lines = [f"(Based on: {best_col})"]
    lines.append(f"  {'Year':<8} {'Records':<10} {'Errors':<10} {'Errors/Record':<15}")
    lines.append(f"  {'----':<8} {'-------':<10} {'------':<10} {'-------------':<15}")
    for year in sorted(year_record_counts.keys()):
        recs = year_record_counts[year]
        errs = year_error_counts.get(year, 0)
        rate = round(errs / recs, 1) if recs > 0 else 0
        lines.append(f"  {year:<8} {recs:<10} {errs:<10} {rate:<15}")

    return lines


# ---------------------------------------------------------------------------
# Data summary builder (for AI prompts)
# ---------------------------------------------------------------------------

def _build_data_summary(df, errors, kpis, date_columns):
    """
    Build a lean, structured data summary for the AI prompt.
    Deliberately minimal to stay within free-tier token limits.
    """
    dq = kpis.get("data_quality", {})
    avail = kpis.get("availability", {})
    breakdown = kpis.get("error_breakdown", {})
    missing_summary = kpis.get("missing_data_summary", {})
    date_completeness = kpis.get("date_completeness", {})
    total_rows = df.shape[0]
    total_errors = sum(breakdown.values())

    lines = []

    # --- Dataset KPIs ---
    lines.append("DATASET OVERVIEW:")
    lines.append(f"  Rows={total_rows} | Columns={df.shape[1]} | Fill Rate={dq.get('fill_rate_pct','N/A')}% | Null Cells={dq.get('null_cells','N/A')}")
    if avail:
        lines.append(
            f"  Availability Date Match={avail.get('match_pct','N/A')}% "
            f"({avail.get('dates_matching',0)} match / {avail.get('dates_not_matching',0)} mismatch "
            f"of {avail.get('total_records_with_both_dates',0)} comparable records)"
        )
    lines.append("")

    # --- Error counts ---
    lines.append(f"ERROR COUNTS ({total_errors} total):")
    for etype, count in sorted(breakdown.items(), key=lambda x: -x[1]):
        pct = round((count / total_errors) * 100, 1) if total_errors else 0
        lines.append(f"  {etype}: {count} ({pct}%)")
    lines.append("")

    # --- Missing data ---
    lines.append("MISSING DATA (column: missing/total %):")
    for col in date_columns:
        dc = date_completeness.get(col, {})
        miss = dc.get("missing", 0)
        if miss > 0:
            pct = round((miss / total_rows) * 100, 1)
            lines.append(f"  {col}: {miss}/{total_rows} ({pct}%) [date]")
    for col, cnt in sorted(missing_summary.items(), key=lambda x: -x[1]):
        pct = round((cnt / total_rows) * 100, 1)
        lines.append(f"  {col}: {cnt}/{total_rows} ({pct}%)")
    lines.append("")

    # --- Per-row summary: top 15 worst rows ---
    grouped = OrderedDict()
    for err in sorted(errors, key=lambda e: e.get("row", 0)):
        row = err.get("row", 0)
        if row not in grouped:
            grouped[row] = {
                "id": err.get("id", "N/A"),
                "ticket": err.get("ticket", "N/A"),
                "etypes": [],
                "missing_cols": [],
            }
        if err["error_type"] == "MISSING_DATA":
            grouped[row]["missing_cols"].append(err.get("column", ""))
        else:
            grouped[row]["etypes"].append(err["error_type"])

    sorted_rows = sorted(
        grouped.items(),
        key=lambda x: len(x[1]["etypes"]) + len(x[1]["missing_cols"]),
        reverse=True,
    )
    top_rows = sorted_rows[:15]
    remaining = sorted_rows[15:]

    lines.append(f"TOP 15 WORST ROWS (of {len(grouped)} total affected rows):")
    for row_num, data in top_rows:
        total_row_errs = len(data["etypes"]) + len(data["missing_cols"])
        parts = []
        if data["etypes"]:
            unique_etypes = list(dict.fromkeys(data["etypes"]))
            parts.append("Errors:[" + ",".join(unique_etypes) + "]")
        if data["missing_cols"]:
            parts.append("Missing:[" + ",".join(data["missing_cols"]) + "]")
        lines.append(
            f"  Row {row_num} | ID:{data['id']} | Ticket:{data['ticket']} "
            f"| TotalErrors:{total_row_errs} | {' | '.join(parts)}"
        )

    if remaining:
        lines.append(
            f"  ...plus {len(remaining)} more rows with smaller error counts "
            f"(1-3 errors each, mostly MISSING_DATA)."
        )

    # --- Year-wise distribution ---
    year_dist = _build_year_distribution(df, errors, date_columns)
    if year_dist:
        lines.append("")
        lines.append("YEAR-WISE DISTRIBUTION:")
        for year_line in year_dist:
            lines.append(f"  {year_line}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

def _build_report_prompt(data_summary, kpis):
    """Build a richer report prompt with 6 analysis sections."""
    dq = kpis.get("data_quality", {})
    avail = kpis.get("availability", {})
    breakdown = kpis.get("error_breakdown", {})
    total_errors = sum(breakdown.values())
    top_errors = sorted(breakdown.items(), key=lambda x: -x[1])[:3]
    top_str = ", ".join([f"{e[0].replace('_', ' ').title()} ({e[1]})" for e in top_errors])

    return f"""Analyze this data quality report for business managers.
Write plain text only, no markdown/asterisks/bullet symbols. Use numbered lists where needed.

Dataset: {dq.get('total_rows',48)} records, {dq.get('fill_rate_pct','N/A')}% fill rate, {total_errors} errors, {avail.get('match_pct','N/A')}% date match. Top issues: {top_str}.

Provide EXACTLY these 6 sections with these headers:

EXECUTIVE SUMMARY:
3-4 sentences covering: what was analyzed, overall data quality score, total errors found, and the single most critical finding that needs immediate attention.

ANOMALY ANALYSIS:
For each of the top 4-5 error types, write 2-3 sentences in plain English explaining: what the error means in business terms, how many records are affected, and what operational impact it has. Do not use bullet points.

ROOT CAUSE ANALYSIS:
3-5 numbered root causes. Reference specific column names and error patterns. Explain WHY these errors are occurring (process gaps, system issues, training gaps).

INVESTIGATION STEPS:
3-4 numbered specific actions the team should take to verify and investigate the flagged records. Include what to check, who should do it, and expected timeline.

RECOMMENDATIONS:
4-6 numbered process improvements to prevent these errors in future. Be specific to this dataset and include both quick fixes and long-term solutions.

YEAR-WISE TRENDS:
Look at the YEAR-WISE DISTRIBUTION data provided. Identify any year-over-year patterns:
- Are errors increasing or decreasing over the years?
- Are certain years significantly worse than others?
- Are there seasonal or temporal patterns in the data quality issues?
If the data spans only one year or has no date variation, note that and skip.

Keep the total response under 700 words.

DATA:
{data_summary}
"""


def _build_email_prompt(data_summary, kpis):
    """Build a richer email prompt with 5 paragraphs."""
    dq = kpis.get("data_quality", {})
    avail = kpis.get("availability", {})
    breakdown = kpis.get("error_breakdown", {})
    total_errors = sum(breakdown.values())
    top_errors = sorted(breakdown.items(), key=lambda x: -x[1])[:3]
    top_error_str = ", ".join([f"{e[0].replace('_', ' ').title()} ({e[1]})" for e in top_errors])

    return f"""Write 5 paragraphs for a management email about data quality issues.
Plain text only, no markdown. Under 300 words total. Professional, factual tone.

Key facts: {dq.get('total_rows',48)} records, {dq.get('total_columns',22)} columns, {dq.get('fill_rate_pct','N/A')}% fill rate, {total_errors} errors, {avail.get('match_pct','N/A')}% date match, top issues: {top_error_str}.

Para 1: What was analyzed and the methodology used (automated data quality check on equipment availability dataset).
Para 2: Key findings with specific numbers (error count, fill rate, match rate).
Para 3: Most critical concerns and their business impact.
Para 4: Specific columns and records that need immediate attention.
Para 5: Next steps -- reports are attached, request the team review and correct flagged records, suggest a follow-up review.

Do NOT include "Dear sir/ma'am" or "Regards" -- those are added separately.
"""


# ---------------------------------------------------------------------------
# Fallback generators
# ---------------------------------------------------------------------------

def _fallback_report_text(kpis, errors):
    """Return a plain-text fallback matching the same 5-section structure the AI would produce."""
    breakdown = kpis.get("error_breakdown", {})
    total_errors = sum(breakdown.values())
    dq = kpis.get("data_quality", {})
    avail = kpis.get("availability", {})

    top_errors = sorted(breakdown.items(), key=lambda x: -x[1])[:3]
    top_str = ", ".join([f"{e[0].replace('_',' ').title()} ({e[1]})" for e in top_errors])

    # Build error type descriptions for anomaly section
    anomaly_lines = []
    for etype, count in sorted(breakdown.items(), key=lambda x: -x[1])[:5]:
        desc = ERROR_TYPES.get(etype, "Unknown error type")
        pct = round((count / total_errors) * 100, 1) if total_errors else 0
        anomaly_lines.append(
            f"{etype.replace('_', ' ').title()} ({count} occurrences, {pct}% of all errors): "
            f"{desc}. This affects data reliability and may impact operational reporting accuracy."
        )

    lines = [
        "EXECUTIVE SUMMARY:",
        f"The dataset ({dq.get('total_rows','N/A')} records, "
        f"{dq.get('total_columns','N/A')} columns) was analyzed for data quality issues. "
        f"The overall data fill rate is {dq.get('fill_rate_pct','N/A')}% with "
        f"{total_errors} errors detected across all records. "
        f"The availability date match rate is {avail.get('match_pct','N/A')}%. "
        f"The most significant issues are: {top_str}.",
        "",
        "ANOMALY ANALYSIS:",
    ]
    for al in anomaly_lines:
        lines.append(al)
        lines.append("")

    lines += [
        "ROOT CAUSE ANALYSIS:",
        "1. Incomplete data entry procedures -- several fields have high missing rates,",
        "   suggesting they are not enforced as mandatory in the data entry process.",
        "2. Timing discrepancies in record creation -- created dates often precede",
        "   actual availability dates, indicating records are filled before work completes.",
        "3. Delayed record modifications -- modified dates frequently exceed acceptable",
        "   thresholds after creation, suggesting updates are not made promptly.",
        "4. Data entry sequencing issues -- maintenance start times appear before entry",
        "   timestamps in many records, pointing to incorrect timestamp recording.",
        "",
        "INVESTIGATION STEPS:",
        "1. Pull all records with missing data in high-impact columns and verify whether",
        "   the data can be recovered from maintenance logs or operator records.",
        "2. Review the flagged date mismatch records with site supervisors to determine",
        "   if the discrepancies reflect actual operational issues or data entry errors.",
        "3. Check whether the delayed modification pattern correlates with specific",
        "   operators, shifts, or sites to identify targeted training needs.",
        "",
        "RECOMMENDATIONS:",
        "1. Make high-missing-rate columns mandatory fields in the data entry form.",
        "2. Add validation rules to prevent illogical date sequences at the point of entry.",
        "3. Implement a review process requiring records to be completed and modified",
        "   within 24 hours of the actual availability date.",
        "4. Conduct targeted training for data entry staff on correct timestamp sequencing.",
        "5. Review the detailed error table below and correct all flagged records,",
        "   prioritizing rows with the highest error counts.",
        "",
        "YEAR-WISE TRENDS:",
        "Year-wise trend analysis requires date columns spanning multiple years.",
        "Please refer to the year-wise distribution table above for temporal patterns.",
        "",
        "(Note: Gemini API was unavailable. This is an automated fallback analysis.)",
    ]
    return "\n".join(lines)


def _fallback_email_body(kpis):
    """Return a plain-text fallback email body matching the 5-paragraph structure."""
    breakdown = kpis.get("error_breakdown", {})
    total_errors = sum(breakdown.values())
    dq = kpis.get("data_quality", {})
    avail = kpis.get("availability", {})
    top_errors = sorted(breakdown.items(), key=lambda x: -x[1])[:3]
    top_str = ", ".join([f"{e[0].replace('_',' ').title()} ({e[1]})" for e in top_errors])

    return (
        f"This email is regarding the automated data quality analysis conducted on "
        f"the equipment availability dataset. The dataset contains "
        f"{dq.get('total_rows', 'N/A')} records across {dq.get('total_columns', 'N/A')} "
        f"columns. An automated quality check was performed covering missing data detection, "
        f"date comparison validation, and full file scan for completeness.\n"
        f"\n"
        f"The analysis identified a total of {total_errors} errors and mismatches, with an "
        f"overall data fill rate of {dq.get('fill_rate_pct', 'N/A')}%. "
        f"The availability date match rate stands at {avail.get('match_pct', 'N/A')}%, "
        f"with {avail.get('dates_not_matching', 0)} records showing a date discrepancy.\n"
        f"\n"
        f"The most critical concerns are: {top_str}. "
        f"These issues indicate significant gaps in data entry completeness and consistency "
        f"that may affect operational reporting and decision-making.\n"
        f"\n"
        f"Immediate attention is recommended for columns with the highest missing data rates "
        f"and records flagged with date comparison errors. The summary tables below provide "
        f"a breakdown of all issues by category and affected columns.\n"
        f"\n"
        f"Detailed reports have been generated and are available in the output folder. "
        f"Please review the flagged records and take corrective action at the earliest "
        f"opportunity. A follow-up review is recommended within one week to track progress."
    )


# ---------------------------------------------------------------------------
# Section builder helper
# ---------------------------------------------------------------------------

def _section(title):
    """Return a formatted section header."""
    return f"\n{THIN}\n\n  {title}\n{THIN}\n"


# Known AI subsection headers (matched case-insensitively with trailing colon)
_AI_SUBSECTION_HEADERS = [
    "EXECUTIVE SUMMARY",
    "ANOMALY ANALYSIS",
    "ROOT CAUSE ANALYSIS",
    "INVESTIGATION STEPS",
    "RECOMMENDATIONS",
    "YEAR-WISE TRENDS",
]


def _format_ai_analysis(ai_text):
    """
    Format AI-generated analysis text with visual sub-section headers.
    Detects known section titles and formats them with clean underlines.
    Regular text gets light indentation. Extra spacing between sections.
    """
    lines = ai_text.split("\n")
    formatted = []

    for line in lines:
        stripped = line.strip()

        # Check if this line is a known sub-section header
        is_header = False
        for header in _AI_SUBSECTION_HEADERS:
            if stripped.upper().startswith(header):
                is_header = True
                formatted.append("")
                formatted.append("")
                formatted.append(f"    {header}")
                formatted.append(f"    {'~' * len(header)}")
                formatted.append("")
                break

        if not is_header:
            if stripped == "":
                formatted.append("")
            else:
                # Wrap long lines for readability
                _wrap_and_indent(stripped, formatted, indent=4, width=88)

    return formatted


def _wrap_and_indent(text, output_list, indent=4, width=88):
    """Word-wrap text to width and add to output_list with indentation."""
    prefix = " " * indent
    if len(text) <= width:
        output_list.append(f"{prefix}{text}")
        return

    words = text.split()
    current_line = ""
    for word in words:
        if current_line and len(current_line) + 1 + len(word) > width:
            output_list.append(f"{prefix}{current_line}")
            current_line = word
        else:
            current_line = f"{current_line} {word}" if current_line else word

    if current_line:
        output_list.append(f"{prefix}{current_line}")



# ---------------------------------------------------------------------------
# Row detail builder (matches report_generator.py format)
# ---------------------------------------------------------------------------

def _build_row_details(errors):
    """Build detailed error breakdown by row, matching the original report format."""
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

    total_errors = sum(len(d["errors"]) for d in grouped.values())
    lines = []

    for row_num, data in grouped.items():
        ticket = data["ticket"]
        record_id = data["id"]
        err_list = data["errors"]

        # Separate errors by category
        date_error_types = {
            "MISSING_DATE", "START_BEFORE_ENTRY", "DATE_MISMATCH",
            "CREATED_BEFORE_ACTUAL", "CREATED_AFTER_ACTUAL",
            "MODIFIED_BEFORE_CREATED", "MODIFIED_TOO_LATE",
            "MODIFIED_BEFORE_ACTUAL", "DATE_ORDER_ERROR",
            "DATE_MATCH_ERROR", "DATE_PROXIMITY_ERROR",
        }
        date_errors = [e for e in err_list if e["error_type"] in date_error_types]
        data_errors = [e for e in err_list if e["error_type"] == "MISSING_DATA"]
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

    return lines, len(grouped), total_errors


# ---------------------------------------------------------------------------
# Public interface -- generates final report + email
# ---------------------------------------------------------------------------

def generate_ai_outputs(df, errors, kpis, date_columns, comparison_rules=None, output_dir=None):
    """
    Main entry point. Generates the FINAL report and email.

    Builds the full document structure in code (all tables, all row details)
    and inserts AI-generated insights into Section 2 (above tables).

    Saves:
      - <output_dir>/report_final.txt  (complete report with everything)
      - <output_dir>/email_final.txt   (complete email with tables)

    Returns:
        dict with keys: 'report_analysis', 'email_body', 'report_success', 'email_success'
    """
    if output_dir is None:
        output_dir = OUTPUT_DIR

    print("\n" + "=" * 80)
    print("GENERATING AI ANALYSIS (Gemini)")
    print("=" * 80)


    data_summary = _build_data_summary(df, errors, kpis, date_columns)

    # --- Generate AI prose ---
    report_prompt = _build_report_prompt(data_summary, kpis)
    report_ai_text, report_success = _call_gemini(report_prompt, label="Report Analysis")

    if not report_success or not report_ai_text:
        print("[AI] Using fallback for report analysis.")
        report_ai_text = _fallback_report_text(kpis, errors)

    email_prompt = _build_email_prompt(data_summary, kpis)
    email_ai_text, email_success = _call_gemini(email_prompt, label="Email Body")

    if not email_success or not email_ai_text:
        print("[AI] Using fallback for email body.")
        email_ai_text = _fallback_email_body(kpis)

    # --- Extract shared data for tables ---
    dq = kpis.get("data_quality", {})
    avail = kpis.get("availability", {})
    breakdown = kpis.get("error_breakdown", {})
    total_errors = sum(breakdown.values())
    missing_summary = kpis.get("missing_data_summary", {})
    date_completeness = kpis.get("date_completeness", {})
    total_rows = dq.get("total_rows", df.shape[0])

    # Column error counts
    column_counts = {}
    for err in errors:
        col = err.get("column", "Unknown")
        column_counts[col] = column_counts.get(col, 0) + 1
    top_columns = sorted(column_counts.items(), key=lambda x: -x[1])[:5]

    # Use provided rules or defaults
    rules_used = comparison_rules or _filter_default_rules(df)

    # ===================================================================
    # BUILD FINAL REPORT (complete, with all sections + row details)
    # ===================================================================
    rpt = []
    rpt.append(LINE)
    rpt.append("")
    rpt.append("    ADOA  --  FINAL ANALYSIS REPORT")
    rpt.append("    Data Quality & Error Analysis")
    rpt.append("")
    rpt.append(LINE)

    # --- Section 1: Data Overview ---
    rpt.append(_section("1.  DATA OVERVIEW"))
    rpt.append(f"    Total Rows           :  {total_rows}")
    rpt.append(f"    Total Columns        :  {dq.get('total_columns', df.shape[1])}")
    rpt.append(f"    Total Cells          :  {dq.get('total_cells', 'N/A')}")
    rpt.append(f"    Null Cells           :  {dq.get('null_cells', 'N/A')}")
    rpt.append(f"    Data Fill Rate       :  {dq.get('fill_rate_pct', 'N/A')}%")
    rpt.append(f"    Date Columns Found   :  {len(date_columns)}")
    if avail:
        rpt.append("")
        rpt.append("    --- Availability (date only, time ignored) ---")
        rpt.append(f"    Records compared     :  {avail.get('total_records_with_both_dates', 'N/A')}")
        rpt.append(f"    Dates matching       :  {avail.get('dates_matching', 'N/A')}")
        rpt.append(f"    Dates not matching   :  {avail.get('dates_not_matching', 'N/A')}")
        rpt.append(f"    Match percentage     :  {avail.get('match_pct', 'N/A')}%")

    # --- Section 2: AI ANALYSIS (ABOVE tables) ---
    rpt.append(_section("2.  AI ANALYSIS"))
    rpt.extend(_format_ai_analysis(report_ai_text))


    # --- Section 3: Comparison Rules Used ---
    rpt.append(_section("3.  COMPARISON RULES APPLIED"))
    if rules_used:
        for i, rule in enumerate(rules_used, 1):
            rpt.append(f"    Rule {i}:  {rule.get('rule', 'N/A')}")
            rpt.append(f"            {rule.get('col_a', '')}  vs  {rule.get('col_b', '')}")
            rpt.append(f"            {rule.get('description', '')}")
            rpt.append("")
    else:
        rpt.append("    No comparison rules were applicable for this dataset.")

    # --- Section 4: Missing Data Summary ---
    rpt.append(_section("4.  MISSING DATA SUMMARY  (Full File Scan)"))
    rpt.append(f"    {'Column':<{COL_W}s}  {'Missing / Total':<15s}  {'%':<8s}  What is it?")
    rpt.append(f"    {'-'*COL_W}  {'-'*15}  {'-'*8}  {'-'*30}")

    for col in date_columns:
        dc = date_completeness.get(col, {})
        miss = dc.get("missing", 0)
        if miss > 0:
            pct = round((miss / total_rows) * 100, 1)
            rpt.append(f"    {col:<{COL_W}s}  {miss:>5d} / {total_rows:<5d}   {pct:>6.1f}%  Date column")

    for col, cnt in sorted(missing_summary.items(), key=lambda x: -x[1]):
        pct = round((cnt / total_rows) * 100, 1)
        rpt.append(f"    {col:<{COL_W}s}  {cnt:>5d} / {total_rows:<5d}   {pct:>6.1f}%")

    # --- Section 5: Error/Mismatch Summary ---
    rpt.append(_section("5.  ERROR / MISMATCH SUMMARY"))
    rpt.append(f"    {'Error Type':<{COL_W}s}  {'Count':>6s}  Description")
    rpt.append(f"    {'-'*COL_W}  {'-'*6}  {'-'*40}")
    for etype, count in sorted(breakdown.items(), key=lambda x: -x[1]):
        desc = ERROR_TYPES.get(etype, "")
        rpt.append(f"    {etype:<{COL_W}s}  {count:>6d}  {desc}")
    rpt.append(f"    {'-'*COL_W}  {'-'*6}")
    rpt.append(f"    {'TOTAL':<{COL_W}s}  {total_errors:>6d}")

    # --- Section 6: Top Affected Columns ---
    rpt.append(_section("6.  TOP AFFECTED COLUMNS"))
    rpt.append(f"    {'Column':<{COL_W}s}  {'Errors':>6s}")
    rpt.append(f"    {'-'*COL_W}  {'-'*6}")
    for col, cnt in top_columns:
        rpt.append(f"    {col:<{COL_W}s}  {cnt:>6d}")

    # --- Section 7: Detailed Errors by Row ---
    row_detail_lines, row_count, row_total_errors = _build_row_details(errors)
    rpt.append(_section(f"7.  DETAILED ERRORS BY ROW  ({row_count} rows, {row_total_errors} errors)"))
    rpt.extend(row_detail_lines)

    # --- Footer ---
    rpt.append("")
    rpt.append(LINE)
    rpt.append(f"  END OF REPORT  --  {row_count} rows  |  {row_total_errors} total errors")
    rpt.append(LINE)

    report_full = "\n".join(rpt)

    # ===================================================================
    # BUILD FINAL EMAIL (AI prose + all tables)
    # ===================================================================
    email_lines = []

    # AI-generated body paragraphs
    email_lines.append(email_ai_text)

    # Missing data table
    has_missing = any(
        date_completeness.get(c, {}).get("missing", 0) > 0 for c in date_columns
    ) or bool(missing_summary)

    if has_missing:
        email_lines.append("")
        email_lines.append("Missing Data Summary (Full File Scan):")
        email_lines.append("")
        email_lines.append(f"  {'Column':<{COL_W}s}  {'Missing':>7s}  {'Total':>5s}  {'% Missing':>9s}")
        email_lines.append(f"  {'-'*COL_W}  {'-'*7}  {'-'*5}  {'-'*9}")

        for col in date_columns:
            dc = date_completeness.get(col, {})
            miss = dc.get("missing", 0)
            if miss > 0:
                pct = round((miss / total_rows) * 100, 1)
                email_lines.append(f"  {col:<{COL_W}s}  {miss:>7d}  {total_rows:>5d}  {pct:>8.1f}%")

        for col, cnt in sorted(missing_summary.items(), key=lambda x: -x[1]):
            pct = round((cnt / total_rows) * 100, 1)
            email_lines.append(f"  {col:<{COL_W}s}  {cnt:>7d}  {total_rows:>5d}  {pct:>8.1f}%")

    # Error summary table
    email_lines.append("")
    email_lines.append("Error/Mismatch Summary:")
    email_lines.append("")
    email_lines.append(f"  {'Error Type':<{COL_W}s}  {'Count':>6s}  Description")
    email_lines.append(f"  {'-'*COL_W}  {'-'*6}  {'-'*40}")
    for etype, count in sorted(breakdown.items(), key=lambda x: -x[1]):
        desc = ERROR_TYPES.get(etype, "")
        email_lines.append(f"  {etype:<{COL_W}s}  {count:>6d}  {desc}")
    email_lines.append(f"  {'-'*COL_W}  {'-'*6}")
    email_lines.append(f"  {'TOTAL':<{COL_W}s}  {total_errors:>6d}")

    # Top affected columns
    email_lines.append("")
    email_lines.append("Top Affected Columns:")
    email_lines.append("")
    email_lines.append(f"  {'Column':<{COL_W}s}  {'Errors':>6s}")
    email_lines.append(f"  {'-'*COL_W}  {'-'*6}")
    for col, cnt in top_columns:
        email_lines.append(f"  {col:<{COL_W}s}  {cnt:>6d}")
    email_lines.append("")

    email_body_full = "\n".join(email_lines)

    # Wrap with Dear/Regards template
    from config import EMAIL_TEMPLATE
    email_draft_full = EMAIL_TEMPLATE.format(body=email_body_full)

    # --- Save files ---
    os.makedirs(output_dir, exist_ok=True)

    report_path = os.path.join(output_dir, REPORT_FILENAME)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_full)
    print(f"[AI] Final report saved to: {report_path}")

    email_path = os.path.join(output_dir, EMAIL_FILENAME)
    with open(email_path, "w", encoding="utf-8") as f:
        f.write(email_draft_full)
    print(f"[AI] Final email saved to: {email_path}")

    return {
        "report_analysis": report_ai_text,
        "email_body": email_ai_text,
        "report_full": report_full,
        "email_full": email_draft_full,
        "report_success": report_success,
        "email_success": email_success,
    }


if __name__ == "__main__":
    from reader import read_excel
    from standardizer import standardize
    from comparator import MismatchDetector

    df = read_excel()
    df, date_cols, parse_errors = standardize(df)
    rules = suggest_comparison_rules(df, date_cols)
    detector = MismatchDetector(df, date_cols, parse_errors, comparison_rules=rules)
    errors, kpis = detector.run_all_checks()
    result = generate_ai_outputs(df, errors, kpis, date_cols, comparison_rules=rules)
    print("\n--- REPORT SAVED ---")
    print(f"Report: output/{REPORT_FILENAME}")
    print(f"Email: output/{EMAIL_FILENAME}")
