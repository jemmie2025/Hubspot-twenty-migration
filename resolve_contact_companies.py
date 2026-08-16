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

CONTACTS_FILE = "contacts_stage1.csv"
COMPANIES_FILE = "companies.csv"

OUTPUT_FILE = "people.csv"
EXCEPTIONS_FILE = "people_company_exceptions.csv"

MAX_RETRIES = 6

# HubSpot-defined Contact -> Primary Company association type
PRIMARY_COMPANY_TYPE_ID = 1


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
            seen.add(
                company_id
            )

            ids.append(
                company_id
            )

    return ids


def canonical_domain_key(value):

    value = clean_text(
        value
    ).lower()

    if not value:
        return ""

    if "://" not in value:
        value = (
            "https://" + value
        )

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


def is_no_association_error(error):
    """
    HubSpot may return NO_ASSOCIATIONS_FOUND for individual
    records inside a batch response.

    This is a source-data condition, not a fatal API failure.
    """

    text = json.dumps(
        error,
        ensure_ascii=False,
    ).upper()

    return (
        "NO_ASSOCIATIONS_FOUND"
        in text
    )


# ============================================================
# LOAD CONTACTS STAGE 1
# ============================================================

def load_contacts():

    with open(
        CONTACTS_FILE,
        encoding="utf-8-sig",
    ) as file:

        rows = list(
            csv.DictReader(file)
        )

    if not rows:

        raise SystemExit(
            f"ERROR: {CONTACTS_FILE} contains no records."
        )

    required = {
        "_hubspotContactId",
        "_associatedCompanyIds",
        "firstName",
        "lastName",
        "email",
        "Phones / Primary Phone Number",
        "Phones / Primary Phone Country Code",
        "jobTitle",
    }

    missing = (
        required
        - set(rows[0].keys())
    )

    if missing:

        raise SystemExit(
            "ERROR: Missing Contacts columns: "
            + ", ".join(
                sorted(missing)
            )
        )

    contact_ids = []

    for row in rows:

        contact_id = clean_text(
            row.get(
                "_hubspotContactId"
            )
        )

        if not contact_id:

            raise SystemExit(
                "ERROR: A Contact record "
                "is missing its HubSpot ID."
            )

        contact_ids.append(
            contact_id
        )

    if (
        len(contact_ids)
        != len(set(contact_ids))
    ):

        raise SystemExit(
            "ERROR: Duplicate HubSpot "
            "Contact IDs detected."
        )

    return rows


# ============================================================
# LOAD FINAL COMPANY DOMAINS
# ============================================================

def load_final_company_domains():

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

    field = (
        "Domain / Domain URL"
    )

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
# CLASSIFY EXISTING CONTACT ASSOCIATIONS
# ============================================================

def classify_stage1_associations(
    contacts
):
    """
    Use the Company IDs already extracted in contacts_stage1.csv.

    0 Companies:
        no association

    1 Company:
        select directly

    >1 Companies:
        use HubSpot v4 to determine Primary Company
    """

    selected = {}

    no_association = set()

    multi_company = {}

    for contact in contacts:

        contact_id = clean_text(
            contact[
                "_hubspotContactId"
            ]
        )

        company_ids = parse_company_ids(
            contact[
                "_associatedCompanyIds"
            ]
        )

        if not company_ids:

            no_association.add(
                contact_id
            )

        elif len(
            company_ids
        ) == 1:

            selected[
                contact_id
            ] = company_ids[0]

        else:

            multi_company[
                contact_id
            ] = company_ids

    return (
        selected,
        no_association,
        multi_company,
    )


# ============================================================
# RESOLVE MULTI-COMPANY CONTACTS
# ============================================================

def resolve_multi_company_contacts(
    multi_company
):

    resolved = {}

    ambiguous = {}

    contact_ids = list(
        multi_company.keys()
    )

    if not contact_ids:

        return (
            resolved,
            ambiguous,
        )

    processed = 0

    for batch_ids in chunks(
        contact_ids,
        1000,
    ):

        body = {
            "inputs": [
                {
                    "id": contact_id
                }
                for contact_id
                in batch_ids
            ]
        }

        data = api_post(
            "/crm/v4/associations/"
            "contacts/companies/"
            "batch/read",
            body,
        )

        result_map = {}

        for result in data.get(
            "results",
            [],
        ):

            contact_id = clean_text(
                (
                    result.get(
                        "from"
                    )
                    or {}
                ).get(
                    "id"
                )
            )

            if contact_id:

                result_map[
                    contact_id
                ] = (
                    result.get(
                        "to",
                        [],
                    )
                    or []
                )

        unexpected_errors = {}

        for error in (
            data.get(
                "errors",
                [],
            )
            or []
        ):

            if is_no_association_error(
                error
            ):
                continue

            error_id = clean_text(
                error.get(
                    "id"
                )
            )

            if error_id:

                unexpected_errors[
                    error_id
                ] = json.dumps(
                    error,
                    ensure_ascii=False,
                )[:500]

        for contact_id in batch_ids:

            candidate_ids = (
                multi_company[
                    contact_id
                ]
            )

            associations = (
                result_map.get(
                    contact_id,
                    [],
                )
            )

            primary_ids = []

            for association in associations:

                company_id = clean_text(
                    association.get(
                        "toObjectId"
                    )
                )

                if (
                    not company_id
                    or company_id
                    not in candidate_ids
                ):

                    continue

                types = (
                    association.get(
                        "associationTypes",
                        [],
                    )
                    or []
                )

                is_primary = any(

                    t.get(
                        "category"
                    )
                    == "HUBSPOT_DEFINED"

                    and int(
                        t.get(
                            "typeId",
                            -1,
                        )
                    )
                    == PRIMARY_COMPANY_TYPE_ID

                    for t in types
                )

                if (
                    is_primary
                    and company_id
                    not in primary_ids
                ):

                    primary_ids.append(
                        company_id
                    )

            if len(
                primary_ids
            ) == 1:

                resolved[
                    contact_id
                ] = primary_ids[0]

            else:

                if contact_id in unexpected_errors:

                    reason = (
                        "Association API error "
                        "while resolving multiple Companies"
                    )

                elif len(
                    primary_ids
                ) > 1:

                    reason = (
                        "Multiple Primary Company associations"
                    )

                else:

                    reason = (
                        "Multiple Company associations "
                        "with no unique Primary Company"
                    )

                ambiguous[
                    contact_id
                ] = {
                    "reason":
                        reason,

                    "candidateCompanyIds":
                        candidate_ids,
                }

        processed += len(
            batch_ids
        )

        print(
            "Multi-Company Contacts processed:",
            processed,
        )

    return (
        resolved,
        ambiguous,
    )


# ============================================================
# FETCH SELECTED COMPANY DOMAINS
# ============================================================

def fetch_company_domains(
    company_ids
):

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
# BUILD FINAL PEOPLE DATASET
# ============================================================

def build_people(
    contacts,
    selected_companies,
    no_association,
    ambiguous_contacts,
    company_lookup,
    final_domain_map,
    ambiguous_domain_keys,
):

    people = []

    exceptions = []

    for contact in contacts:

        contact_id = clean_text(
            contact[
                "_hubspotContactId"
            ]
        )

        company_domain = ""

        if contact_id in no_association:

            exceptions.append({
                "_hubspotContactId":
                    contact_id,

                "email":
                    clean_text(
                        contact.get(
                            "email"
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

        elif contact_id in ambiguous_contacts:

            info = (
                ambiguous_contacts[
                    contact_id
                ]
            )

            exceptions.append({
                "_hubspotContactId":
                    contact_id,

                "email":
                    clean_text(
                        contact.get(
                            "email"
                        )
                    ),

                "reason":
                    info[
                        "reason"
                    ],

                "companyId":
                    "",

                "companyName":
                    "",

                "hubspotDomain":
                    "",

                "candidateCompanyIds":
                    ";".join(
                        info[
                            "candidateCompanyIds"
                        ]
                    ),
            })

        else:

            company_id = clean_text(
                selected_companies.get(
                    contact_id
                )
            )

            company = (
                company_lookup.get(
                    company_id
                )
            )

            if not company:

                exceptions.append({
                    "_hubspotContactId":
                        contact_id,

                    "email":
                        clean_text(
                            contact.get(
                                "email"
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
                        "_hubspotContactId":
                            contact_id,

                        "email":
                            clean_text(
                                contact.get(
                                    "email"
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

        people.append({
            "firstName":
                clean_text(
                    contact.get(
                        "firstName"
                    )
                ),

            "lastName":
                clean_text(
                    contact.get(
                        "lastName"
                    )
                ),

            "email":
                clean_text(
                    contact.get(
                        "email"
                    )
                ),

            "Phones / Primary Phone Number":
                clean_text(
                    contact.get(
                        "Phones / Primary Phone Number"
                    )
                ),

            "Phones / Primary Phone Country Code":
                clean_text(
                    contact.get(
                        "Phones / Primary Phone Country Code"
                    )
                ),

            "jobTitle":
                clean_text(
                    contact.get(
                        "jobTitle"
                    )
                ),

            "companyDomain":
                company_domain,
        })

    return (
        people,
        exceptions,
    )


# ============================================================
# WRITE OUTPUTS
# ============================================================

def write_people(rows):

    fields = [
        "firstName",
        "lastName",
        "email",
        "Phones / Primary Phone Number",
        "Phones / Primary Phone Country Code",
        "jobTitle",
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
        "_hubspotContactId",
        "email",
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
        "Loading Contacts Stage 1 data..."
    )

    contacts = load_contacts()

    print(
        "Contacts loaded:",
        len(contacts),
    )

    print(
        "Loading final Companies domain reference..."
    )

    (
        final_domain_map,
        ambiguous_domain_keys,
    ) = load_final_company_domains()

    print(
        "Usable Company domain keys:",
        len(final_domain_map),
    )

    (
        selected_companies,
        no_association,
        multi_company,
    ) = classify_stage1_associations(
        contacts
    )

    print()
    print(
        "Single-Company Contacts:",
        len(selected_companies),
    )

    print(
        "Contacts without Company association:",
        len(no_association),
    )

    print(
        "Contacts with multiple Companies:",
        len(multi_company),
    )

    if multi_company:

        print(
            "Resolving Primary Company for "
            "multi-Company Contacts..."
        )

        (
            multi_resolved,
            ambiguous_contacts,
        ) = resolve_multi_company_contacts(
            multi_company
        )

        selected_companies.update(
            multi_resolved
        )

    else:

        ambiguous_contacts = {}

    print()
    print(
        "Contacts with selected Company:",
        len(selected_companies),
    )

    print(
        "Ambiguous multi-Company Contacts:",
        len(ambiguous_contacts),
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
        fetch_company_domains(
            company_ids
        )
    )

    people, exceptions = (
        build_people(
            contacts,
            selected_companies,
            no_association,
            ambiguous_contacts,
            company_lookup,
            final_domain_map,
            ambiguous_domain_keys,
        )
    )

    write_people(
        people
    )

    write_exceptions(
        exceptions
    )

    resolved_domains = sum(
        bool(
            row[
                "companyDomain"
            ]
        )
        for row in people
    )

    print()
    print(
        "=== Contact -> Company Resolution Report ==="
    )

    print(
        "Total Contacts:",
        len(people),
    )

    print(
        "Contacts with resolved companyDomain:",
        resolved_domains,
    )

    print(
        "Contacts without resolved companyDomain:",
        len(people)
        - resolved_domains,
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


if __name__ == "__main__":
    main()
