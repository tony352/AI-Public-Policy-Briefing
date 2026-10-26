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
# Latest successful pipeline run
# ---------------------------------------------------------

def get_latest_successful_run():
    response = requests.get(
        (
            f"{SUPABASE_URL}"
            "/rest/v1/pipeline_runs"
        ),
        headers=SUPABASE_HEADERS,
        params={
            "select":
                "started_at,completed_at",

            "status":
                "eq.success",

            "completed_at":
                "not.is.null",

            "order":
                "completed_at.desc",

            "limit":
                "1",
        },
        timeout=30,
    )

    response.raise_for_status()

    rows = response.json()

    if not rows:
        return None

    return rows[0]


# ---------------------------------------------------------
# Get this run's completed summaries
# ---------------------------------------------------------

def get_items(
    start,
    end,
):
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
                "relevance_to_uk"
            ),

            "stream":
                "eq.policy_research",

            "priority":
                "in.(medium,high)",

            "summarized_at":
                "not.is.null",
        },
        timeout=30,
    )

    response.raise_for_status()

    rows = response.json()


    start_dt = datetime.fromisoformat(
        start.replace(
            "Z",
            "+00:00",
        )
    )

    end_dt = datetime.fromisoformat(
        end.replace(
            "Z",
            "+00:00",
        )
    )


    filtered = []


    for row in rows:
        value = row.get(
            "summarized_at"
        )

        if not value:
            continue


        summary_time = (
            datetime.fromisoformat(
                value.replace(
                    "Z",
                    "+00:00",
                )
            )
        )


        if (
            start_dt
            <= summary_time
            <= end_dt
        ):
            filtered.append(
                row
            )


    priority_rank = {
        "high": 0,
        "medium": 1,
    }


    filtered.sort(
        key=lambda row: (
            priority_rank.get(
                row.get(
                    "priority"
                ),
                99,
            ),

            -publication_timestamp(
                row.get(
                    "published_at"
                )
            ),
        )
    )


    return filtered


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
        or ""
    ).upper()


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
            {make_tags(
                item.get(
                    "policy_areas"
                )
                or []
            )}
        </div>


        <div style="
            font-size:15px;
            line-height:1.65;
            color:#334155;
        ">
            {escape(item.get("summary"))}
        </div>


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
            No new medium or high priority
            policy research items were
            completed in this run.
        </div>
        """


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
                    Newly analyzed medium and high
                    priority research from selected
                    public policy journals.
                </p>


                <p style="
                    font-size:14px;
                    color:#64748b;
                ">
                    Articles are ordered High priority
                    first, then Medium priority.
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
        "US & UK Public Policy Briefing"
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
            "This email contains newly analyzed "
            "medium and high priority public "
            "policy research."
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
    print(
        "Preparing Public Policy "
        "Briefing email..."
    )


    run = (
        get_latest_successful_run()
    )


    if not run:
        raise RuntimeError(
            "No successful pipeline "
            "run is available."
        )


    start = (
        run[
            "started_at"
        ]
    )

    end = (
        run[
            "completed_at"
        ]
    )


    print(
        "Pipeline window:"
    )

    print(
        start
    )

    print(
        "to"
    )

    print(
        end
    )


    items = get_items(
        start,
        end,
    )


    print()
    print(
        "Medium/high items "
        "for email:",
        len(items),
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
        "Policy briefing email "
        "completed successfully."
    )

    print()


if __name__ == "__main__":
    main()
