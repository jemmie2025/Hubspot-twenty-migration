import os
import csv
import json
import urllib.parse
import urllib.request
import urllib.error
from dotenv import load_dotenv

load_dotenv(override=True)

TOKEN = os.getenv("HUBSPOT_ACCESS_TOKEN")

if not TOKEN:
    raise SystemExit("HUBSPOT_ACCESS_TOKEN was not found in .env")

BASE = "https://api.hubapi.com"

HEADERS = {
    "Authorization": "Bearer " + TOKEN.strip(),
    "Accept": "application/json",
}

PROPERTIES = [
    "name",
    "domain",
    "website",
    "address",
    "city",
    "state",
    "zip",
    "country",
    "numberofemployees",
    "annualrevenue",
]


def get_companies():
    records = []
    after = None

    while True:
        params = {
            "limit": 100,
            "archived": "false",
            "properties": ",".join(PROPERTIES),
        }

        if after:
            params["after"] = after

        url = (
            BASE
            + "/crm/v3/objects/companies?"
            + urllib.parse.urlencode(params)
        )

        request = urllib.request.Request(
            url,
            headers=HEADERS,
            method="GET",
        )

        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                data = json.loads(response.read().decode("utf-8"))

        except urllib.error.HTTPError as error:
            message = error.read().decode("utf-8", "replace")
            raise SystemExit(f"HTTP {error.code}: {message}")

        records.extend(data.get("results", []))

        after = (
            data.get("paging", {})
            .get("next", {})
            .get("after")
        )

        print(f"Companies fetched: {len(records)}")

        if not after:
            break

    return records


def clean_text(value):
    if value is None:
        return ""

    value = str(value).strip()

    if value.lower() in {"null", "none", "n/a", "nan"}:
        return ""

    return value


def format_domain(value):
    value = clean_text(value)

    if not value:
        return ""

    value = value.rstrip("/")

    if value.startswith("http://"):
        value = "https://" + value[7:]
    elif not value.startswith("https://"):
        value = "https://" + value

    return value


def format_website(value):
    value = clean_text(value)

    if not value:
        return ""

    if not value.startswith(("http://", "https://")):
        value = "https://" + value

    return value


def clean_integer(value):
    value = clean_text(value)

    if not value:
        return ""

    try:
        return int(float(value))
    except ValueError:
        return ""


def clean_decimal(value):
    value = clean_text(value)

    if not value:
        return ""

    try:
        return float(value)
    except ValueError:
        return ""


def transform(records):
    companies = []

    for record in records:
        p = record.get("properties", {})

        companies.append({
            "name": clean_text(p.get("name")),
            "Domain / Domain URL": format_domain(p.get("domain")),
            "Links / Primary Link URL": format_website(p.get("website")),
            "Address / Address 1": clean_text(p.get("address")),
            "Address / City": clean_text(p.get("city")),
            "Address / State": clean_text(p.get("state")),
            "Address / Post Code": clean_text(p.get("zip")),
            "Address / Country": clean_text(p.get("country")),
            "employees": clean_integer(p.get("numberofemployees")),
            "annualRevenue / Amount": clean_decimal(p.get("annualrevenue")),
        })

    return companies


def deduplicate(companies):
    seen = set()
    result = []

    for company in companies:
        domain = company["Domain / Domain URL"].lower()

        if domain and domain in seen:
            continue

        if domain:
            seen.add(domain)

        result.append(company)

    return result


def export_csv(companies):
    fields = [
        "name",
        "Domain / Domain URL",
        "Links / Primary Link URL",
        "Address / Address 1",
        "Address / City",
        "Address / State",
        "Address / Post Code",
        "Address / Country",
        "employees",
        "annualRevenue / Amount",
    ]

    with open(
        "companies.csv",
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(companies)


def main():
    print("Extracting Companies from HubSpot...")

    raw = get_companies()
    cleaned = transform(raw)
    final = deduplicate(cleaned)

    export_csv(final)

    print(f"Raw Companies: {len(raw)}")
    print(f"Final Companies: {len(final)}")
    print("companies.csv created successfully.")


if __name__ == "__main__":
    main()
