import json
import os
import time
from datetime import datetime, timezone

import requests

from dotenv import load_dotenv
from google import genai
from pydantic import BaseModel, Field


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

GEMINI_API_KEY = os.environ[
    "GEMINI_API_KEY"
]


MODEL_NAME = "gemini-3.5-flash-lite"


SUPABASE_HEADERS = {
    "apikey": SUPABASE_SECRET_KEY,
    "Authorization": f"Bearer {SUPABASE_SECRET_KEY}",
    "Content-Type": "application/json",
}


MAX_GEMINI_ATTEMPTS = 3

RETRY_DELAYS = [
    5,
    10,
    20,
]


# ---------------------------------------------------------
# Structured Gemini output
# ---------------------------------------------------------

class PolicySummary(BaseModel):
    summary: str

    priority: str = Field(
        pattern="^(low|medium|high)$"
    )

    countries: list[str]

    jurisdictions: list[str]

    policy_areas: list[str]

    policy_stage: str

    methods: str

    key_findings: list[str]

    policy_implications: list[str]

    limitations: list[str]

    relevance_to_us: str

    relevance_to_uk: str


# ---------------------------------------------------------
# Find next pending record
# ---------------------------------------------------------

def get_pending_item():
    response = requests.get(
        f"{SUPABASE_URL}/rest/v1/items",
        headers=SUPABASE_HEADERS,
        params={
            "select": "*",
            "stream": "eq.policy_research",
            "or": (
                '(model_name.is.null,'
                'summary.eq."AI summary pending.")'
            ),
            "order": "retrieved_at.asc",
            "limit": "1",
        },
        timeout=30,
    )

    response.raise_for_status()

    rows = response.json()

    if not rows:
        return None

    return rows[0]


# ---------------------------------------------------------
# Gemini
# ---------------------------------------------------------

def call_gemini(prompt):
    client = genai.Client(
        api_key=GEMINI_API_KEY
    )

    last_error = None

    for attempt in range(
        1,
        MAX_GEMINI_ATTEMPTS + 1,
    ):
        try:
            response = (
                client.models.generate_content(
                    model=MODEL_NAME,
                    contents=prompt,
                    config={
                        "response_mime_type":
                            "application/json",

                        "response_schema":
                            PolicySummary,
                    },
                )
            )

            return (
                PolicySummary
                .model_validate_json(
                    response.text
                )
            )

        except Exception as exc:
            last_error = exc

            print()
            print(
                "Gemini request failed "
                f"(attempt {attempt}/"
                f"{MAX_GEMINI_ATTEMPTS}):"
            )

            print(exc)

            if (
                attempt
                < MAX_GEMINI_ATTEMPTS
            ):
                delay = (
                    RETRY_DELAYS[
                        attempt - 1
                    ]
                )

                print(
                    f"Retrying in "
                    f"{delay} seconds..."
                )

                time.sleep(delay)

    raise last_error


# ---------------------------------------------------------
# Save result
# ---------------------------------------------------------

def save_summary(
    item_id,
    result,
):
    payload = {
        "summary":
            result.summary,

        "priority":
            result.priority,

        "countries":
            result.countries,

        "jurisdictions":
            result.jurisdictions,

        "policy_areas":
            result.policy_areas,

        "policy_stage":
            result.policy_stage,

        "methods":
            result.methods,

        "key_findings":
            result.key_findings,

        "policy_implications":
            result.policy_implications,

        "limitations":
            result.limitations,

        "relevance_to_us":
            result.relevance_to_us,

        "relevance_to_uk":
            result.relevance_to_uk,

        "model_name":
            MODEL_NAME,

        "summarized_at": 
             datetime.now(
                 timezone.utc
             ).isoformat(),
    }

    response = requests.patch(
        f"{SUPABASE_URL}/rest/v1/items",
        headers={
            **SUPABASE_HEADERS,
            "Prefer": "return=minimal",
        },
        params={
            "id": f"eq.{item_id}",
        },
        json=payload,
        timeout=30,
    )

    response.raise_for_status()


# ---------------------------------------------------------
# Main
# ---------------------------------------------------------

def main():
    item = get_pending_item()

    if not item:
        print(
            "No pending policy "
            "research items."
        )

        return 0

    print()
    print("=" * 72)

    print(
        "POLICY RESEARCH "
        "SUMMARISATION"
    )

    print("=" * 72)
    print()

    print(
        "Summarising:"
    )

    print(
        item.get(
            "title"
        )
    )

    print()

    abstract = (
        item.get(
            "abstract"
        )
        or ""
    )

    # Crossref does not always provide an abstract.
    # When absent, Gemini must not invent article findings.

    source_material = (
        abstract
        if abstract
        else (
            "No abstract was available "
            "from Crossref. Use only the "
            "title and metadata supplied."
        )
    )

    prompt = f"""
You are preparing a professional public policy research briefing
for readers interested primarily in the United States and United
Kingdom.

Analyze ONLY the material supplied below.

Do not invent:
- methods
- sample size
- empirical results
- geography
- jurisdictions
- causal claims
- policy recommendations
- limitations

If no abstract is available, clearly state that the available
information is limited and do not infer findings from the title.

SUMMARY
Provide a concise professional summary suitable for a policy
briefing.

PRIORITY
Classify the item as:
- HIGH: potentially important, actionable, major policy relevance,
  significant institutional change, or substantial implications
  for the US or UK.
- MEDIUM: relevant and useful for professional policy review.
- LOW: limited immediate policy relevance, narrow significance,
  commentary without substantive evidence, or insufficient detail.

POLICY AREAS
Use one or more of these where appropriate:

- Health
- Education
- Housing
- Economic & fiscal
- Labor & employment
- Social welfare
- Immigration
- Justice
- Environment & climate
- Energy
- Transportation
- Technology & AI
- National security
- Local government
- Public administration
- Regulation
- Governance
- Other

POLICY STAGE
Use the best-supported description, for example:

- agenda setting
- policy formulation
- adoption
- implementation
- evaluation
- governance / administration
- comparative policy
- theoretical / conceptual
- unclear

METHODS
Describe the study method only if supported by the supplied material.
Otherwise say:
"Not available from supplied metadata."

COUNTRIES
Include only countries explicitly supported by the supplied material.

JURISDICTIONS
Examples:
- US federal
- US state
- US local
- UK national
- devolved UK administration
- UK local
- international
- comparative
- unclear

RELEVANCE TO US / UK
Briefly explain the relevance separately.
Do not invent relevance where none is evident.

TITLE:
{item.get("title")}

JOURNAL:
{item.get("source_name")}

DOI:
{item.get("doi")}

ABSTRACT / SOURCE MATERIAL:
{source_material}
"""

    result = call_gemini(
        prompt
    )

    print(
        "Gemini result:"
    )

    print()

    print(
        json.dumps(
            result.model_dump(),
            indent=2,
        )
    )

    save_summary(
        item["id"],
        result,
    )

    print()
    print(
        "Saved structured policy "
        "summary to Supabase."
    )

    print()

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
