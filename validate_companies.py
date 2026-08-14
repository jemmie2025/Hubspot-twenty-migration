import csv
from collections import Counter

FILE = "companies.csv"

# Read companies.csv
with open(FILE, encoding="utf-8-sig") as f:
    rows = list(csv.DictReader(f))

# Domain validation
domains = [
    row["Domain / Domain URL"].strip().lower()
    for row in rows
    if row["Domain / Domain URL"].strip()
]

domain_counts = Counter(domains)

duplicate_domains = [
    domain
    for domain, count in domain_counts.items()
    if count > 1
]

missing_domains = [
    row
    for row in rows
    if not row["Domain / Domain URL"].strip()
]

invalid_domains = [
    domain
    for domain in domains
    if not domain.startswith("https://")
]

# Numeric validation
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

# Print validation report
print("=== Companies Validation Report ===")
print("Total companies:", len(rows))
print("Companies with domain:", len(domains))
print("Missing domains:", len(missing_domains))
print("Duplicate domains:", len(duplicate_domains))
print("Invalid domains:", len(invalid_domains))
print("Invalid employee values:", invalid_employees)
print("Invalid revenue values:", invalid_revenue)

# Export companies with missing domains
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
        f"Missing-domain report created: "
        f"{len(missing_domains)} records"
    )
else:
    print("No companies with missing domains found.")
