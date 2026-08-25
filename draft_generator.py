"""
draft_generator.py -- AI-ready draft generation module.

Creates draft instruction files saved to output/drafts/.
These are backup templates that can be provided to an AI manually.
"""

import os
from config import (
    DRAFTS_DIR, DEFAULT_COMPARISON_RULES, ERROR_TYPES,
    DRAFT_REPORT_FILENAME, DRAFT_EMAIL_FILENAME,
)


def generate_drafts(df, errors, kpis):
    """
    Generate AI-ready draft instruction files.
    Saved to output/drafts/ for backup purposes.

    Returns:
        tuple: (report_draft_path, email_draft_path)
    """
    print("\n" + "=" * 80)
    print("GENERATING DRAFT INSTRUCTION FILES")
    print("=" * 80)

    os.makedirs(DRAFTS_DIR, exist_ok=True)

    report_path = _generate_report_draft(df, errors, kpis)
    email_path = _generate_email_draft(df, errors, kpis)

    return report_path, email_path


def _generate_report_draft(df, errors, kpis):
    """Generate the report draft (instructions only)."""
    total_errors = sum(kpis.get("error_breakdown", {}).values())
    dq = kpis.get("data_quality", {})

    draft = f"""================================================================================
AI REPORT DRAFT -- Instructions for generating a polished report
================================================================================

INSTRUCTIONS FOR AI:
--------------------
Generate a professional 1-2 page error report for the dataset.
The report should:

1. Start with an executive summary (3-4 sentences) of the dataset and findings.

2. Include an anomaly analysis explaining each error type in business terms.

3. Include a root cause analysis (3-5 causes referencing specific columns).

4. Include investigation steps (3-4 specific actions).

5. Include recommendations (4-6 process improvements).

6. Use a professional, factual tone suitable for management review.

7. Format it as a clean text document (no markdown, no asterisks).

KEY METRICS:
  Rows: {dq.get('total_rows', df.shape[0])}
  Columns: {dq.get('total_columns', df.shape[1])}
  Fill Rate: {dq.get('fill_rate_pct', 'N/A')}%
  Total Errors: {total_errors}

NOTE: The actual data will be provided separately by the pipeline.
This file contains instructions only.
================================================================================
"""

    filepath = os.path.join(DRAFTS_DIR, DRAFT_REPORT_FILENAME)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(draft)
    print(f"[DRAFT] Report draft saved to: {filepath}")
    return filepath


def _generate_email_draft(df, errors, kpis):
    """Generate the email draft (instructions only)."""
    total_errors = sum(kpis.get("error_breakdown", {}).values())
    dq = kpis.get("data_quality", {})
    avail = kpis.get("availability", {})
    breakdown = kpis.get("error_breakdown", {})

    top_errors = sorted(breakdown.items(), key=lambda x: -x[1])[:3]
    top_error_str = ", ".join([f"{e[0].replace('_',' ').title()} ({e[1]})" for e in top_errors])

    draft = f"""================================================================================
AI EMAIL DRAFT -- Instructions for generating a management email
================================================================================

INSTRUCTIONS FOR AI:
--------------------
Generate the BODY of a professional email (5 paragraphs, under 300 words).
Do NOT include "Dear sir/ma'am" or "Regards".

Para 1: What was analyzed and methodology.
Para 2: Key findings with numbers ({total_errors} errors, {dq.get('fill_rate_pct','N/A')}% fill rate).
Para 3: Most critical concerns and business impact.
Para 4: Specific columns needing attention.
Para 5: Next steps (reports attached, request review).

Top issues: {top_error_str}
Date match rate: {avail.get('match_pct', 'N/A')}%

NOTE: The actual data will be provided separately by the pipeline.
This file contains instructions only.
================================================================================
"""

    filepath = os.path.join(DRAFTS_DIR, DRAFT_EMAIL_FILENAME)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(draft)
    print(f"[DRAFT] Email draft saved to: {filepath}")
    return filepath


if __name__ == "__main__":
    from reader import read_excel
    from standardizer import standardize
    from comparator import MismatchDetector

    df = read_excel()
    df, date_cols, parse_errors = standardize(df)
    detector = MismatchDetector(df, date_cols, parse_errors)
    errors, kpis = detector.run_all_checks()
    generate_drafts(df, errors, kpis)
