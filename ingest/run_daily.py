import os
import subprocess
import sys
import time
from datetime import datetime, timezone

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


PROJECT_ROOT = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)
    )
)

INGEST_DIR = os.path.join(
    PROJECT_ROOT,
    "ingest",
)


# Maximum number of Gemini summaries per run.
#
# We are deliberately keeping this conservative
# to reduce API load and make failures easier to manage.

MAX_POLICY_SUMMARIES_PER_RUN = 5


# Small pause between summaries.

SUMMARY_DELAY_SECONDS = 2


SUPABASE_HEADERS = {
    "apikey": SUPABASE_SECRET_KEY,
    "Authorization": (
        f"Bearer {SUPABASE_SECRET_KEY}"
    ),
    "Content-Type": "application/json",
}


# ---------------------------------------------------------
# Pipeline run tracking
# ---------------------------------------------------------

def create_pipeline_run():
    """
    Create a pipeline run record in Supabase.
    """

    response = requests.post(
        (
            f"{SUPABASE_URL}"
            "/rest/v1/pipeline_runs"
        ),
        headers={
            **SUPABASE_HEADERS,
            "Prefer": "return=representation",
        },
        json={
            "status": "running",
        },
        timeout=30,
    )

    response.raise_for_status()

    rows = response.json()

    if not rows:
        raise RuntimeError(
            "Supabase did not return "
            "a pipeline run record."
        )

    return rows[0]["id"]


def finish_pipeline_run(
    run_id,
    status,
):
    """
    Mark the run as success or failed.
    """

    response = requests.patch(
        (
            f"{SUPABASE_URL}"
            "/rest/v1/pipeline_runs"
        ),
        headers={
            **SUPABASE_HEADERS,
            "Prefer": "return=minimal",
        },
        params={
            "id": f"eq.{run_id}",
        },
        json={
            "status": status,
            "completed_at": (
                datetime.now(
                    timezone.utc
                ).isoformat()
            ),
        },
        timeout=30,
    )

    response.raise_for_status()


# ---------------------------------------------------------
# Run another Python script
# ---------------------------------------------------------

def run_script(
    script_name,
):
    """
    Run an ingestion/summarisation script using the same
    Python interpreter as this process.
    """

    path = os.path.join(
        INGEST_DIR,
        script_name,
    )

    print()
    print("=" * 72)
    print(
        f"RUNNING: {script_name}"
    )
    print("=" * 72)
    print()

    sys.stdout.flush()


    if not os.path.exists(path):
        print(
            f"ERROR: {path} does not exist."
        )

        return False


    result = subprocess.run(
        [
            sys.executable,
            path,
        ],
        cwd=PROJECT_ROOT,
    )


    if result.returncode != 0:
        print()
        print(
            f"FAILED: {script_name} "
            f"returned code "
            f"{result.returncode}"
        )

        return False


    print()
    print(
        f"COMPLETED: {script_name}"
    )

    return True


# ---------------------------------------------------------
# Pending summary check
# ---------------------------------------------------------

def has_pending_policy_items():
    """
    Return True if at least one policy research item
    still needs Gemini summarisation.
    """

    response = requests.get(
        (
            f"{SUPABASE_URL}"
            "/rest/v1/items"
        ),
        headers=SUPABASE_HEADERS,
        params={
            "select": "id",

            "stream":
                "eq.policy_research",

            "or": (
                '(model_name.is.null,'
                'summary.eq."AI summary pending.")'
            ),

            "limit":
                "1",
        },
        timeout=30,
    )

    response.raise_for_status()

    return bool(
        response.json()
    )


# ---------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------

def main():
    print()
    print("=" * 72)
    print(
        "PUBLIC POLICY INTELLIGENCE "
        "DAILY PIPELINE"
    )
    print("=" * 72)
    print()


    pipeline_run_id = (
        create_pipeline_run()
    )


    print(
        "Pipeline run started:"
    )

    print(
        pipeline_run_id
    )

    print()


    failures = []


    try:

        # -------------------------------------------------
        # STEP 1: Crossref ingestion
        # -------------------------------------------------

        print()
        print("=" * 72)
        print(
            "STEP 1: CROSSREF INGESTION"
        )
        print("=" * 72)
        print()


        if not run_script(
            "crossref.py"
        ):
            failures.append(
                "crossref.py"
            )


        # -------------------------------------------------
        # STEP 2: Gemini policy summaries
        # -------------------------------------------------

        print()
        print("=" * 72)
        print(
            "STEP 2: POLICY RESEARCH "
            "SUMMARISATION"
        )
        print("=" * 72)
        print()


        summaries_completed = 0


        while (
            summaries_completed
            < MAX_POLICY_SUMMARIES_PER_RUN
        ):

            try:
                pending = (
                    has_pending_policy_items()
                )

            except Exception as exc:
                print()
                print(
                    "Could not check pending "
                    "policy research items:"
                )

                print(exc)

                failures.append(
                    "policy pending check"
                )

                break


            if not pending:
                print(
                    "No pending policy "
                    "research items found."
                )

                break


            success = run_script(
                "summarise_policy.py"
            )


            if not success:
                print()
                print(
                    "Policy summarisation failed "
                    "after retries."
                )

                print(
                    "Leaving the current item "
                    "pending for a future run."
                )

                # Do not fail the whole pipeline just
                # because one Gemini request had a
                # transient problem.

                break


            summaries_completed += 1


            print()
            print(
                "Policy summaries completed "
                "this run:",
                summaries_completed,
                "/",
                MAX_POLICY_SUMMARIES_PER_RUN,
            )


            if (
                summaries_completed
                < MAX_POLICY_SUMMARIES_PER_RUN
            ):
                time.sleep(
                    SUMMARY_DELAY_SECONDS
                )


        # -------------------------------------------------
        # Safety-limit message
        # -------------------------------------------------

        if (
            summaries_completed
            >= MAX_POLICY_SUMMARIES_PER_RUN
        ):
            print()
            print(
                "Policy summary safety "
                "limit reached:"
            )

            print(
                MAX_POLICY_SUMMARIES_PER_RUN
            )

            print(
                "Any remaining items will stay "
                "pending for a future run."
            )


        # -------------------------------------------------
        # Final report
        # -------------------------------------------------

        print()
        print("=" * 72)
        print(
            "DAILY PIPELINE FINISHED"
        )
        print("=" * 72)
        print()


        print(
            "Policy summaries processed:",
            summaries_completed,
        )


        # -------------------------------------------------
        # Hard failures
        # -------------------------------------------------

        if failures:
            finish_pipeline_run(
                pipeline_run_id,
                "failed",
            )

            print()
            print(
                "The pipeline completed with "
                "the following failure(s):"
            )

            for failure in failures:
                print(
                    f"  - {failure}"
                )

            print()

            return 1


        # -------------------------------------------------
        # Successful pipeline
        # -------------------------------------------------

        finish_pipeline_run(
            pipeline_run_id,
            "success",
        )


        print()
        print(
            "All pipeline stages completed "
            "successfully."
        )

        print()


        return 0


    # -----------------------------------------------------
    # Unexpected pipeline-level exception
    # -----------------------------------------------------

    except Exception as exc:
        print()
        print("=" * 72)
        print(
            "UNEXPECTED PIPELINE ERROR"
        )
        print("=" * 72)
        print()

        print(exc)

        print()


        try:
            finish_pipeline_run(
                pipeline_run_id,
                "failed",
            )

        except Exception as tracking_exc:
            print(
                "Could not mark pipeline "
                "run as failed:"
            )

            print(
                tracking_exc
            )


        return 1


# ---------------------------------------------------------
# Entry point
# ---------------------------------------------------------

if __name__ == "__main__":
    sys.exit(
        main()
    )
