import os
import csv
import json
import re
import time
import urllib.parse
import urllib.request
import urllib.error

import phonenumbers
import pycountry

from phonenumbers import NumberParseException
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
}

CONTACT_PROPERTIES = [
    "firstname",
    "lastname",
    "email",
    "phone",
    "mobilephone",
    "jobtitle",
    "country",
]

OUTPUT_FILE = "contacts_stage1.csv"

MAX_RETRIES = 6


# ============================================================
# HTTP / HUBSPOT API
# ============================================================

def api_get(path, params=None):
    """
    Perform an authenticated HubSpot GET request.

    Retries:
    - HTTP 429
    - HTTP 5xx
    - Temporary network failures
    """

    url = BASE_URL + path

    if params:
        query = urllib.parse.urlencode(params)
        url = f"{url}?{query}"

    for attempt in range(MAX_RETRIES):

        request = urllib.request.Request(
            url,
            headers=HEADERS,
            method="GET",
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

            error_body = error.read().decode(
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
                f"{error_body[:500]}"
            )

        except urllib.error.URLError as error:

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
        "ERROR: HubSpot request failed after retries."
    )


# ============================================================
# STEP 1–3
# EXTRACT CONTACTS + PAGINATION + COMPANY ASSOCIATIONS
# ============================================================

def fetch_contacts():
    """
    Retrieve all Contacts from HubSpot.

    Also preserves Contact -> Company associations
    for later companyDomain resolution.
    """

    contacts = []
    after = None

    while True:

        params = {
            "limit": 100,
            "archived": "false",
            "properties": ",".join(
                CONTACT_PROPERTIES
            ),
            "associations": "companies",
        }

        if after:
            params["after"] = after

        data = api_get(
            "/crm/v3/objects/contacts",
            params,
        )

        page = data.get(
            "results",
            [],
        )

        contacts.extend(page)

        print(
            f"Contacts fetched: {len(contacts)}"
        )

        after = (
            data.get("paging", {})
            .get("next", {})
            .get("after")
        )

        if not after:
            break

    return contacts


# ============================================================
# GENERAL CLEANING
# ============================================================

NULL_VALUES = {
    "null",
    "none",
    "n/a",
    "nan",
}


def clean_text(value):
    """
    Convert source null-like values into blank strings.
    """

    if value is None:
        return ""

    value = str(value).strip()

    if value.lower() in NULL_VALUES:
        return ""

    return value


# ============================================================
# STEP 4
# NAME TRANSFORMATION
# ============================================================

def normalize_name(value):
    """
    Preserve the HubSpot name while trimming whitespace.
    """

    return clean_text(value)


# ============================================================
# STEP 5–7
# EMAIL NORMALIZATION, VALIDATION & DEDUPLICATION
# ============================================================

EMAIL_PATTERN = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+"
    r"@[A-Za-z0-9-]+"
    r"(?:\.[A-Za-z0-9-]+)+$"
)


def normalize_email(value):
    """
    Twenty CRM requirement:
    populated email addresses must be lowercase.
    """

    return clean_text(value).lower()


def is_valid_email(email):
    """
    Validate populated email structure.

    Blank emails are handled separately as source-data
    exceptions rather than formatting errors.
    """

    if not email:
        return True

    return bool(
        EMAIL_PATTERN.fullmatch(email)
    )


# ============================================================
# STEP 8–10
# PHONE CLEANING + ISO COUNTRY CODE RESOLUTION
# ============================================================

COUNTRY_ALIASES = {
    "uk": "GB",
    "u.k.": "GB",
    "united kingdom": "GB",
    "great britain": "GB",

    "usa": "US",
    "u.s.a.": "US",
    "united states": "US",
    "united states of america": "US",

    "south korea": "KR",
    "republic of korea": "KR",

    "russia": "RU",

    "vietnam": "VN",
}


def resolve_country_code(value):
    """
    Convert HubSpot country data into a two-letter ISO code
    where it can be resolved reliably.

    Examples:
    Nigeria -> NG
    United States -> US
    Germany -> DE

    Unknown values remain blank rather than being guessed.
    """

    value = clean_text(value)

    if not value:
        return ""

    normalized = value.strip().lower()

    if normalized in COUNTRY_ALIASES:
        return COUNTRY_ALIASES[normalized]

    # Already a two-letter ISO code.
    if len(value) == 2 and value.isalpha():

        code = value.upper()

        if pycountry.countries.get(
            alpha_2=code
        ):
            return code

    try:
        country = pycountry.countries.lookup(
            value
        )

        return country.alpha_2

    except LookupError:
        return ""


def digits_only(value):
    """
    Strip all non-digit characters.
    """

    return re.sub(
        r"\D",
        "",
        clean_text(value),
    )


def normalize_phone(
    raw_phone,
    hubspot_country,
):
    """
    Transform a raw HubSpot phone into:

    1. digits-only national phone number
    2. two-letter ISO country code

    Country resolution priority:

    1. International number (+...)
    2. 00 international prefix
    3. HubSpot country property
    4. Preserve digits but leave ISO country blank

    No country is guessed.
    """

    raw_phone = clean_text(
        raw_phone
    )

    if not raw_phone:
        return "", ""

    country_hint = resolve_country_code(
        hubspot_country
    )

    parse_value = raw_phone

    # Convert international 00 prefix to +
    if parse_value.startswith("00"):
        parse_value = "+" + parse_value[2:]

    try:

        if parse_value.startswith("+"):

            parsed = phonenumbers.parse(
                parse_value,
                None,
            )

        elif country_hint:

            parsed = phonenumbers.parse(
                parse_value,
                country_hint,
            )

        else:

            return (
                digits_only(raw_phone),
                "",
            )

        if not phonenumbers.is_possible_number(
            parsed
        ):

            return (
                digits_only(raw_phone),
                country_hint,
            )

        phone_number = str(
            parsed.national_number
        )

        detected_country = (
            phonenumbers.region_code_for_number(
                parsed
            )
            or country_hint
            or ""
        )

        return (
            phone_number,
            detected_country,
        )

    except NumberParseException:

        return (
            digits_only(raw_phone),
            country_hint,
        )


# ============================================================
# STEP 3
# PRESERVE COMPANY ASSOCIATIONS
# ============================================================

def get_company_ids(contact):
    """
    Extract all HubSpot Company IDs associated
    with a Contact.

    We preserve IDs now and convert them to companyDomain
    during the relationship-resolution stage.
    """

    associations = (
        contact.get("associations")
        or {}
    )

    companies = (
        associations.get("companies")
        or {}
    )

    ids = []

    for result in companies.get(
        "results",
        [],
    ):

        company_id = result.get("id")

        if company_id:
            ids.append(
                str(company_id)
            )

    return ";".join(ids)


# ============================================================
# CONTACT TRANSFORMATION
# ============================================================

def transform_contacts(records):
    """
    Transform raw HubSpot Contacts into the
    Step 1–10 intermediate schema.
    """

    transformed = []

    for record in records:

        properties = (
            record.get("properties")
            or {}
        )

        first_name = normalize_name(
            properties.get("firstname")
        )

        last_name = normalize_name(
            properties.get("lastname")
        )

        email = normalize_email(
            properties.get("email")
        )

        # Prefer primary phone.
        # Fall back to mobilephone only when phone is blank.
        raw_phone = clean_text(
            properties.get("phone")
        )

        if not raw_phone:
            raw_phone = clean_text(
                properties.get(
                    "mobilephone"
                )
            )

        phone_number, country_code = (
            normalize_phone(
                raw_phone,
                properties.get("country"),
            )
        )

        transformed.append({
            "_hubspotContactId":
                str(record.get("id", "")),

            "_associatedCompanyIds":
                get_company_ids(record),

            "firstName":
                first_name,

            "lastName":
                last_name,

            "email":
                email,

            "Phones / Primary Phone Number":
                phone_number,

            "Phones / Primary Phone Country Code":
                country_code,

            "jobTitle":
                clean_text(
                    properties.get("jobtitle")
                ),
        })

    return transformed


# ============================================================
# EMAIL DEDUPLICATION
# ============================================================

def deduplicate_contacts(rows):
    """
    Jira requirement:
    Contacts are deduplicated by email.

    Rule:
    - populated normalized emails must be unique
    - first occurrence is retained
    - blank-email Contacts are retained
    """

    seen_emails = set()

    final_rows = []

    duplicate_rows = []

    for row in rows:

        email = row["email"]

        if email:

            if email in seen_emails:

                duplicate_rows.append(
                    row
                )

                continue

            seen_emails.add(email)

        final_rows.append(row)

    return (
        final_rows,
        duplicate_rows,
    )


# ============================================================
# STAGE 1–10 EXPORT
# ============================================================

def export_contacts(rows):
    """
    Export an intermediate Contacts file.

    Internal HubSpot IDs are intentionally retained here
    because they are needed to resolve companyDomain later.

    This is NOT yet the final people.csv.
    """

    fieldnames = [
        "_hubspotContactId",
        "_associatedCompanyIds",
        "firstName",
        "lastName",
        "email",
        "Phones / Primary Phone Number",
        "Phones / Primary Phone Country Code",
        "jobTitle",
    ]

    with open(
        OUTPUT_FILE,
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
        )

        writer.writeheader()

        writer.writerows(rows)


# ============================================================
# SUMMARY / LOCAL VALIDATION
# ============================================================

def summarize(
    raw_contacts,
    final_contacts,
    duplicate_rows,
):

    invalid_emails = [
        row
        for row in final_contacts
        if row["email"]
        and not is_valid_email(
            row["email"]
        )
    ]

    missing_emails = [
        row
        for row in final_contacts
        if not row["email"]
    ]

    phones_present = [
        row
        for row in final_contacts
        if row[
            "Phones / Primary Phone Number"
        ]
    ]

    country_codes_present = [
        row
        for row in final_contacts
        if row[
            "Phones / Primary Phone Country Code"
        ]
    ]

    associated_contacts = [
        row
        for row in final_contacts
        if row[
            "_associatedCompanyIds"
        ]
    ]

    print()
    print(
        "=== Contacts Steps 1–10 Report ==="
    )

    print(
        "Raw Contacts:",
        len(raw_contacts),
    )

    print(
        "Final Contacts:",
        len(final_contacts),
    )

    print(
        "Duplicate populated emails removed:",
        len(duplicate_rows),
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
        "Contacts with phone numbers:",
        len(phones_present),
    )

    print(
        "Phone country codes resolved:",
        len(country_codes_present),
    )

    print(
        "Contacts with Company associations:",
        len(associated_contacts),
    )

    print()
    print(
        f"{OUTPUT_FILE} created successfully."
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "Starting HubSpot Contacts extraction..."
    )

    raw_contacts = fetch_contacts()

    transformed = transform_contacts(
        raw_contacts
    )

    (
        final_contacts,
        duplicate_rows,
    ) = deduplicate_contacts(
        transformed
    )

    export_contacts(
        final_contacts
    )

    summarize(
        raw_contacts,
        final_contacts,
        duplicate_rows,
    )


if __name__ == "__main__":
    main()
