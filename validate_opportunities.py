import csv
import os
import re
from collections import Counter
from decimal import Decimal, InvalidOperation
from datetime import datetime


# ============================================================
# CONFIGURATION
# ============================================================

OPPORTUNITIES_FILE = "opportunities.csv"
COMPANIES_FILE = "companies.csv"
EXCEPTIONS_FILE = "deal_company_exceptions.csv"

EXPECTED_HEADERS = [
    "name",
    "amount / Amount",
    "amount / Currency Code",
    "stage",
    "closeDate",
    "companyDomain",
]

COMPANY_DOMAIN_FIELD = "Domain / Domain URL"

INVALID_NULL_VALUES = {
    "null",
    "none",
    "n/a",
    "nan",
}

ISO_DATE_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T"
    r"\d{2}:\d{2}:\d{2}"
    r"\.\d{3}Z$"
)


# ============================================================
# HELPERS
# ============================================================

def clean_text(value):
    if value is None:
        return ""

    return str(value).strip()


def load_csv(path):
    if not os.path.exists(path):
        raise SystemExit(
            f"ERROR: Required file not found: {path}"
        )

    with open(
        path,
        encoding="utf-8-sig",
    ) as file:

        reader = csv.DictReader(file)

        headers = reader.fieldnames or []

        rows = list(reader)

    return headers, rows


def is_numeric(value):
    value = clean_text(value)

    if not value:
        return True

    try:
        number = Decimal(value)

        return number.is_finite()

    except InvalidOperation:
        return False


def is_valid_iso_date(value):
    value = clean_text(value)

    if not value:
        return True

    if not ISO_DATE_PATTERN.fullmatch(value):
        return False

    try:
        datetime.strptime(
            value,
            "%Y-%m-%dT%H:%M:%S.%fZ",
        )

        return True

    except ValueError:
        return False


# ============================================================
# LOAD OPPORTUNITIES
# ============================================================

opportunity_headers, opportunities = load_csv(
    OPPORTUNITIES_FILE
)

if not opportunities:
    raise SystemExit(
        "ERROR: opportunities.csv contains no Deal records."
    )


# ============================================================
# LOAD COMPANIES
# ============================================================

company_headers, companies = load_csv(
    COMPANIES_FILE
)

if COMPANY_DOMAIN_FIELD not in company_headers:
    raise SystemExit(
        "ERROR: companies.csv is missing "
        "'Domain / Domain URL'."
    )

company_domains = {
    clean_text(
        row.get(
            COMPANY_DOMAIN_FIELD
        )
    )
    for row in companies
    if clean_text(
        row.get(
            COMPANY_DOMAIN_FIELD
        )
    )
}


# ============================================================
# LOAD RELATIONSHIP EXCEPTIONS
# ============================================================

if os.path.exists(
    EXCEPTIONS_FILE
):
    _, exceptions = load_csv(
        EXCEPTIONS_FILE
    )
else:
    exceptions = []


# ============================================================
# SCHEMA VALIDATION
# ============================================================

schema_correct = (
    opportunity_headers
    == EXPECTED_HEADERS
)


# ============================================================
# NAME VALIDATION
# ============================================================

missing_names = [
    row
    for row in opportunities
    if not clean_text(
        row["name"]
    )
]


# ============================================================
# AMOUNT VALIDATION
# ============================================================

amounts_present = []

missing_amounts = []

invalid_amounts = []

for row in opportunities:

    amount = clean_text(
        row[
            "amount / Amount"
        ]
    )

    if not amount:

        missing_amounts.append(
            row
        )

        continue

    amounts_present.append(
        amount
    )

    if not is_numeric(
        amount
    ):

        invalid_amounts.append(
            amount
        )


# ============================================================
# CURRENCY VALIDATION
# ============================================================

currencies_present = [
    clean_text(
        row[
            "amount / Currency Code"
        ]
    )
    for row in opportunities
    if clean_text(
        row[
            "amount / Currency Code"
        ]
    )
]

missing_currencies = [
    row
    for row in opportunities
    if not clean_text(
        row[
            "amount / Currency Code"
        ]
    )
]

invalid_currency_codes = [
    currency
    for currency in currencies_present
    if not (
        len(currency) == 3
        and currency.isalpha()
        and currency.upper() == currency
    )
]


# ============================================================
# STAGE VALIDATION
# ============================================================

stages_present = [
    clean_text(
        row["stage"]
    )
    for row in opportunities
    if clean_text(
        row["stage"]
    )
]

missing_stages = [
    row
    for row in opportunities
    if not clean_text(
        row["stage"]
    )
]


# ============================================================
# CLOSE DATE VALIDATION
# ============================================================

close_dates_present = []

missing_close_dates = []

invalid_close_dates = []

for row in opportunities:

    close_date = clean_text(
        row["closeDate"]
    )

    if not close_date:

        missing_close_dates.append(
            row
        )

        continue

    close_dates_present.append(
        close_date
    )

    if not is_valid_iso_date(
        close_date
    ):

        invalid_close_dates.append(
            close_date
        )


# ============================================================
# NULL PLACEHOLDER VALIDATION
# ============================================================

null_issues = []

for row_number, row in enumerate(
    opportunities,
    start=2,
):

    for column, value in row.items():

        normalized = clean_text(
            value
        ).lower()

        if (
            normalized
            in INVALID_NULL_VALUES
        ):

            null_issues.append({
                "row":
                    row_number,

                "column":
                    column,

                "value":
                    value,
            })


# ============================================================
# DUPLICATE FULL ROW VALIDATION
# ============================================================

row_signatures = [
    tuple(
        clean_text(
            row.get(header)
        )
        for header
        in EXPECTED_HEADERS
    )
    for row in opportunities
]

row_counts = Counter(
    row_signatures
)

duplicate_full_rows = [
    signature
    for signature, count
    in row_counts.items()
    if count > 1
]


# ============================================================
# COMPANY RELATIONSHIP VALIDATION
# ============================================================

resolved_company_domains = []

unresolved_company_domains = []

invalid_company_domain_format = []

unmatched_company_domains = []

for row in opportunities:

    domain = clean_text(
        row["companyDomain"]
    )

    if not domain:

        unresolved_company_domains.append(
            row
        )

        continue

    resolved_company_domains.append(
        domain
    )

    if not domain.startswith(
        "https://"
    ):

        invalid_company_domain_format.append(
            domain
        )

    if domain not in company_domains:

        unmatched_company_domains.append(
            domain
        )


# ============================================================
# RELATIONSHIP RECONCILIATION
# ============================================================

resolved_count = len(
    resolved_company_domains
)

unresolved_count = len(
    unresolved_company_domains
)

exception_count = len(
    exceptions
)

relationship_reconciles = (
    unresolved_count
    == exception_count
)

total_reconciles = (
    resolved_count
    + unresolved_count
    == len(opportunities)
)


# ============================================================
# REPORT
# ============================================================

print(
    "=== Opportunities / Deals Validation Report ==="
)

print(
    "Total Deals:",
    len(opportunities),
)

print(
    "Columns:",
    len(opportunity_headers),
)

print(
    "Schema correct:",
    schema_correct,
)

print(
    "Missing deal names:",
    len(missing_names),
)

print(
    "Amounts present:",
    len(amounts_present),
)

print(
    "Missing amounts:",
    len(missing_amounts),
)

print(
    "Invalid numeric amounts:",
    len(invalid_amounts),
)

print(
    "Currency codes present:",
    len(currencies_present),
)

print(
    "Missing currency codes:",
    len(missing_currencies),
)

print(
    "Invalid currency-code format:",
    len(invalid_currency_codes),
)

print(
    "Stages present:",
    len(stages_present),
)

print(
    "Missing stages:",
    len(missing_stages),
)

print(
    "Close dates present:",
    len(close_dates_present),
)

print(
    "Missing close dates:",
    len(missing_close_dates),
)

print(
    "Invalid close-date format:",
    len(invalid_close_dates),
)

print(
    "Invalid null placeholders:",
    len(null_issues),
)

print(
    "Duplicate full rows:",
    len(duplicate_full_rows),
)


# ============================================================
# RELATIONSHIP REPORT
# ============================================================

print()
print(
    "=== Deal -> Company Relationship Validation ==="
)

print(
    "Resolved companyDomain:",
    resolved_count,
)

print(
    "Unresolved companyDomain:",
    unresolved_count,
)

print(
    "Invalid companyDomain format:",
    len(
        invalid_company_domain_format
    ),
)

print(
    "companyDomain not found in companies.csv:",
    len(
        unmatched_company_domains
    ),
)

print(
    "Relationship exception records:",
    exception_count,
)

print(
    "Relationship reconciliation correct:",
    relationship_reconciles,
)

print(
    "Total relationship count correct:",
    total_reconciles,
)


# ============================================================
# QUALITY STATUS
# ============================================================

critical_errors = (
    int(
        not schema_correct
    )
    + len(
        invalid_amounts
    )
    + len(
        invalid_currency_codes
    )
    + len(
        missing_stages
    )
    + len(
        invalid_close_dates
    )
    + len(
        null_issues
    )
    + len(
        duplicate_full_rows
    )
    + len(
        invalid_company_domain_format
    )
    + len(
        unmatched_company_domains
    )
    + int(
        not relationship_reconciles
    )
    + int(
        not total_reconciles
    )
)


print()
print(
    "=== Quality Status ==="
)

if critical_errors == 0:

    print(
        "PASS: No critical schema, formatting, "
        "duplicate, or relationship errors detected."
    )

else:

    print(
        "REVIEW REQUIRED:",
        critical_errors,
        "critical validation issue(s) detected."
    )


# ============================================================
# KNOWN BLOCKER / SOURCE-DATA EXCEPTIONS
# ============================================================

print()
print(
    "=== Known Blockers / Source-Data Exceptions ==="
)

print(
    "Missing deal names:",
    len(missing_names),
)

print(
    "Missing amounts:",
    len(missing_amounts),
)

print(
    "Missing close dates:",
    len(missing_close_dates),
)

print(
    "Deals without resolved companyDomain:",
    unresolved_count,
)

print(
    "Missing currency codes:",
    len(missing_currencies),
)

if len(missing_currencies) == len(opportunities):

    print(
        "Currency status: PENDING — "
        "HubSpot currency settings could not be "
        "verified with the current token scope."
    )

else:

    print(
        "Currency status: PARTIALLY AVAILABLE"
    )

print()
print(
    "NOTE: HubSpot stage labels are locally resolved, "
    "but exact Twenty CRM stage-name matching remains "
    "pending Twenty CRM workspace access."
)
