import csv
from collections import Counter

FILE = "companies.csv"

# --------------------------------
# Load Companies CSV
# --------------------------------
with open(FILE, encoding="utf-8-sig") as f:
    reader = csv.DictReader(f)
    rows = list(reader)

if not rows:
    raise SystemExit("ERROR: companies.csv contains no company records.")

# --------------------------------
# Company Name Validation
# --------------------------------
missing_names = [
    row for row in rows
    if not row["name"].strip()
]

# --------------------------------
# Domain Validation
# --------------------------------
domains = [
    row["Domain / Domain URL"].strip().lower()
    for row in rows
    if row["Domain / Domain URL"].strip()
]

missing_domains = [
    row for row in rows
    if not row["Domain / Domain URL"].strip()
]

domain_counts = Counter(domains)

duplicate_domains = [
    domain
    for domain, count in domain_counts.items()
    if count > 1
]

invalid_domains = [
    domain
    for domain in domains
    if not domain.startswith("https://")
]

# --------------------------------
# Website URL Validation
# --------------------------------
websites = [
    row["Links / Primary Link URL"].strip()
    for row in rows
    if row["Links / Primary Link URL"].strip()
]

invalid_websites = [
    website
    for website in websites
    if not (
        website.startswith("https://")
        or website.startswith("http://")
    )
]

# --------------------------------
# Numeric Field Validation
# --------------------------------
invalid_employees = 0
invalid_revenue = 0

for row in rows:
    employees = row["employees"].strip()
    revenue = row["annualRevenue / Amount"].strip()

    if employees:
        try:
            int(employees)
        except ValueError:
            invalid_employees += 1

    if revenue:
        try:
            float(revenue)
        except ValueError:
            invalid_revenue += 1

# --------------------------------
# Null Placeholder Validation
# --------------------------------
invalid_null_values = {"null", "n/a", "none", "nan"}
null_issues = []

for row_number, row in enumerate(rows, start=2):
    for column, value in row.items():
        if value and value.strip().lower() in invalid_null_values:
            null_issues.append(
                (row_number, column, value)
            )

# --------------------------------
# Missing Data Overlap Analysis
# --------------------------------
missing_both_name_domain = [
    row for row in rows
    if not row["name"].strip()
    and not row["Domain / Domain URL"].strip()
]

missing_name_domain_available = [
    row for row in rows
    if not row["name"].strip()
    and row["Domain / Domain URL"].strip()
]

# --------------------------------
# Validation Summary
# --------------------------------
print("=== Companies Validation Report ===")
print("Total companies:", len(rows))
print("Missing company names:", len(missing_names))
print("Companies with domain:", len(domains))
print("Missing domains:", len(missing_domains))
print("Duplicate domains:", len(duplicate_domains))
print("Invalid domains:", len(invalid_domains))
print("Websites present:", len(websites))
print("Invalid website URLs:", len(invalid_websites))
print("Invalid employee values:", invalid_employees)
print("Invalid revenue values:", invalid_revenue)
print("Invalid null placeholders:", len(null_issues))

print()
print("=== Missing Data Analysis ===")
print(
    "Missing BOTH name and domain:",
    len(missing_both_name_domain)
)
print(
    "Missing name but domain available:",
    len(missing_name_domain_available)
)

# --------------------------------
# Export Missing-Domain Report
# --------------------------------
if missing_domains:
    with open(
        "companies_missing_domains.csv",
        "w",
        newline="",
        encoding="utf-8-sig"
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=rows[0].keys()
        )
        writer.writeheader()
        writer.writerows(missing_domains)

    print(
        f"\nMissing-domain report created: "
        f"{len(missing_domains)} records"
    )

# --------------------------------
# Export Missing-Name Report
# --------------------------------
if missing_names:
    with open(
        "companies_missing_names.csv",
        "w",
        newline="",
        encoding="utf-8-sig"
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=rows[0].keys()
        )
        writer.writeheader()
        writer.writerows(missing_names)

    print(
        f"Missing-name report created: "
        f"{len(missing_names)} records"
    )

# --------------------------------
# Final Quality Status
# --------------------------------
critical_format_errors = (
    len(duplicate_domains)
    + len(invalid_domains)
    + len(invalid_websites)
    + invalid_employees
    + invalid_revenue
    + len(null_issues)
)

print()
print("=== Quality Status ===")

if critical_format_errors == 0:
    print("PASS: No formatting or duplicate-domain errors detected.")
else:
    print(
        "REVIEW REQUIRED:",
        critical_format_errors,
        "formatting/data-quality errors detected."
    )

print(
    "Source-data exceptions:",
    len(missing_names),
    "missing names and",
    len(missing_domains),
    "missing domains."
)





















