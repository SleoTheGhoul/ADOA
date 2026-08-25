# ADOA — Asset Data & Outage Analysis Tool
# Project Walkthrough & User Guide


## How to Run
─────────────

    python main.py --auto

That single command processes ALL Excel files in the Excels/ folder.
Each file gets its own output subfolder with a report, email, CSV, and summary.

Alternative commands:
    python main.py --auto     Process all Excel files in Excels/
    python main.py --batch    Same as --auto
    python main.py            Interactive menu (manual control)


## Project Structure
────────────────────

    ADOA/
    │
    ├── main.py               Entry point — runs the 9-step pipeline
    ├── reader.py              Reads Excel files, discovers sheets
    ├── standardizer.py        Cleans columns, auto-detects date columns
    ├── comparator.py          Detects errors using AI-suggested rules
    ├── ai_engine.py           Gemini AI — suggests rules, writes report & email
    ├── config.py              All settings, API keys, paths, defaults
    │
    ├── Excels/                DROP YOUR EXCEL FILES HERE
    │   ├── spmdata.xls
    │   └── EQUIPMENT DET.xls
    │
    └── output/                GENERATED OUTPUT (per file)
        ├── spmdata/
        │   ├── report_final.txt
        │   ├── email_final.txt
        │   ├── mismatches.csv
        │   └── pipeline_summary.txt
        └── EQUIPMENT DET/
            ├── report_final.txt
            ├── email_final.txt
            ├── mismatches.csv
            └── pipeline_summary.txt

    Legacy files (not used by pipeline):
        report_generator.py    Old report generator (replaced by ai_engine.py)
        email_drafter.py       Old email drafter (replaced by ai_engine.py)
        draft_generator.py     Old draft templates (replaced by ai_engine.py)


## Pipeline — 9 Steps (per file, per sheet)
────────────────────────────────────────────

    Step 1: READ EXCEL
        reader.py reads the file and discovers all sheets.
        Each sheet is processed independently.

    Step 2: STANDARDIZE DATA
        standardizer.py cleans the data:
        - Column names → UPPERCASE, stripped, underscores
        - Auto-detects date columns by name patterns
          (looks for: date, time, created, modified, start, end, etc.)
        - Parses detected date columns to datetime format
        - Strips whitespace from string columns
        - Converts empty strings / "nan" / "null" to NaN

    Step 3: AI COLUMN ANALYSIS
        ai_engine.py sends ALL column names to Gemini and asks:
        "What should we compare? What logical rules apply?"

        Gemini returns 3-10 rules like:
        - CREATEDON should be after ENTRYDATETIME (A_AFTER_OR_EQUAL_B)
        - ACTUALDATEOFAVAILABILITY should match EXPECTEDDATEOFAVAILABILITY (A_EQUALS_B_DATE)

        The AI is ALWAYS consulted, regardless of how many date columns exist.
        If Gemini is unavailable, falls back to 5 default rules from config.py.

    Step 4: DETECT ERRORS & COMPUTE KPIs
        comparator.py runs 4 checks (all automatic, every time):

        Check 1: Missing Dates
            Flags null/empty values in detected date columns.

        Check 2: Date Comparisons (AI rules)
            Applies the AI-suggested rules using 6 generic handlers:
            - A_BEFORE_B          Column A should be before Column B
            - A_AFTER_B           Column A should be after Column B
            - A_EQUALS_B_DATE     Dates should match (time ignored)
            - A_WITHIN_DAYS_B     Dates should be within 1 day
            - A_BEFORE_OR_EQUAL_B Column A <= Column B
            - A_AFTER_OR_EQUAL_B  Column A >= Column B

        Check 3: Missing Data (full file scan)
            Scans EVERY non-date column for nulls/empty values.

        Check 4: Similar Columns
            Finds column pairs that are >60% similar and flags mismatches.

        Then computes KPIs: fill rate, date match rate, error breakdown, etc.

    Step 5: CSV REPORT
        comparator.py exports all errors to mismatches.csv
        Grouped by row — each row appears once with all its errors.

    Steps 6-8: AI REPORT & EMAIL
        ai_engine.py builds the final report and email:

        1. Sends error data + KPIs to Gemini for prose analysis
        2. Gemini writes 6 sections:
           - Executive Summary
           - Anomaly Analysis
           - Root Cause Analysis
           - Investigation Steps
           - Recommendations
           - Year-Wise Trends
        3. Combines AI prose with data tables into report_final.txt
        4. Builds email_final.txt with tables + AI prose
        5. If Gemini is unavailable, uses fallback text

    Step 9: PIPELINE SUMMARY
        Saves a quick summary of what was processed, rules used, errors found.


## How Rules Work (Fully AI-Driven)
────────────────────────────────────

    NO hardcoded rules. The flow is:

    1. Standardizer detects date columns by name pattern matching
    2. AI receives ALL column names + sample data
    3. AI suggests rules: "compare X vs Y using check_type Z"
    4. Comparator applies those rules using generic handlers
    5. If AI is unavailable → falls back to 5 default rules in config.py

    The AI decides:
        - WHICH columns to compare
        - WHAT type of comparison to use
        - HOW MANY rules to generate (3-10)

    The code only provides the 6 comparison mechanisms (before, after, equals, etc.)
    The AI picks which ones to use for each column pair.


## Multi-File & Multi-Sheet Support
────────────────────────────────────

    Multi-file:
        Drop any number of .xlsx / .xls files into the Excels/ folder.
        Each file gets its own output subfolder: output/<filename>/

    Multi-sheet:
        If an Excel file has multiple sheets, each sheet is processed
        independently with its own rules, report, and email.
        Output goes to: output/<filename>/<sheet_name>/

        If a file has only 1 sheet, output goes directly to output/<filename>/
        Empty sheets are automatically skipped.


## Requirements
───────────────

    pip install pandas numpy google-generativeai xlrd openpyxl

    Python 3.8+
    Gemini API keys are configured in config.py (4 keys with auto-rotation)


## Output Files Explained
─────────────────────────

    report_final.txt      Full analysis report with:
                          - Data overview tables
                          - AI analysis (6 sections)
                          - Comparison rules applied
                          - Missing data summary
                          - Error breakdown tables
                          - Detailed errors by row

    email_final.txt       Management email with:
                          - AI-written prose (5 paragraphs)
                          - Error summary table
                          - Top affected columns

    mismatches.csv        All errors in CSV format, grouped by row.
                          Can be opened in Excel for filtering/sorting.

    pipeline_summary.txt  Quick stats: rows, columns, rules, errors, fill rate.


## Config Reference (config.py)
───────────────────────────────

    EXCELS_DIR              Where to find Excel files (default: Excels/)
    OUTPUT_DIR              Where output goes (default: output/)
    GEMINI_API_KEYS         List of 4 API keys (auto-rotates on rate limit)
    GEMINI_MODEL            Model name (default: gemini-2.5-flash)
    DATE_PATTERNS           Keywords for auto-detecting date columns
    ID_PATTERNS             Keywords for auto-detecting ID columns
    SIMILARITY_THRESHOLD    Min similarity for flagging column pairs (default: 0.6)
    CRITICAL_COLUMNS        Non-date columns that should not be empty
    DEFAULT_COMPARISON_RULES  Fallback rules when AI is unavailable
    ERROR_TYPES             Generic error type definitions
