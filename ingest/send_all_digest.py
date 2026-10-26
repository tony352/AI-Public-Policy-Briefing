import html
import os
import smtplib

from datetime import datetime
from email.message import EmailMessage
from email.utils import formataddr

import requests
from dotenv import load_dotenv


# ---------------------------------------------------------
# Configuration
# ---------------------------------------------------------

load_dotenv(".env.ingest")

SUPABASE_URL = os.environ[
    "SUPABASE_URL"
]

SUPABASE_SECRET_KEY = os.environ[
    "SUPABASE_SECRET_KEY"
]

GMAIL_ADDRESS = os.environ[
    "GMAIL_ADDRESS"
]

GMAIL_APP_PASSWORD = os.environ[
    "GMAIL_APP_PASSWORD"
]

DIGEST_RECIPIENTS = os.environ[
    "DIGEST_RECIPIENTS"
]


SUPABASE_HEADERS = {
    "apikey":
        SUPABASE_SECRET_KEY,

    "Authorization":
        f"Bearer {SUPABASE_SECRET_KEY}",

    "Content-Type":
        "application/json",
}


# ---------------------------------------------------------
# Get all completed policy research items
# ---------------------------------------------------------

def get_items():
    response = requests.get(
        (
            f"{SUPABASE_URL}"
            "/rest/v1/items"
        ),
        headers=SUPABASE_HEADERS,
        params={
            "select": (
                "id,"
                "source_name,"
                "title,"
                "url,"
                "doi,"
                "published_at,"
                "summarized_at,"
                "summary,"
                "priority,"
                "countries,"
                "jurisdictions,"
                "policy_areas,"
                "policy_stage,"
                "methods,"
                "key_findings,"
                "policy_implications,"
                "limitations,"
                "relevance_to_us,"
                "relevance_to_uk,"
                "model_name"
            ),

            "stream":
                "eq.policy_research",

            "model_name":
                "not.is.null",

            "order":
                "published_at.desc",
        },
        timeout=30,
    )

    response.raise_for_status()

    rows = response.json()


    priority_rank = {
        "high": 0,
        "medium": 1,
        "low": 2,
    }


    rows.sort(
        key=lambda row: (
            priority_rank.get(
                (
                    row.get(
                        "priority"
                    )
                    or ""
                ).lower(),
                99,
            ),

            -publication_timestamp(
                row.get(
                    "published_at"
                )
            ),
        )
    )


    return rows


# ---------------------------------------------------------
# Date helpers
# ---------------------------------------------------------

def publication_timestamp(
    value,
):
    if not value:
        return 0

    try:
        return (
            datetime.fromisoformat(
                value.replace(
                    "Z",
                    "+00:00",
                )
            )
            .timestamp()
        )

    except ValueError:
        return 0


def format_date(
    value,
):
    if not value:
        return (
            "Date unavailable"
        )

    try:
        date = (
            datetime.fromisoformat(
                value.replace(
                    "Z",
                    "+00:00",
                )
            )
        )

        return date.strftime(
            "%d %b %Y"
        )

    except ValueError:
        return (
            "Date unavailable"
        )


def escape(
    value,
):
    return html.escape(
        str(
            value
            or ""
        )
    )


# ---------------------------------------------------------
# HTML helpers
# ---------------------------------------------------------

def make_tags(
    values,
):
    if not values:
        return ""

    valid_values = [
        value
        for value in values
        if value
    ]

    if not valid_values:
        return ""

    return " ".join(
        (
            "<span style='"
            "display:inline-block;"
            "background:#f1f5f9;"
            "border-radius:999px;"
            "padding:5px 9px;"
            "margin:2px;"
            "font-size:12px;"
            "color:#475569;"
            "'>"
            f"{escape(value)}"
            "</span>"
        )
        for value in valid_values
    )


def make_bullets(
    values,
):
    if not values:
        return ""

    valid_values = [
        value
        for value in values
        if isinstance(
            value,
            str,
        )
        and value.strip()
    ]

    if not valid_values:
        return ""

    items = "".join(
        (
            "<li style='"
            "margin-bottom:7px;"
            "'>"
            f"{escape(value)}"
            "</li>"
        )
        for value in valid_values
    )

    return (
        "<ul style='"
        "padding-left:22px;"
        "line-height:1.6;"
        "color:#334155;"
        "'>"
        f"{items}"
        "</ul>"
    )


# ---------------------------------------------------------
# One article
# ---------------------------------------------------------

def build_item_html(
    item,
):
    priority = (
        item.get(
            "priority"
        )
        or "Unclassified"
    ).upper()


    countries = (
        item.get(
            "countries"
        )
        or []
    )


    jurisdictions = (
        item.get(
            "jurisdictions"
        )
        or []
    )


    policy_areas = (
        item.get(
            "policy_areas"
        )
        or []
    )


    methods = (
        item.get(
            "methods"
        )
        or ""
    )


    policy_stage = (
        item.get(
            "policy_stage"
        )
        or ""
    )


    limitations = (
        item.get(
            "limitations"
        )
        or []
    )


    geography_html = ""


    if countries:
        geography_html += f"""
        <div style="
            margin-top:16px;
        ">
            <strong>
                Countries
            </strong>

            <div style="
                margin-top:6px;
            ">
                {make_tags(countries)}
            </div>
        </div>
        """


    if jurisdictions:
        geography_html += f"""
        <div style="
            margin-top:16px;
        ">
            <strong>
                Jurisdictions
            </strong>

            <div style="
                margin-top:6px;
            ">
                {make_tags(jurisdictions)}
            </div>
        </div>
        """


    methods_html = ""

    if methods:
        methods_html = f"""
        <div style="
            margin-top:18px;
        ">
            <strong>
                Methods
            </strong>

            <p style="
                color:#334155;
                line-height:1.6;
            ">
                {escape(methods)}
            </p>
        </div>
        """


    policy_stage_html = ""

    if policy_stage:
        policy_stage_html = f"""
        <div style="
            margin-top:18px;
        ">
            <strong>
                Policy stage
            </strong>

            <p style="
                color:#334155;
                line-height:1.6;
            ">
                {escape(policy_stage)}
            </p>
        </div>
        """


    limitations_html = ""

    if limitations:
        limitations_html = f"""
        <div style="
            margin-top:18px;
        ">
            <strong>
                Limitations
            </strong>

            {make_bullets(limitations)}
        </div>
        """


    return f"""
    <div style="
        border:1px solid #e2e8f0;
        border-radius:14px;
        padding:22px;
        margin-bottom:22px;
        background:#ffffff;
    ">

        <div style="
            font-size:13px;
            color:#64748b;
            margin-bottom:10px;
        ">
            {escape(item.get("source_name"))}
            &nbsp;·&nbsp;
            {escape(format_date(item.get("published_at")))}
            &nbsp;·&nbsp;
            <strong>
                {escape(priority)}
            </strong>
        </div>


        <div style="
            font-size:20px;
            font-weight:700;
            line-height:1.35;
            color:#0f172a;
            margin-bottom:14px;
        ">
            {escape(item.get("title"))}
        </div>


        <div style="
            margin-bottom:14px;
        ">
            {make_tags(policy_areas)}
        </div>


        <div style="
            font-size:15px;
            line-height:1.65;
            color:#334155;
        ">
            {escape(item.get("summary"))}
        </div>


        {geography_html}


        {policy_stage_html}


        {methods_html}


        <div style="
            margin-top:18px;
        ">
            <strong>
                Key findings
            </strong>

            {make_bullets(
                item.get(
                    "key_findings"
                )
                or []
            )}
        </div>


        <div style="
            margin-top:18px;
        ">
            <strong>
                Policy implications
            </strong>

            {make_bullets(
                item.get(
                    "policy_implications"
                )
                or []
            )}
        </div>


        {limitations_html}


        <div style="
            margin-top:18px;
        ">
            <strong>
                Relevance to the US
            </strong>

            <p style="
                color:#334155;
                line-height:1.6;
            ">
                {escape(
                    item.get(
                        "relevance_to_us"
                    )
                )}
            </p>
        </div>


        <div style="
            margin-top:18px;
        ">
            <strong>
                Relevance to the UK
            </strong>

            <p style="
                color:#334155;
                line-height:1.6;
            ">
                {escape(
                    item.get(
                        "relevance_to_uk"
                    )
                )}
            </p>
        </div>


        <div style="
            margin-top:20px;
        ">
            <a
                href="{escape(item.get("url"))}"
                style="
                    color:#6d28d9;
                    font-weight:600;
                    text-decoration:none;
                "
            >
                View original article →
            </a>
        </div>

    </div>
    """


# ---------------------------------------------------------
# Full email
# ---------------------------------------------------------

def build_email_html(
    items,
):
    if items:
        article_html = "".join(
            build_item_html(
                item
            )
            for item in items
        )

    else:
        article_html = """
        <div style="
            border:1px dashed #cbd5e1;
            border-radius:12px;
            padding:22px;
            color:#64748b;
        ">
            No completed policy research
            summaries were found.
        </div>
        """


    high_count = sum(
        1
        for item in items
        if (
            item.get(
                "priority"
            )
            or ""
        ).lower()
        == "high"
    )


    medium_count = sum(
        1
        for item in items
        if (
            item.get(
                "priority"
            )
            or ""
        ).lower()
        == "medium"
    )


    low_count = sum(
        1
        for item in items
        if (
            item.get(
                "priority"
            )
            or ""
        ).lower()
        == "low"
    )


    return f"""
    <!doctype html>

    <html>

    <body style="
        margin:0;
        padding:0;
        background:#f5f3ff;
    ">

        <div style="
            padding:30px 15px;
        ">

            <div style="
                max-width:780px;
                margin:0 auto;
                background:#ffffff;
                border-radius:18px;
                padding:34px;
                font-family:
                    Arial,
                    Helvetica,
                    sans-serif;
            ">

                <div style="
                    font-size:13px;
                    font-weight:700;
                    letter-spacing:1.5px;
                    color:#7c3aed;
                ">
                    PUBLIC POLICY INTELLIGENCE
                </div>


                <h1 style="
                    margin:12px 0;
                    font-size:32px;
                    color:#1e1b4b;
                ">
                    US & UK Public Policy Briefing
                </h1>


                <p style="
                    font-size:16px;
                    line-height:1.6;
                    color:#475569;
                ">
                    Full research digest of completed
                    policy research analyses currently
                    stored in Supabase.
                </p>


                <div style="
                    background:#f8fafc;
                    border-radius:12px;
                    padding:16px;
                    margin:22px 0 30px 0;
                    color:#334155;
                ">

                    <strong>
                        {len(items)} articles
                    </strong>

                    <br><br>

                    High priority:
                    {high_count}

                    <br>

                    Medium priority:
                    {medium_count}

                    <br>

                    Low priority:
                    {low_count}

                </div>


                <p style="
                    font-size:14px;
                    color:#64748b;
                ">
                    Articles are ordered by priority
                    first, then publication date.
                </p>


                <div style="
                    margin-top:32px;
                ">
                    {article_html}
                </div>

            </div>

        </div>

    </body>

    </html>
    """


# ---------------------------------------------------------
# Gmail
# ---------------------------------------------------------

def send_email(
    recipient,
    email_html,
):
    message = EmailMessage()


    message[
        "Subject"
    ] = (
        "US & UK Public Policy Briefing "
        "— Full Research Digest"
    )


    message[
        "From"
    ] = formataddr(
        (
            "Public Policy Briefing",
            GMAIL_ADDRESS,
        )
    )


    message[
        "To"
    ] = recipient


    message.set_content(
        (
            "US & UK Public Policy Briefing\n\n"
            "This message contains the full set "
            "of completed public policy research "
            "analyses currently stored in the "
            "database."
        )
    )


    message.add_alternative(
        email_html,
        subtype="html",
    )


    with smtplib.SMTP_SSL(
        "smtp.gmail.com",
        465,
    ) as smtp:

        smtp.login(
            GMAIL_ADDRESS,
            GMAIL_APP_PASSWORD,
        )

        smtp.send_message(
            message
        )


# ---------------------------------------------------------
# Main
# ---------------------------------------------------------

def main():
    print()
    print("=" * 72)

    print(
        "FULL PUBLIC POLICY "
        "RESEARCH DIGEST"
    )

    print("=" * 72)
    print()


    items = get_items()


    print(
        "Completed policy "
        "research records found:",
        len(items),
    )


    if not items:
        print()
        print(
            "No completed summaries "
            "were found."
        )

        return 0


    high_count = sum(
        1
        for item in items
        if (
            item.get(
                "priority"
            )
            or ""
        ).lower()
        == "high"
    )


    medium_count = sum(
        1
        for item in items
        if (
            item.get(
                "priority"
            )
            or ""
        ).lower()
        == "medium"
    )


    low_count = sum(
        1
        for item in items
        if (
            item.get(
                "priority"
            )
            or ""
        ).lower()
        == "low"
    )


    print(
        "High:",
        high_count,
    )

    print(
        "Medium:",
        medium_count,
    )

    print(
        "Low:",
        low_count,
    )


    email_html = (
        build_email_html(
            items
        )
    )


    recipients = [
        address.strip()

        for address
        in DIGEST_RECIPIENTS.split(",")

        if address.strip()
    ]


    if not recipients:
        raise RuntimeError(
            "No email recipients "
            "configured."
        )


    print()
    print(
        "Recipients:",
        len(recipients),
    )

    print()


    for recipient in recipients:

        send_email(
            recipient,
            email_html,
        )

        print(
            "Sent to:",
            recipient,
        )


    print()
    print(
        "Full research digest "
        "completed successfully."
    )

    print()


    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
