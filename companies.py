import os
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

HUBSPOT_ACCESS_TOKEN = os.getenv("HUBSPOT_ACCESS_TOKEN")


def format_domain(domain):
    if not domain:
        return ""

    domain = str(domain).strip()

    if not domain.startswith(("http://", "https://")):
        domain = "https://" + domain

    return domain


def clean_companies(data):
    df = pd.DataFrame(data)

    # Replace null values with blank cells
    df = df.fillna("")

    # Format company domains
    df["Domain / Domain URL"] = df["Domain / Domain URL"].apply(format_domain)

    # Remove duplicate companies by domain
    df = df.drop_duplicates(
        subset=["Domain / Domain URL"],
        keep="first"
    )

    # Validate employee count
    df["employees"] = pd.to_numeric(
        df["employees"],
        errors="coerce"
    ).astype("Int64")

    # Validate annual revenue
    df["annualRevenue / Amount"] = pd.to_numeric(
        df["annualRevenue / Amount"],
        errors="coerce"
    )

    return df


sample_companies = [
    {
        "name": "Alpha Ltd",
        "Domain / Domain URL": "alpha.com",
        "Links / Primary Link URL": "https://alpha.com",
        "Address / Address 1": "10 Main Street",
        "Address / City": "Lagos",
        "Address / State": "Lagos",
        "Address / Post Code": "100001",
        "Address / Country": "Nigeria",
        "employees": 25,
        "annualRevenue / Amount": 500000
    },
    {
        "name": "Beta Ltd",
        "Domain / Domain URL": "https://beta.com",
        "Links / Primary Link URL": "https://beta.com",
        "Address / Address 1": "20 Market Road",
        "Address / City": "Abuja",
        "Address / State": "FCT",
        "Address / Post Code": "900001",
        "Address / Country": "Nigeria",
        "employees": 10,
        "annualRevenue / Amount": 250000
    }
]


cleaned_companies = clean_companies(sample_companies)

cleaned_companies.to_csv("companies.csv", index=False)

print(cleaned_companies)
print("\ncompanies.csv created successfully.")