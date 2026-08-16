import os
import json
import time
import socket
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
}

MAX_RETRIES = 4


# ============================================================
# HTTP
# ============================================================

def api_get(path):
    url = BASE_URL + path

    for attempt in range(MAX_RETRIES):

        request = urllib.request.Request(
            url,
            headers=HEADERS,
            method="GET",
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=60,
            ) as response:

                return {
                    "ok": True,
                    "status": response.status,
                    "data": json.loads(
                        response.read().decode("utf-8")
                    ),
                }

        except urllib.error.HTTPError as error:

            status = error.code

            body = error.read().decode(
                "utf-8",
                "replace",
            )

            if status == 429 or 500 <= status < 600:
                delay = min(
                    30,
                    2 ** attempt,
                )

                print(
                    f"Temporary HubSpot error {status}. "
                    f"Retrying in {delay}s..."
                )

                time.sleep(delay)
                continue

            try:
                parsed = json.loads(body)
            except json.JSONDecodeError:
                parsed = {
                    "message": body
                }

            return {
                "ok": False,
                "status": status,
                "data": parsed,
            }

        except (
            urllib.error.URLError,
            TimeoutError,
            socket.timeout,
        ) as error:

            delay = min(
                30,
                2 ** attempt,
            )

            print(
                f"Network error: {error}. "
                f"Retrying in {delay}s..."
            )

            time.sleep(delay)

    return {
        "ok": False,
        "status": None,
        "data": {
            "message":
                "Request failed after maximum retries."
        },
    }


# ============================================================
# HELPERS
# ============================================================

def extract_currency_code(data):
    """
    Return a likely ISO currency code from a HubSpot
    company-currency response without assuming a fixed
    response shape.
    """

    if not isinstance(data, dict):
        return ""

    direct_keys = [
        "currencyCode",
        "code",
        "companyCurrency",
    ]

    for key in direct_keys:
        value = data.get(key)

        if (
            isinstance(value, str)
            and len(value.strip()) == 3
        ):
            return value.strip().upper()

    for value in data.values():

        if isinstance(value, dict):
            found = extract_currency_code(value)

            if found:
                return found

    return ""


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "=== HubSpot Currency Diagnostic ==="
    )

    print()
    print(
        "Checking account company currency..."
    )

    company_currency = api_get(
        "/settings/currencies/2026-03/company-currency"
    )

    if company_currency["ok"]:

        currency_code = extract_currency_code(
            company_currency["data"]
        )

        print(
            "Company currency request: SUCCESS"
        )

        if currency_code:
            print(
                "Company currency:",
                currency_code,
            )
        else:
            print(
                "Company currency response received, "
                "but no 3-letter code was automatically detected."
            )

            print(
                "Response:",
                json.dumps(
                    company_currency["data"],
                    indent=2,
                ),
            )

    else:

        print(
            "Company currency request:",
            f"HTTP {company_currency['status']}",
        )

        print(
            "Message:",
            (
                company_currency["data"].get(
                    "message",
                    ""
                )
                if isinstance(
                    company_currency["data"],
                    dict,
                )
                else company_currency["data"]
            ),
        )

    print()
    print(
        "Checking current exchange rates..."
    )

    exchange_rates = api_get(
        "/settings/currencies/2026-03/exchange-rates/current"
    )

    if exchange_rates["ok"]:

        results = (
            exchange_rates["data"].get(
                "results",
                [],
            )
            if isinstance(
                exchange_rates["data"],
                dict,
            )
            else []
        )

        print(
            "Exchange-rate request: SUCCESS"
        )

        print(
            "Current exchange-rate records:",
            len(results),
        )

        if results:
            print(
                "Multiple-currency configuration detected."
            )
        else:
            print(
                "No additional current exchange-rate "
                "records detected."
            )

    else:

        print(
            "Exchange-rate request:",
            f"HTTP {exchange_rates['status']}",
        )

        print(
            "Message:",
            (
                exchange_rates["data"].get(
                    "message",
                    ""
                )
                if isinstance(
                    exchange_rates["data"],
                    dict,
                )
                else exchange_rates["data"]
            ),
        )

    print()
    print(
        "=== Interpretation ==="
    )

    if company_currency["ok"]:

        currency_code = extract_currency_code(
            company_currency["data"]
        )

        if currency_code:

            print(
                "Verified account company currency:",
                currency_code,
            )

            if (
                exchange_rates["ok"]
                and not (
                    exchange_rates["data"].get(
                        "results",
                        [],
                    )
                )
            ):

                print(
                    "No additional active currency "
                    "rates were returned."
                )

                print(
                    "This strongly supports using the "
                    "company currency as the Deal currency "
                    "where no record-level currency exists."
                )

            else:

                print(
                    "Additional currency configuration "
                    "exists or could not be ruled out."
                )

                print(
                    "Do not assign one currency to all Deals "
                    "until we inspect the result."
                )

        else:

            print(
                "A currency response was received, but "
                "manual interpretation is required."
            )

    else:

        print(
            "The token could not read the account currency."
        )

        print(
            "Do not guess the Deal currency."
        )


if __name__ == "__main__":
    main()
