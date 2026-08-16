import os
import csv
import json
import time
import socket
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

import pycountry
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

OUTPUT_FILE = "deals_stage1.csv"
EXCEPTIONS_FILE = "deals_stage1_exceptions.csv"

MAX_RETRIES = 6

BASE_DEAL_PROPERTIES = [
    "dealname",
    "amount",
    "dealstage",
    "pipeline",
    "closedate",
]

CURRENCY_PROPERTY = "hs_currency_code"

VALID_CURRENCY_CODES = {
    currency.alpha_3
    for currency in pycountry.currencies
    if getattr(currency, "alpha_3", None)
}


# ============================================================
# HTTP
# ============================================================

def api_get(path, params=None):
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
# GENERAL HELPERS
# ============================================================

NULL_VALUES = {
    "null",
    "none",
    "n/a",
    "nan",
}


def clean_text(value):
    if value is None:
        return ""

    value = str(value).strip()

    if value.lower() in NULL_VALUES:
        return ""

    return value


def get_company_ids(deal):
    associations = (
        deal.get("associations")
        or {}
    )

    companies = (
        associations.get("companies")
        or {}
    )

    ids = []
    seen = set()

    for item in companies.get(
        "results",
        [],
    ):
        company_id = clean_text(
            item.get("id")
        )

        if (
            company_id
            and company_id not in seen
        ):
            seen.add(company_id)
            ids.append(company_id)

    return ";".join(ids)


# ============================================================
# DISCOVER AVAILABLE DEAL PROPERTIES
# ============================================================

def get_available_deal_properties():
    data = api_get(
        "/crm/v3/properties/deals"
    )

    return {
        clean_text(item.get("name"))
        for item in data.get(
            "results",
            [],
        )
        if clean_text(item.get("name"))
    }


# ============================================================
# PIPELINE / STAGE LOOKUP
# ============================================================

def get_stage_lookup():
    data = api_get(
        "/crm/v3/pipelines/deals"
    )

    stage_lookup = {}
    pipeline_lookup = {}

    for pipeline in data.get(
        "results",
        [],
    ):
        pipeline_id = clean_text(
            pipeline.get("id")
        )

        pipeline_label = clean_text(
            pipeline.get("label")
        )

        if pipeline_id:
            pipeline_lookup[
                pipeline_id
            ] = pipeline_label

        for stage in (
            pipeline.get("stages")
            or []
        ):
            stage_id = clean_text(
                stage.get("id")
            )

            stage_label = clean_text(
                stage.get("label")
            )

            if stage_id:
                stage_lookup[
                    (pipeline_id, stage_id)
                ] = stage_label

    return (
        pipeline_lookup,
        stage_lookup,
    )


# ============================================================
# EXTRACT ALL DEALS
# ============================================================

def fetch_deals(properties):
    deals = []
    after = None

    while True:
        params = {
            "limit": 100,
            "archived": "false",
            "properties": ",".join(properties),
            "associations": "companies",
        }

        if after:
            params["after"] = after

        data = api_get(
            "/crm/v3/objects/deals",
            params,
        )

        page = data.get(
            "results",
            [],
        )

        deals.extend(page)

        print(
            f"Deals fetched: {len(deals)}"
        )

        after = (
            data.get("paging", {})
            .get("next", {})
            .get("after")
        )

        if not after:
            break

    return deals


# ============================================================
# AMOUNT NORMALIZATION
# ============================================================

def normalize_amount(value):
    value = clean_text(value)

    if not value:
        return "", ""

    normalized = (
        value.replace(",", "")
        .replace("$", "")
        .strip()
    )

    try:
        amount = Decimal(normalized)

    except InvalidOperation:
        return "", "Invalid numeric amount"

    if not amount.is_finite():
        return "", "Invalid numeric amount"

    text = format(
        amount,
        "f",
    )

    if "." in text:
        text = text.rstrip("0").rstrip(".")

    return text, ""


# ============================================================
# CURRENCY NORMALIZATION
# ============================================================

def normalize_currency(value):
    value = clean_text(
        value
    ).upper()

    if not value:
        return "", ""

    if value not in VALID_CURRENCY_CODES:
        return value, "Invalid ISO currency code"

    return value, ""


# ============================================================
# CLOSE DATE NORMALIZATION
# ============================================================

def normalize_close_date(value):
    value = clean_text(value)

    if not value:
        return "", ""

    parsed = None

    try:
        if value.isdigit():
            timestamp = int(value)

            if len(value) >= 13:
                timestamp = timestamp / 1000

            parsed = datetime.fromtimestamp(
                timestamp,
                tz=timezone.utc,
            )

        else:
            iso_value = value

            if iso_value.endswith("Z"):
                iso_value = (
                    iso_value[:-1]
                    + "+00:00"
                )

            parsed = datetime.fromisoformat(
                iso_value
            )

            if parsed.tzinfo is None:
                parsed = parsed.replace(
                    tzinfo=timezone.utc
                )
            else:
                parsed = parsed.astimezone(
                    timezone.utc
                )

    except (
        ValueError,
        OverflowError,
        OSError,
    ):
        return "", "Invalid close date"

    milliseconds = (
        parsed.microsecond // 1000
    )

    return (
        parsed.strftime(
            "%Y-%m-%dT%H:%M:%S"
        )
        + f".{milliseconds:03d}Z",
        "",
    )


# ============================================================
# TRANSFORM DEALS
# ============================================================

def transform_deals(
    records,
    pipeline_lookup,
    stage_lookup,
    currency_property_available,
):
    transformed = []
    exceptions = []

    for record in records:
        properties = (
            record.get("properties")
            or {}
        )

        deal_id = clean_text(
            record.get("id")
        )

        name = clean_text(
            properties.get(
                "dealname"
            )
        )

        amount, amount_error = (
            normalize_amount(
                properties.get(
                    "amount"
                )
            )
        )

        raw_currency = ""

        if currency_property_available:
            raw_currency = properties.get(
                CURRENCY_PROPERTY
            )

        currency, currency_error = (
            normalize_currency(
                raw_currency
            )
        )

        pipeline_id = clean_text(
            properties.get(
                "pipeline"
            )
        )

        stage_id = clean_text(
            properties.get(
                "dealstage"
            )
        )

        pipeline_label = (
            pipeline_lookup.get(
                pipeline_id,
                "",
            )
        )

        stage_label = (
            stage_lookup.get(
                (pipeline_id, stage_id),
                "",
            )
        )

        close_date, date_error = (
            normalize_close_date(
                properties.get(
                    "closedate"
                )
            )
        )

        company_ids = get_company_ids(
            record
        )

        transformed.append({
            "_hubspotDealId":
                deal_id,

            "_associatedCompanyIds":
                company_ids,

            "_hubspotPipelineId":
                pipeline_id,

            "_hubspotPipelineLabel":
                pipeline_label,

            "_hubspotStageId":
                stage_id,

            "name":
                name,

            "amount / Amount":
                amount,

            "amount / Currency Code":
                currency,

            "stage":
                stage_label,

            "closeDate":
                close_date,
        })

        reasons = []

        if amount_error:
            reasons.append(
                amount_error
            )

        if currency_error:
            reasons.append(
                currency_error
            )

        if date_error:
            reasons.append(
                date_error
            )

        if (
            stage_id
            and not stage_label
        ):
            reasons.append(
                "Deal stage ID could not be resolved to a HubSpot stage label"
            )

        if reasons:
            exceptions.append({
                "_hubspotDealId":
                    deal_id,

                "name":
                    name,

                "reason":
                    "; ".join(reasons),

                "rawAmount":
                    clean_text(
                        properties.get(
                            "amount"
                        )
                    ),

                "rawCurrency":
                    clean_text(
                        raw_currency
                    ),

                "rawCloseDate":
                    clean_text(
                        properties.get(
                            "closedate"
                        )
                    ),

                "pipelineId":
                    pipeline_id,

                "dealStageId":
                    stage_id,
            })

    return (
        transformed,
        exceptions,
    )


# ============================================================
# WRITE OUTPUTS
# ============================================================

def write_stage1(rows):
    fields = [
        "_hubspotDealId",
        "_associatedCompanyIds",
        "_hubspotPipelineId",
        "_hubspotPipelineLabel",
        "_hubspotStageId",
        "name",
        "amount / Amount",
        "amount / Currency Code",
        "stage",
        "closeDate",
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
        writer.writerows(rows)


def write_exceptions(rows):
    fields = [
        "_hubspotDealId",
        "name",
        "reason",
        "rawAmount",
        "rawCurrency",
        "rawCloseDate",
        "pipelineId",
        "dealStageId",
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
        writer.writerows(rows)


# ============================================================
# SUMMARY
# ============================================================

def summarize(
    deals,
    exceptions,
    currency_property_available,
):
    missing_names = sum(
        not clean_text(row["name"])
        for row in deals
    )

    missing_amount = sum(
        not clean_text(
            row["amount / Amount"]
        )
        for row in deals
    )

    missing_currency = sum(
        not clean_text(
            row["amount / Currency Code"]
        )
        for row in deals
    )

    missing_stage = sum(
        not clean_text(row["stage"])
        for row in deals
    )

    missing_close_date = sum(
        not clean_text(
            row["closeDate"]
        )
        for row in deals
    )

    with_company_association = sum(
        bool(
            clean_text(
                row["_associatedCompanyIds"]
            )
        )
        for row in deals
    )

    print()
    print(
        "=== Deals Steps 1–7 Report ==="
    )

    print(
        "Raw Deals:",
        len(deals),
    )

    print(
        "Final Stage-1 Deals:",
        len(deals),
    )

    print(
        "Missing deal names:",
        missing_names,
    )

    print(
        "Missing/invalid amounts:",
        missing_amount,
    )

    print(
        "Currency property available:",
        currency_property_available,
    )

    print(
        "Missing/invalid currency codes:",
        missing_currency,
    )

    print(
        "Missing/unresolved HubSpot stages:",
        missing_stage,
    )

    print(
        "Missing/invalid close dates:",
        missing_close_date,
    )

    print(
        "Deals with Company associations:",
        with_company_association,
    )

    print(
        "Stage-1 transformation exceptions:",
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


# ============================================================
# MAIN
# ============================================================

def main():
    print(
        "Discovering HubSpot Deal properties..."
    )

    available_properties = (
        get_available_deal_properties()
    )

    properties = list(
        BASE_DEAL_PROPERTIES
    )

    currency_property_available = (
        CURRENCY_PROPERTY
        in available_properties
    )

    if currency_property_available:
        properties.append(
            CURRENCY_PROPERTY
        )

    print(
        "Currency property available:",
        currency_property_available,
    )

    print(
        "Loading HubSpot Deal pipeline stages..."
    )

    (
        pipeline_lookup,
        stage_lookup,
    ) = get_stage_lookup()

    print(
        "Pipelines loaded:",
        len(pipeline_lookup),
    )

    print(
        "Stages loaded:",
        len(stage_lookup),
    )

    print(
        "Starting HubSpot Deals extraction..."
    )

    raw_deals = fetch_deals(
        properties
    )

    (
        transformed,
        exceptions,
    ) = transform_deals(
        raw_deals,
        pipeline_lookup,
        stage_lookup,
        currency_property_available,
    )

    write_stage1(
        transformed
    )

    write_exceptions(
        exceptions
    )

    summarize(
        transformed,
        exceptions,
        currency_property_available,
    )


if __name__ == "__main__":
    main()
