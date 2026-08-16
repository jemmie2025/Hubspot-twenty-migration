import os
import csv
import json
import time
import socket
import urllib.parse
import urllib.request
import urllib.error

from dotenv import load_dotenv


# ============================================================
# CONFIGURATION
# ============================================================

load_dotenv(override=True)

TOKEN = os.getenv("HUBSPOT_ACCESS_TOKEN")

if not TOKEN:
    raise SystemExit(
        "ERROR: HUBSPOT_ACCESS_TOKEN was not found in .env"
    )

BASE_URL = "https://api.hubapi.com"

HEADERS = {
    "Authorization": "Bearer " + TOKEN.strip(),
    "Accept": "application/json",
    "Content-Type": "application/json",
}

DEALS_FILE = "deals_stage1.csv"
COMPANIES_FILE = "companies.csv"

OUTPUT_FILE = "opportunities.csv"
EXCEPTIONS_FILE = "deal_company_exceptions.csv"

MAX_RETRIES = 6


# ============================================================
# HTTP
# ============================================================

def api_post(path, body):
    url = BASE_URL + path
    payload = json.dumps(body).encode("utf-8")

    for attempt in range(MAX_RETRIES):
        request = urllib.request.Request(
            url,
            headers=HEADERS,
            data=payload,
            method="POST",
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=90,
            ) as response:
                return json.loads(
                    response.read().decode("utf-8")
                )

        except urllib.error.HTTPError as error:
            status = error.code
            message = error.read().decode(
                "utf-8",
                "replace",
            )

            if status == 429 or 500 <= status < 600:
                delay = min(
                    60,
                    2 ** attempt,
                )

                print(
                    f"Temporary HubSpot error {status}. "
                    f"Retrying in {delay}s..."
                )

                time.sleep(delay)
                continue

            raise SystemExit(
                f"HubSpot API error {status}: "
                f"{message[:500]}"
            )

        except (
            urllib.error.URLError,
            TimeoutError,
            socket.timeout,
        ) as error:
            delay = min(
                60,
                2 ** attempt,
            )

            print(
                f"Network error: {error}. "
                f"Retrying in {delay}s..."
            )

            time.sleep(delay)

    raise SystemExit(
        "ERROR: HubSpot request failed after maximum retries."
    )


# ============================================================
# HELPERS
# ============================================================

def clean_text(value):
    if value is None:
        return ""

    return str(value).strip()


def chunks(items, size):
    for i in range(
        0,
        len(items),
        size,
    ):
        yield items[i:i + size]


def parse_company_ids(value):
    ids = []
    seen = set()

    for item in clean_text(
        value
    ).split(";"):
        company_id = item.strip()

        if (
            company_id
            and company_id not in seen
        ):
            seen.add(company_id)
            ids.append(company_id)

    return ids


def canonical_domain_key(value):
    value = clean_text(
        value
    ).lower()

    if not value:
        return ""

    if "://" not in value:
        value = "https://" + value

    parsed = urllib.parse.urlparse(
        value
    )

    host = (
        parsed.hostname
        or ""
    ).lower().strip(".")

    if host.startswith("www."):
        host = host[4:]

    return host


# ============================================================
# LOAD DEALS
# ============================================================

def load_deals():
    with open(
        DEALS_FILE,
        encoding="utf-8-sig",
    ) as file:
        rows = list(
            csv.DictReader(file)
        )

    if not rows:
        raise SystemExit(
            f"ERROR: {DEALS_FILE} contains no records."
        )

    required = {
        "_hubspotDealId",
        "_associatedCompanyIds",
        "name",
        "amount / Amount",
        "amount / Currency Code",
        "stage",
        "closeDate",
    }

    missing = (
        required
        - set(rows[0].keys())
    )

    if missing:
        raise SystemExit(
            "ERROR: Missing Deals columns: "
            + ", ".join(
                sorted(missing)
            )
        )

    deal_ids = []

    for row in rows:
        deal_id = clean_text(
            row.get(
                "_hubspotDealId"
            )
        )

        if not deal_id:
            raise SystemExit(
                "ERROR: Deal record missing HubSpot ID."
            )

        deal_ids.append(
            deal_id
        )

    if len(
        deal_ids
    ) != len(
        set(deal_ids)
    ):
        raise SystemExit(
            "ERROR: Duplicate HubSpot Deal IDs detected."
        )

    return rows


# ============================================================
# LOAD FINAL COMPANY DOMAINS
# ============================================================

def load_company_domain_reference():
    with open(
        COMPANIES_FILE,
        encoding="utf-8-sig",
    ) as file:
        rows = list(
            csv.DictReader(file)
        )

    if not rows:
        raise SystemExit(
            f"ERROR: {COMPANIES_FILE} contains no records."
        )

    field = "Domain / Domain URL"

    if field not in rows[0]:
        raise SystemExit(
            f"ERROR: Missing '{field}' "
            f"in {COMPANIES_FILE}."
        )

    domain_map = {}
    ambiguous_keys = set()

    for row in rows:
        exact_domain = clean_text(
            row.get(field)
        )

        key = canonical_domain_key(
            exact_domain
        )

        if not key:
            continue

        if (
            key in domain_map
            and domain_map[key]
            != exact_domain
        ):
            ambiguous_keys.add(
                key
            )

        else:
            domain_map[
                key
            ] = exact_domain

    for key in ambiguous_keys:
        domain_map.pop(
            key,
            None,
        )

    return (
        domain_map,
        ambiguous_keys,
    )


# ============================================================
# CLASSIFY DEAL -> COMPANY ASSOCIATIONS
# ============================================================

def classify_associations(deals):
    selected = {}
    no_association = set()
    ambiguous = {}

    for deal in deals:
        deal_id = clean_text(
            deal[
                "_hubspotDealId"
            ]
        )

        company_ids = parse_company_ids(
            deal[
                "_associatedCompanyIds"
            ]
        )

        if not company_ids:
            no_association.add(
                deal_id
            )

        elif len(
            company_ids
        ) == 1:
            selected[
                deal_id
            ] = company_ids[0]

        else:
            ambiguous[
                deal_id
            ] = company_ids

    return (
        selected,
        no_association,
        ambiguous,
    )


# ============================================================
# FETCH COMPANY RECORDS
# ============================================================

def fetch_company_records(company_ids):
    lookup = {}

    unique_ids = sorted(
        set(company_ids)
    )

    for batch in chunks(
        unique_ids,
        100,
    ):
        body = {
            "properties": [
                "domain",
                "name",
            ],
            "inputs": [
                {
                    "id": company_id
                }
                for company_id
                in batch
            ],
        }

        data = api_post(
            "/crm/v3/objects/"
            "companies/batch/read",
            body,
        )

        for company in data.get(
            "results",
            [],
        ):
            company_id = clean_text(
                company.get(
                    "id"
                )
            )

            properties = (
                company.get(
                    "properties"
                )
                or {}
            )

            if company_id:
                lookup[
                    company_id
                ] = {
                    "name":
                        clean_text(
                            properties.get(
                                "name"
                            )
                        ),
                    "domain":
                        clean_text(
                            properties.get(
                                "domain"
                            )
                        ),
                }

        print(
            "Company records resolved:",
            len(lookup),
        )

    return lookup


# ============================================================
# BUILD OPPORTUNITIES
# ============================================================

def build_opportunities(
    deals,
    selected_companies,
    no_association,
    ambiguous_associations,
    company_lookup,
    final_domain_map,
    ambiguous_domain_keys,
):
    opportunities = []
    exceptions = []

    for deal in deals:
        deal_id = clean_text(
            deal[
                "_hubspotDealId"
            ]
        )

        company_domain = ""

        if deal_id in no_association:
            exceptions.append({
                "_hubspotDealId":
                    deal_id,
                "name":
                    clean_text(
                        deal.get(
                            "name"
                        )
                    ),
                "reason":
                    "No Company association",
                "companyId":
                    "",
                "companyName":
                    "",
                "hubspotDomain":
                    "",
                "candidateCompanyIds":
                    "",
            })

        elif deal_id in ambiguous_associations:
            exceptions.append({
                "_hubspotDealId":
                    deal_id,
                "name":
                    clean_text(
                        deal.get(
                            "name"
                        )
                    ),
                "reason":
                    "Multiple Company associations; "
                    "no unique Company selected",
                "companyId":
                    "",
                "companyName":
                    "",
                "hubspotDomain":
                    "",
                "candidateCompanyIds":
                    ";".join(
                        ambiguous_associations[
                            deal_id
                        ]
                    ),
            })

        else:
            company_id = clean_text(
                selected_companies.get(
                    deal_id
                )
            )

            company = company_lookup.get(
                company_id
            )

            if not company:
                exceptions.append({
                    "_hubspotDealId":
                        deal_id,
                    "name":
                        clean_text(
                            deal.get(
                                "name"
                            )
                        ),
                    "reason":
                        "Associated Company "
                        "could not be retrieved",
                    "companyId":
                        company_id,
                    "companyName":
                        "",
                    "hubspotDomain":
                        "",
                    "candidateCompanyIds":
                        "",
                })

            else:
                hubspot_domain = (
                    company[
                        "domain"
                    ]
                )

                key = canonical_domain_key(
                    hubspot_domain
                )

                reason = ""

                if not key:
                    reason = (
                        "Associated Company "
                        "has no domain"
                    )

                elif (
                    key
                    in ambiguous_domain_keys
                ):
                    reason = (
                        "Company domain is ambiguous "
                        "in final companies.csv"
                    )

                elif (
                    key
                    not in final_domain_map
                ):
                    reason = (
                        "Company domain not present "
                        "in final companies.csv"
                    )

                else:
                    company_domain = (
                        final_domain_map[
                            key
                        ]
                    )

                if reason:
                    exceptions.append({
                        "_hubspotDealId":
                            deal_id,
                        "name":
                            clean_text(
                                deal.get(
                                    "name"
                                )
                            ),
                        "reason":
                            reason,
                        "companyId":
                            company_id,
                        "companyName":
                            company[
                                "name"
                            ],
                        "hubspotDomain":
                            hubspot_domain,
                        "candidateCompanyIds":
                            "",
                    })

        opportunities.append({
            "name":
                clean_text(
                    deal.get(
                        "name"
                    )
                ),
            "amount / Amount":
                clean_text(
                    deal.get(
                        "amount / Amount"
                    )
                ),
            "amount / Currency Code":
                clean_text(
                    deal.get(
                        "amount / Currency Code"
                    )
                ),
            "stage":
                clean_text(
                    deal.get(
                        "stage"
                    )
                ),
            "closeDate":
                clean_text(
                    deal.get(
                        "closeDate"
                    )
                ),
            "companyDomain":
                company_domain,
        })

    return (
        opportunities,
        exceptions,
    )


# ============================================================
# WRITE OUTPUTS
# ============================================================

def write_opportunities(rows):
    fields = [
        "name",
        "amount / Amount",
        "amount / Currency Code",
        "stage",
        "closeDate",
        "companyDomain",
    ]

    with open(
        OUTPUT_FILE,
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=fields,
        )

        writer.writeheader()
        writer.writerows(
            rows
        )


def write_exceptions(rows):
    fields = [
        "_hubspotDealId",
        "name",
        "reason",
        "companyId",
        "companyName",
        "hubspotDomain",
        "candidateCompanyIds",
    ]

    with open(
        EXCEPTIONS_FILE,
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=fields,
        )

        writer.writeheader()
        writer.writerows(
            rows
        )


# ============================================================
# MAIN
# ============================================================

def main():
    print(
        "Loading Deals Stage 1 data..."
    )

    deals = load_deals()

    print(
        "Deals loaded:",
        len(deals),
    )

    print(
        "Loading final Companies domain reference..."
    )

    (
        final_domain_map,
        ambiguous_domain_keys,
    ) = load_company_domain_reference()

    print(
        "Usable Company domain keys:",
        len(final_domain_map),
    )

    (
        selected_companies,
        no_association,
        ambiguous_associations,
    ) = classify_associations(
        deals
    )

    print()
    print(
        "Deals with one Company:",
        len(selected_companies),
    )

    print(
        "Deals without Company association:",
        len(no_association),
    )

    print(
        "Deals with multiple Companies:",
        len(ambiguous_associations),
    )

    company_ids = list(
        selected_companies.values()
    )

    print(
        "Unique selected Company IDs:",
        len(set(company_ids)),
    )

    print(
        "Retrieving selected Company domains..."
    )

    company_lookup = (
        fetch_company_records(
            company_ids
        )
    )

    (
        opportunities,
        exceptions,
    ) = build_opportunities(
        deals,
        selected_companies,
        no_association,
        ambiguous_associations,
        company_lookup,
        final_domain_map,
        ambiguous_domain_keys,
    )

    write_opportunities(
        opportunities
    )

    write_exceptions(
        exceptions
    )

    resolved = sum(
        bool(
            row[
                "companyDomain"
            ]
        )
        for row in opportunities
    )

    print()
    print(
        "=== Deal -> Company Resolution Report ==="
    )

    print(
        "Total Deals:",
        len(opportunities),
    )

    print(
        "Deals with resolved companyDomain:",
        resolved,
    )

    print(
        "Deals without resolved companyDomain:",
        len(opportunities)
        - resolved,
    )

    print(
        "Relationship exceptions:",
        len(exceptions),
    )

    print()
    print(
        f"{OUTPUT_FILE} created successfully."
    )

    print(
        f"{EXCEPTIONS_FILE} created: "
        f"{len(exceptions)} records"
    )

    print()
    print(
        "NOTE: Deal currency remains blank because "
        "HubSpot currency settings could not be verified "
        "with the available token scope."
    )


if __name__ == "__main__":
    main()
