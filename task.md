# ADOA -- Task List

## Week 1: Data Ingestion and Preparation

The first week focuses on building the data foundation of the ADOA system. The provided Excel file will act as the initial enterprise data source. The goal is to read, understand, clean, and prepare this data so it can be used for KPI validation later.
The first step is to create a Python-based data ingestion module that loads the Excel file using libraries like Pandas and OpenPyXL. The system will identify the available sheets, columns, data types, and understand what KPIs or operational metrics are present in the file.

After loading the data, a preprocessing layer will be developed to clean and standardize the information. This includes handling missing values, removing duplicate records, correcting data formats (especially dates and numbers), standardizing column names, and converting the data into a consistent structure.

The final output of Week 1 will be a cleaned and structured dataset stored in a processed format. This prepared dataset will become the input for Week 2.

### Week 1 Tasks

- `[x]` Data Ingestion
  - `[x]` Find and inspect Excel file structure (spmdata.xls: 48 rows x 36 columns)
  - `[x]` Create reader.py -- Excel reading with auto-detect & preview
  - `[x]` Support .xls and .xlsx formats via xlrd / openpyxl engines
  - `[x]` Print column names, row counts, and data previews

- `[x]` Data Preprocessing & Standardization
  - `[x]` Create standardizer.py -- Data cleaning module
  - `[x]` Auto-detect date columns (8 detected)
  - `[x]` Parse date columns to datetime format
  - `[x]` Strip whitespace from string columns
  - `[x]` Standardize column names (uppercase, trimmed)
  - `[x]` Log cells that fail to parse

---

## Week 2: KPI Validation and Report Generation

The second week focuses on building the validation and reporting layer of the ADOA system. The cleaned Excel data will be used to create KPI validation rules that check whether calculated metrics are accurate and within acceptable limits.

A validation engine will be developed to compare KPI values against expected calculations, identify differences, and classify them as normal or exceptions. The system will calculate differences, apply threshold rules, and highlight mismatches that require investigation.

Once validation is complete, a reporting module will be created to automatically generate outputs such as a daily KPI report and an exceptions report. The daily report will summarize the overall KPI status, while the exceptions report will list failed validations with details about the mismatch.

The final outcome of Week 2 will be a working MVP pipeline where the system can take the Excel file as input, process the data, validate KPIs, and generate business-ready reports. This will later be extended with AI-based anomaly explanations and automation features.

### Week 2 Tasks

- `[x]` KPI Validation & Mismatch Detection
  - `[x]` Create comparator.py -- Validation engine
  - `[x]` Compare date pairs (Expected vs Actual availability, etc.)
  - `[x]` Detect missing dates (104 found)
  - `[x]` Detect date mismatches (41 found)
  - `[x]` Detect late/early availability (5 late, 20 early)
  - `[x]` Detect missing critical data (16 found)
  - `[x]` Auto-detect similar columns (REASONIFBREAKDOWN <-> ACTIONTAKEN, 83%)
  - `[x]` Compute KPIs (fill rate, on-time %, variance)

- `[x]` Report Generation
  - `[x]` Create report_generator.py -- Detailed error table report
  - `[x]` Create email_drafter.py -- Email draft with summary paragraph + error table
  - `[x]` Export combined CSV report (mismatches.csv, 235 entries)
  - `[x]` Save error_report.txt with row-by-row error listing
  - `[x]` Save email_draft.txt with "Dear sir/ma'am" template

- `[x]` Pipeline & Orchestration
  - `[x]` Create main.py -- Entry point with --auto and interactive menu
  - `[x]` Create config.py -- Central configuration
  - `[x]` Create requirements.txt
  - `[x]` Fix Windows cp1252 Unicode encoding compatibility
  - `[x]` Verify full pipeline end-to-end (235 errors, 88.1% on-time, 55% fill rate)
