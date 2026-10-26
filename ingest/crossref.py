import os
import re
import sys

from datetime import datetime, timedelta, timezone

import requests
from dotenv import load_dotenv


# ---------------------------------------------------------
# Configuration
# ---------------------------------------------------------

load_dotenv(".env.ingest")

SUPABASE_URL = os.environ["SUPABASE_URL"]

SUPABASE_SECRET_KEY = os.environ[
    "SUPABASE_SECRET_KEY"
]


# ---------------------------------------------------------
# Journal list
# ---------------------------------------------------------
#
# Use online ISSNs where available.
#
# Each journal is queried separately so:
# - failures are easy to identify
# - source_name is reliable
# - one problematic journal does not stop the others
# ---------------------------------------------------------

JOURNALS = [
    {
        "name": "Policy Studies Journal",
        "issn": "1541-0072",
    },
    {
        "name": "Public Administration Review",
        "issn": "1540-6210",
    },
    {
        "name": (
            "Journal of Public Administration "
            "Research and Theory"
        ),
        "issn": "1477-9803",
    },
    {
        "name": (
            "Journal of Policy Analysis "
            "and Management"
        ),
        "issn": "1520-6688",
    },
    {
        "name": (
            "American Review of "
            "Public Administration"
        ),
        "issn": "1552-3357",
    },
    {
        "name": "Journal of Public Policy",
        "issn": "1469-7815",
    },
    {
        "name": "Public Administration",
        "issn": "1467-9299",
    },
    {
        "name": (
            "Public Policy and Administration"
        ),
        "issn": "1749-4192",
    },
    {
        "name": "Policy & Politics",
        "issn": "1470-8442",
    },
    {
        "name": "Policy Studies",
        "issn": "1470-1006",
    },
    {
        "name": "Public Management Review",
        "issn": "1471-9045",
    },
    {
        "name": "Journal of Social Policy",
        "issn": "1469-7823",
    },
    {
        "name": "Policy and Society",
        "issn": "1839-3373",
    },
    {
        "name": "Governance",
        "issn": "1468-0491",
    },
]


# ---------------------------------------------------------
# Search settings
# ---------------------------------------------------------

LOOKBACK_DAYS = 14

MAX_RESULTS_PER_JOURNAL = 100


# ---------------------------------------------------------
# HTTP configuration
# ---------------------------------------------------------

SESSION = requests.Session()

SESSION.headers.update(
    {
        "User-Agent": (
            "DRPH-Public-Policy-Intelligence/1.0 "
            "(public policy research monitoring)"
        ),
    }
)


SUPABASE_HEADERS = {
    "apikey": SUPABASE_SECRET_KEY,
    "Authorization": (
        f"Bearer {SUPABASE_SECRET_KEY}"
    ),
    "Content-Type": "application/json",
}


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

def clean_text(value):
    """
    Remove simple HTML markup and collapse whitespace.
    """

    if not value:
        return ""

    value = re.sub(
        r"<[^>]+>",
        " ",
        value,
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value.strip()


def first_value(value):
    """
    Crossref commonly returns titles as one-element lists.
    """

    if isinstance(
        value,
        list,
    ):
        if value:
            return value[0]

        return None

    return value


def normalize_doi(doi):
    """
    Normalize DOI for consistent duplicate detection.
    """

    if not doi:
        return ""

    value = (
        doi
        .strip()
        .lower()
    )

    value = re.sub(
        r"^https?://doi\.org/",
        "",
        value,
    )

    return value


# ---------------------------------------------------------
# Date handling
# ---------------------------------------------------------

def crossref_date_to_iso(
    date_obj,
):
    """
    Convert Crossref date-parts to UTC ISO timestamp.
    """

    if not date_obj:
        return None

    date_parts = (
        date_obj.get(
            "date-parts",
            []
        )
    )

    if not date_parts:
        return None

    values = date_parts[0]

    if not values:
        return None


    year = values[0]

    month = (
        values[1]
        if len(values) >= 2
        else 1
    )

    day = (
        values[2]
        if len(values) >= 3
        else 1
    )


    try:
        date = datetime(
            int(year),
            int(month),
            int(day),
            tzinfo=timezone.utc,
        )

        return date.isoformat()

    except (
        TypeError,
        ValueError,
    ):
        return None


def extract_publication_date(
    item,
):
    """
    Prefer online publication date, then print,
    then general publication/issued date.
    """

    keys = [
        "published-online",
        "published-print",
        "published",
        "issued",
        "created",
    ]


    for key in keys:
        value = (
            crossref_date_to_iso(
                item.get(key)
            )
        )

        if value:
            return value


    return None


# ---------------------------------------------------------
# Crossref
# ---------------------------------------------------------

def fetch_recent_articles(
    journal,
):
    """
    Retrieve recent journal articles for one journal.
    """

    journal_name = (
        journal["name"]
    )

    journal_issn = (
        journal["issn"]
    )


    cutoff = (
        datetime.now(
            timezone.utc
        )
        - timedelta(
            days=LOOKBACK_DAYS
        )
    )


    cutoff_date = (
        cutoff.strftime(
            "%Y-%m-%d"
        )
    )


    url = (
        "https://api.crossref.org/"
        f"journals/{journal_issn}/works"
    )


    params = {
        "filter": (
            f"from-pub-date:{cutoff_date},"
            "type:journal-article"
        ),

        "rows":
            MAX_RESULTS_PER_JOURNAL,

        "sort":
            "published",

        "order":
            "desc",
    }


    print()
    print("=" * 72)

    print(
        "SEARCHING CROSSREF:"
    )

    print(
        journal_name
    )

    print("=" * 72)

    print()

    print(
        "ISSN:",
        journal_issn,
    )

    print(
        "Lookback:",
        LOOKBACK_DAYS,
        "days",
    )


    response = SESSION.get(
        url,
        params=params,
        timeout=60,
    )


    response.raise_for_status()


    payload = response.json()


    items = (
        payload
        .get(
            "message",
            {}
        )
        .get(
            "items",
            []
        )
    )


    print(
        "Crossref records found:",
        len(items),
    )


    return items


# ---------------------------------------------------------
# Supabase duplicate checks
# ---------------------------------------------------------

def doi_already_exists(
    doi,
):
    """
    Check for existing DOI.
    """

    doi = normalize_doi(
        doi
    )


    if not doi:
        return False


    response = requests.get(
        (
            f"{SUPABASE_URL}"
            "/rest/v1/items"
        ),
        headers=SUPABASE_HEADERS,
        params={
            "select": "id",
            "doi": f"eq.{doi}",
            "limit": "1",
        },
        timeout=30,
    )


    response.raise_for_status()


    return bool(
        response.json()
    )


def url_already_exists(
    url,
):
    """
    Fallback duplicate check using the canonical URL.
    """

    if not url:
        return False


    response = requests.get(
        (
            f"{SUPABASE_URL}"
            "/rest/v1/items"
        ),
        headers=SUPABASE_HEADERS,
        params={
            "select": "id",
            "url": f"eq.{url}",
            "limit": "1",
        },
        timeout=30,
    )


    response.raise_for_status()


    return bool(
        response.json()
    )


# ---------------------------------------------------------
# Save to Supabase
# ---------------------------------------------------------

def save_article(
    record,
):
    """
    Insert one policy research item.
    """

    response = requests.post(
        (
            f"{SUPABASE_URL}"
            "/rest/v1/items"
        ),
        headers={
            **SUPABASE_HEADERS,

            "Prefer": (
                "resolution=ignore-duplicates,"
                "return=minimal"
            ),
        },
        params={
            "on_conflict":
                "url",
        },
        json=record,
        timeout=30,
    )


    response.raise_for_status()


# ---------------------------------------------------------
# Convert Crossref record to our schema
# ---------------------------------------------------------

def build_record(
    item,
    journal_name,
):
    doi = normalize_doi(
        item.get(
            "DOI"
        )
    )


    title = clean_text(
        first_value(
            item.get(
                "title"
            )
        )
    )


    if not title:
        return None


    # Prefer DOI URL because it is stable.

    if doi:
        url = (
            "https://doi.org/"
            f"{doi}"
        )

    else:
        url = (
            item.get(
                "URL"
            )
            or ""
        ).strip()


    if not url:
        return None


    abstract = clean_text(
        item.get(
            "abstract"
        )
    )


    published_at = (
        extract_publication_date(
            item
        )
    )


    return {
        "stream":
            "policy_research",

        "source_name":
            journal_name,

        "title":
            title,

        "url":
            url,

        "doi":
            (
                doi
                or None
            ),

        "published_at":
            published_at,

        "abstract":
            (
                abstract
                or None
            ),

        "source_text":
            None,

        "summary":
            "AI summary pending.",

        "priority":
            None,

        "countries":
            [],

        "jurisdictions":
            [],

        "policy_areas":
            [],

        "policy_stage":
            None,

        "methods":
            None,

        "key_findings":
            [],

        "policy_implications":
            [],

        "limitations":
            [],

        "relevance_to_us":
            None,

        "relevance_to_uk":
            None,

        "model_name":
            None,
    }


# ---------------------------------------------------------
# Process one journal
# ---------------------------------------------------------

def process_journal(
    journal,
):
    journal_name = (
        journal["name"]
    )


    statistics = {
        "found": 0,
        "saved": 0,
        "duplicates": 0,
        "skipped": 0,
        "failed": False,
    }


    try:
        items = (
            fetch_recent_articles(
                journal
            )
        )

    except Exception as exc:
        print()
        print(
            "ERROR retrieving "
            f"{journal_name}:"
        )

        print(
            exc
        )

        statistics[
            "failed"
        ] = True

        return statistics


    statistics[
        "found"
    ] = len(items)


    for item in items:
        try:
            record = build_record(
                item,
                journal_name,
            )


            if record is None:
                statistics[
                    "skipped"
                ] += 1

                continue


            doi = (
                record.get(
                    "doi"
                )
            )


            url = (
                record.get(
                    "url"
                )
            )


            # ---------------------------------------------
            # Duplicate detection
            # ---------------------------------------------

            duplicate = False


            if doi:
                duplicate = (
                    doi_already_exists(
                        doi
                    )
                )


            if (
                not duplicate
                and url
            ):
                duplicate = (
                    url_already_exists(
                        url
                    )
                )


            if duplicate:
                print(
                    "Already exists:",
                    doi or url,
                    "-",
                    record["title"],
                )

                statistics[
                    "duplicates"
                ] += 1

                continue


            # ---------------------------------------------
            # Save
            # ---------------------------------------------

            save_article(
                record
            )


            print(
                "Saved:",
                doi or url,
                "-",
                record["title"],
            )


            statistics[
                "saved"
            ] += 1


        except Exception as exc:
            print()
            print(
                "ERROR processing article:"
            )

            print(
                item.get(
                    "DOI"
                )
                or item.get(
                    "URL"
                )
                or "unknown record"
            )

            print(
                exc
            )

            statistics[
                "skipped"
            ] += 1


    return statistics


# ---------------------------------------------------------
# Main
# ---------------------------------------------------------

def main():
    print()
    print("=" * 72)

    print(
        "PUBLIC POLICY RESEARCH "
        "CROSSREF INGESTION"
    )

    print("=" * 72)

    print()

    print(
        "Journals configured:",
        len(JOURNALS),
    )

    print(
        "Lookback:",
        LOOKBACK_DAYS,
        "days",
    )

    print()


    total_found = 0
    total_saved = 0
    total_duplicates = 0
    total_skipped = 0
    failed_journals = []


    for journal in JOURNALS:

        stats = (
            process_journal(
                journal
            )
        )


        total_found += (
            stats[
                "found"
            ]
        )

        total_saved += (
            stats[
                "saved"
            ]
        )

        total_duplicates += (
            stats[
                "duplicates"
            ]
        )

        total_skipped += (
            stats[
                "skipped"
            ]
        )


        if stats[
            "failed"
        ]:
            failed_journals.append(
                journal[
                    "name"
                ]
            )


    # -----------------------------------------------------
    # Final report
    # -----------------------------------------------------

    print()
    print("=" * 72)

    print(
        "CROSSREF INGESTION COMPLETE"
    )

    print("=" * 72)

    print()

    print(
        "Total records found:",
        total_found,
    )

    print(
        "Saved:",
        total_saved,
    )

    print(
        "Already existed:",
        total_duplicates,
    )

    print(
        "Skipped:",
        total_skipped,
    )


    if failed_journals:
        print()

        print(
            "Journals with retrieval "
            "errors:"
        )

        for journal_name in (
            failed_journals
        ):
            print(
                "-",
                journal_name,
            )


    print()


    # We deliberately return failure only when
    # EVERY configured journal failed.
    #
    # One journal having a temporary Crossref problem
    # should not prevent useful results from the others.

    if (
        len(failed_journals)
        == len(JOURNALS)
    ):
        return 1


    return 0


# ---------------------------------------------------------
# Entry point
# ---------------------------------------------------------

if __name__ == "__main__":

    sys.exit(
        main()
    )
