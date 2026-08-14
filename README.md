# HubSpot to Twenty CRM — Companies Migration

## Overview

This project implements the **Companies** component of a HubSpot-to-Twenty CRM data migration.

The workflow extracts Company records from HubSpot, transforms them into the required Twenty CRM schema, validates data quality, and generates CSV output for the next migration stage.

### Workflow

```text
HubSpot API
    ↓
Extract Companies
    ↓
Transform & Normalize
    ↓
Validate
    ↓
companies.csv
    ↓
Twenty CRM
```

## Scope

This component covers:

- HubSpot Companies API extraction
- API pagination
- Twenty CRM field mapping
- Domain and URL normalization
- Numeric field validation
- Duplicate detection
- Missing-value handling
- CSV generation and validation

Contacts and Deals are outside the scope of this component.

## Field Mapping

| HubSpot | Twenty CRM |
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

`companies.py` authenticates with HubSpot, retrieves Companies through pagination, transforms the required fields, normalizes populated URLs, cleans numeric values, removes duplicate populated domains, and generates `companies.csv`.

`validate_companies.py` performs independent quality checks and generates `companies_missing_domains.csv` for records requiring domain review.

## Validation Results

| Check | Result |
|---|---:|
| Total Companies | **3,043** |
| Companies with Domain | **2,250** |
| Missing Domains | **793** |
| Duplicate Domains | **0** |
| Invalid Domains | **0** |
| Invalid Employee Values | **0** |
| Invalid Revenue Values | **0** |

Missing domains were **not fabricated or silently removed**. The 793 affected records were retained for review.

## Blockers & Resolutions

### Authentication

Initial HubSpot requests returned `401 INVALID_AUTHENTICATION`. The authentication method and working request format were verified, and the API connection succeeded using Bearer authentication.

```text
Authorization: Bearer <ACCESS_TOKEN>
```

### WSL Network Resolution

WSL temporarily returned:

```text
Temporary failure in name resolution
```

WSL was restarted and connectivity verified with:

```bash
ping -c 3 google.com
```

API connectivity was restored successfully.

### CSV Record Verification

`wc -l` produced a higher physical line count for the missing-domain CSV because some CSV fields contained embedded line breaks.

Python's CSV parser was therefore used to verify the actual number of records:

```bash
python - <<'PY'
import csv
with open("companies_missing_domains.csv", encoding="utf-8-sig") as f:
    print("Actual records:", len(list(csv.DictReader(f))))
PY
```

Result: **793 records**.

## Evidence

### Successful Extraction

The API returned **3,047 raw records**, producing **3,043 final Companies** after transformation and duplicate handling.

![Companies Extraction](evidence/companies-extraction-success.png)

### Validation

The final dataset passed the implemented domain, duplicate, employee, and revenue validation checks.

![Companies Validation](evidence/companies-validation-report.png)

## Run & Verify

```bash
# Activate environment
source venv/bin/activate

# Extract and transform
python companies.py

# Preview Companies
head -5 companies.csv

# Run validation
python validate_companies.py
```

Expected validation:

```text
Total companies: 3043
Companies with domain: 2250
Missing domains: 793
Duplicate domains: 0
Invalid domains: 0
Invalid employee values: 0
Invalid revenue values: 0
```

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

## Security

Credentials and CRM exports are excluded from Git:

```text
.env
venv/
__pycache__/
*.csv
```

The HubSpot access token is loaded from the environment and is never hard-coded or committed.

## Status

**Companies extraction, transformation, and validation completed successfully.**

The final dataset contains **3,043 Companies**. **793 missing-domain records** are documented separately for review before the final Twenty CRM import.

---
**Author:** Jemimah Godswill  
**Component:** Companies Extraction, Transformation & Validation
