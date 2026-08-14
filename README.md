# HubSpot to Twenty CRM — Companies Migration

## Overview

This project implements the **Companies** component of the DATA-01 HubSpot-to-Twenty CRM migration.

The workflow extracts Company records from HubSpot, transforms them into the required Twenty CRM schema, validates data quality, and generates clean CSV outputs for migration.

```text
HubSpot API → Extract → Transform → Validate → CSV → Twenty CRM
```

## Scope

The Companies workflow covers:

- HubSpot API extraction with pagination
- Twenty CRM field mapping
- Domain and website normalization
- Duplicate-domain detection
- Numeric field validation
- Null-value cleaning
- Missing-data analysis
- Exception reporting
- Test-import preparation

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

`companies.py` retrieves Companies through HubSpot API pagination, maps the required properties, normalizes URLs and numeric values, removes duplicate populated domains, preserves missing values as blanks, and generates `companies.csv`.

`validate_companies.py` performs automated quality checks and generates exception reports for missing names and domains.

## Final Validation

```text
=== Companies Validation Report ===
Total companies: 3043
Missing company names: 60
Companies with domain: 2250
Missing domains: 793
Duplicate domains: 0
Invalid domains: 0
Websites present: 2251
Invalid website URLs: 0
Invalid employee values: 0
Invalid revenue values: 0
Invalid null placeholders: 0

=== Missing Data Analysis ===
Missing BOTH name and domain: 30
Missing name but domain available: 30

=== Quality Status ===
PASS: No formatting or duplicate-domain errors detected.
```

Source-data exceptions were preserved rather than replaced with fabricated values:

- `companies_missing_domains.csv` — **793 records**
- `companies_missing_names.csv` — **60 records**

## Twenty CRM Test Preparation

A 10-record `companies_test_import.csv` was prepared and locally validated:

```text
Records: 10
Columns: 10
Schema correct: True
Missing names: 0
Missing domains: 0
Invalid domains: 0
```

The actual Twenty CRM schema verification and test import are **pending workspace access**.

## Blockers & Resolutions

### HubSpot Authentication
Initial API requests returned a `401` authentication error. The Bearer authentication configuration was verified and corrected, after which HubSpot extraction succeeded.

### WSL DNS
A temporary `name resolution` error interrupted API connectivity. WSL networking was restarted and connectivity verified before continuing.

### Twenty CRM Access
The migration task requires destination-side schema verification and a test import. The test CSV is ready, but the actual import is pending access to the Twenty CRM workspace.

## Evidence

### Successful Companies Extraction

The extraction retrieved **3,047 raw records** and produced **3,043 final Companies** after transformation and duplicate handling.

![Companies Extraction](evidence/companies-extraction-success.png)

### Validation Evidence

![Companies Validation](evidence/companies-validation-report.png)

## Run & Verify

```bash
source venv/bin/activate
python companies.py
python validate_companies.py
```

Preview the output:

```bash
head -5 companies.csv
```

## Security

Sensitive credentials and CRM exports are excluded from Git:

```text
.env
venv/
__pycache__/
*.csv
```

The HubSpot access token is loaded from the environment and is never hard-coded or committed.

## Status

**Companies extraction, transformation, cleaning, validation, exception reporting, and test-import preparation are complete.**

Twenty CRM destination verification and test import remain pending workspace access.

---
**Author:** Jemimah Godswill  
**Component:** Companies Extraction, Transformation & Validate.