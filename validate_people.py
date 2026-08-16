import csv
import os
import re
from collections import Counter

import pycountry


# ============================================================
# CONFIGURATION
# ============================================================

PEOPLE_FILE = "people.csv"
COMPANIES_FILE = "companies.csv"
EXCEPTIONS_FILE = "people_company_exceptions.csv"

EXPECTED_HEADERS = [
    "firstName",
    "lastName",
    "email",
    "Phones / Primary Phone Number",
    "Phones / Primary Phone Country Code",
    "jobTitle",
    "companyDomain",
]

COMPANY_DOMAIN_FIELD = "Domain / Domain URL"

INVALID_NULL_VALUES = {
    "null",
    "none",
    "n/a",
    "nan",
}

EMAIL_PATTERN = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+"
    r"@[A-Za-z0-9-]+"
    r"(?:\.[A-Za-z0-9-]+)+$"
)

VALID_ISO_COUNTRY_CODES = {
    country.alpha_2
    for country in pycountry.countries
}


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


# ============================================================
# LOAD PEOPLE
# ============================================================

people_headers, people = load_csv(
    PEOPLE_FILE
)

if not people:
    raise SystemExit(
        "ERROR: people.csv contains no Contact records."
    )


# ============================================================
# SCHEMA VALIDATION
# ============================================================

schema_correct = (
    people_headers
    == EXPECTED_HEADERS
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
# NAME COMPLETENESS
# ============================================================

missing_first_names = [
    row
    for row in people
    if not clean_text(
        row["firstName"]
    )
]

missing_last_names = [
    row
    for row in people
    if not clean_text(
        row["lastName"]
    )
]

missing_both_names = [
    row
    for row in people
    if (
        not clean_text(
            row["firstName"]
        )
        and not clean_text(
            row["lastName"]
        )
    )
]


# ============================================================
# EMAIL VALIDATION
# ============================================================

emails = [
    clean_text(
        row["email"]
    )
    for row in people
    if clean_text(
        row["email"]
    )
]

missing_emails = [
    row
    for row in people
    if not clean_text(
        row["email"]
    )
]

invalid_emails = [
    email
    for email in emails
    if not EMAIL_PATTERN.fullmatch(
        email
    )
]

non_lowercase_emails = [
    email
    for email in emails
    if email != email.lower()
]

normalized_emails = [
    email.lower()
    for email in emails
]

email_counts = Counter(
    normalized_emails
)

duplicate_emails = [
    email
    for email, count
    in email_counts.items()
    if count > 1
]


# ============================================================
# PHONE VALIDATION
# ============================================================

phones_present = []
invalid_phone_values = []

country_codes_present = []
invalid_country_codes = []

for row in people:

    phone = clean_text(
        row[
            "Phones / Primary Phone Number"
        ]
    )

    country_code = clean_text(
        row[
            "Phones / Primary Phone Country Code"
        ]
    )

    if phone:

        phones_present.append(
            phone
        )

        # Jira requirement:
        # digits only
        if not phone.isdigit():

            invalid_phone_values.append(
                phone
            )

    if country_code:

        country_codes_present.append(
            country_code
        )

        # Jira requirement:
        # two-letter ISO code
        if (
            country_code
            not in VALID_ISO_COUNTRY_CODES
        ):

            invalid_country_codes.append(
                country_code
            )


# ============================================================
# NULL PLACEHOLDER VALIDATION
# ============================================================

null_issues = []

for row_number, row in enumerate(
    people,
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
# DUPLICATE FULL ROWS
# ============================================================

row_signatures = [
    tuple(
        clean_text(
            row.get(header)
        )
        for header
        in EXPECTED_HEADERS
    )
    for row in people
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

missing_company_domains = []

invalid_company_domain_format = []

unmatched_company_domains = []

for row in people:

    domain = clean_text(
        row["companyDomain"]
    )

    if not domain:

        missing_company_domains.append(
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

    # Jira requires the Contact foreign key
    # to match an actual Company domain.
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
    missing_company_domains
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
    == len(people)
)


# ============================================================
# REPORT
# ============================================================

print(
    "=== People / Contacts Validation Report ==="
)

print(
    "Total Contacts:",
    len(people),
)

print(
    "Columns:",
    len(people_headers),
)

print(
    "Schema correct:",
    schema_correct,
)

print(
    "Missing first names:",
    len(missing_first_names),
)

print(
    "Missing last names:",
    len(missing_last_names),
)

print(
    "Missing BOTH names:",
    len(missing_both_names),
)

print(
    "Missing emails:",
    len(missing_emails),
)

print(
    "Invalid populated emails:",
    len(invalid_emails),
)

print(
    "Non-lowercase emails:",
    len(non_lowercase_emails),
)

print(
    "Duplicate populated emails:",
    len(duplicate_emails),
)

print(
    "Contacts with phone numbers:",
    len(phones_present),
)

print(
    "Invalid phone values:",
    len(invalid_phone_values),
)

print(
    "Phone country codes present:",
    len(country_codes_present),
)

print(
    "Invalid ISO country codes:",
    len(invalid_country_codes),
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
    "=== Contact -> Company Relationship Validation ==="
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
        invalid_emails
    )
    + len(
        non_lowercase_emails
    )
    + len(
        duplicate_emails
    )
    + len(
        invalid_phone_values
    )
    + len(
        invalid_country_codes
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
# SOURCE-DATA EXCEPTIONS
# ============================================================

print()
print(
    "=== Source-Data Exceptions ==="
)

print(
    "Missing first names:",
    len(
        missing_first_names
    ),
)

print(
    "Missing last names:",
    len(
        missing_last_names
    ),
)

print(
    "Missing emails:",
    len(
        missing_emails
    ),
)

print(
    "Contacts without resolved companyDomain:",
    unresolved_count,
)
