# HubSpot to Twenty CRM — Companies Migration

## Overview

This repository contains the **Companies component of DATA-01: HubSpot to Twenty CRM Data Extraction & Migration Pipeline**.

The workflow extracts Company records from HubSpot, transforms them into the required Twenty CRM schema, validates data quality, generates exception reports, and prepares clean CSV data for migration.

## Architecture

```text
┌──────────────────────┐
│     HubSpot CRM      │
│    Companies API     │
└──────────┬───────────┘
           │ REST API / Bearer Auth
           ▼
┌──────────────────────┐
│     companies.py     │
│ • API Pagination     │
│ • Field Extraction   │
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│ Transform & Clean    │
│ • Field Mapping      │
│ • URL Normalization  │
│ • Deduplication      │
│ • Null Cleaning      │
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│    companies.csv     │
│  3,043 Companies     │
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│validate_companies.py │
│ • Names & Domains    │
│ • Websites           │
│ • Numeric Fields     │
│ • Nulls/Duplicates   │
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│ Reports + Test CSV   │
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│      Twenty CRM      │
│ Test Import Pending  │
│ Workspace Access     │
└──────────────────────┘
```

## Field Mapping

| HubSpot Field | Twenty CRM Column |
|---|---|
| Company Name | `name` |
| Company Domain | `Domain / Domain URL` |
| Website | `Links / Primary Link URL` |
| Street Address | `Address / Address 1` |
| City | `Address / City` |
| State/Region | `Address / State` |
| Postal Code | `Address / Post Code` |
| Country | `Address / Country` |
| Number of Employees | `employees` |
| Annual Revenue | `annualRevenue / Amount` |

## Implementation

`companies.py` authenticates with HubSpot, retrieves Companies through API pagination, maps the required properties, normalizes URLs and numeric values, removes duplicate populated domains, preserves missing values as blanks, and generates `companies.csv`.

`validate_companies.py` independently validates the transformed dataset and generates exception reports for records requiring review.

```text
Raw HubSpot Companies:  3047
Final Companies:        3043
```

## Data Quality Results

```text
Total Companies:               3043
Missing Company Names:           60
Companies with Domain:         2250
Missing Domains:                793
Missing Both Name & Domain:      30
Duplicate Domains:                0
Invalid Domains:                  0
Websites Present:              2251
Invalid Website URLs:             0
Invalid Employee Values:          0
Invalid Revenue Values:           0
Invalid Null Placeholders:        0
```

**Quality Status:** PASS — no formatting or duplicate-domain errors detected.

Source-data exceptions were preserved rather than fabricated:

```text
companies_missing_domains.csv → 793 records
companies_missing_names.csv   → 60 records
```

## Twenty CRM Test Preparation

A clean 10-record test dataset was generated and validated against the required 10-column schema.

```text
Records: 10
Columns: 10
Schema correct: True
Missing names: 0
Missing domains: 0
Invalid domains: 0
```

The actual Twenty CRM schema verification and test import are **pending workspace access**.

## Commands Used

### Run Extraction and Validation

```bash
cd ~/hubspot-twenty-migration
source venv/bin/activate
python companies.py
python validate_companies.py
```

### Preview Extracted Companies

```bash
head -5 companies.csv
```

### Verify CSV Headers

```bash
python - <<'PY'
import csv

with open("companies.csv", encoding="utf-8-sig") as f:
    reader = csv.DictReader(f)
    for i, header in enumerate(reader.fieldnames, 1):
        print(f"{i}. {header}")
PY
```

### Verify Missing-Domain Records

Python's CSV parser was used instead of `wc -l` because CSV fields may contain embedded line breaks.

```bash
python - <<'PY'
import csv

with open("companies_missing_domains.csv", encoding="utf-8-sig") as f:
    print("Actual missing-domain records:", len(list(csv.DictReader(f))))
PY
```

Result:

```text
Actual missing-domain records: 793
```

### Git Workflow

```bash
git add .
git status
git commit -m "Update companies migration validation"
git push origin main
```

## Evidence

### Successful Companies Extraction

The HubSpot API returned **3,047 raw records**, producing **3,043 final Companies** after transformation and duplicate handling.

![Companies Extraction](evidence/companies-extraction-success.png)

### Final Validation

The final dataset passed the implemented formatting, duplicate, URL, numeric, and null-value checks.

![Companies Validation](evidence/companies-validation-report.png)

## Blockers & Resolutions

**HubSpot Authentication — Resolved:** Initial requests returned `401 INVALID_AUTHENTICATION`. Bearer authentication was verified and the API connection succeeded.

**WSL DNS — Resolved:** A temporary `name resolution` failure interrupted connectivity. WSL networking was restarted and connectivity restored.

**CSV Record Count — Resolved:** Physical line counts differed because of embedded line breaks. Python `csv.DictReader` confirmed **793 logical missing-domain records**.

**Twenty CRM Access — Pending:** The test dataset is locally validated, but destination schema verification and test import require Twenty CRM workspace access.

## Security

Sensitive credentials and generated CRM data are excluded from source control:

```gitignore
.env
venv/
__pycache__/
*.csv
```

The HubSpot token is loaded from the environment and is never hard-coded or committed.

## Project Structure

```text
hubspot-twenty-migration/
├── companies.py
├── validate_companies.py
├── README.md
├── .gitignore
└── evidence/
    ├── companies-extraction-success.png
    └── companies-validation-report.png
```

## Status

**Completed:** Companies extraction, transformation, normalization, deduplication, validation, exception reporting, and test-import preparation.

**Pending:** Twenty CRM workspace access for destination schema verification and test import.

---
**Author:** Jemimah Godswill  
**Project:** DATA-01 — HubSpot to Twenty CRM Migration  
**Component:** Companies Extraction, Transformation & Validation