
"""
IncuBrix PS3 — Batch Runner

Usage:
    python batch_runner.py --input test_inputs/batch.json
    python batch_runner.py --input test_inputs/batch.json --api http://127.0.0.1:8000
"""

import argparse
import json
import time
import uuid
from pathlib import Path

import requests


def load_batch(input_path):
    """Load a JSON array of scripts from disk."""
    path = Path(input_path)

    if not path.is_file():
        raise FileNotFoundError(f"Batch input file not found: {path}")

    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, list) or not data:
        raise ValueError("The input JSON must contain a non-empty array.")

    for index, item in enumerate(data):
        if not isinstance(item, dict) or not isinstance(
            item.get("script"), str
        ) or not item["script"].strip():
            raise ValueError(
                f"Item {index + 1} must be an object with a non-empty script."
            )

    return data


def submit_job(session, api_url, item, timeout):
    """Submit one job and return its job ID and status URL."""
    response = session.post(
        f"{api_url}/api/v1/jobs",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "script": item["script"],
            "aspect_ratio": item.get("aspect_ratio", "16:9"),
            "narration_language": item.get("narration_language", "en"),
        },
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


def wait_for_job(session, api_url, status_url, timeout, poll_interval):
    """Poll a job until it succeeds, fails, or times out."""
    deadline = time.monotonic() + timeout
    url = f"{api_url}{status_url}" if status_url.startswith("/") else status_url

    while time.monotonic() < deadline:
        response = session.get(url, timeout=30)
        response.raise_for_status()
        job = response.json()

        status = job.get("status", "unknown")
        progress = job.get("progress", 0)
        print(f"  Status: {status} | Progress: {progress}%")

        if status in {"succeeded", "completed", "failed", "cancelled"}:
            return job

        time.sleep(poll_interval)

    raise TimeoutError(f"Job did not finish within {timeout} seconds.")


def main():
    parser = argparse.ArgumentParser(description="Run multiple IncuBrix jobs.")
    parser.add_argument("--input", required=True, help="Path to batch JSON file.")
    parser.add_argument(
        "--api",
        default="http://127.0.0.1:8000",
        help="Base URL of the running API.",
    )
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--poll-interval", type=float, default=3)
    parser.add_argument("--output", default="outputs/batch_report.json")
    args = parser.parse_args()

    api_url = args.api.rstrip("/")
    items = load_batch(args.input)
    results = []

    with requests.Session() as session:
        for index, item in enumerate(items, start=1):
            print(f"\n[{index}/{len(items)}] Submitting script")

            record = {
                "index": index,
                "script": item["script"],
                "job_id": None,
                "status": "submission_failed",
                "result": None,
                "error": None,
            }

            try:
                submitted = submit_job(
                    session, api_url, item, timeout=30
                )
                record["job_id"] = submitted.get("job_id")
                record["status"] = submitted.get("status", "queued")

                print(f"  Job ID: {record['job_id']}")

                status_url = submitted.get("status_url")
                if not status_url:
                    raise ValueError("API response did not include status_url.")

                job = wait_for_job(
                    session,
                    api_url,
                    status_url,
                    timeout=args.timeout,
                    poll_interval=args.poll_interval,
                )

                record["status"] = job.get("status", "unknown")
                record["result"] = job.get("result")
                record["error"] = job.get("error")

            except (requests.RequestException, ValueError, TimeoutError) as exc:
                record["error"] = str(exc)
                print(f"  Error: {exc}")

            results.append(record)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(results, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    succeeded = sum(
        result["status"] in {"succeeded", "completed"} for result in results
    )
    failed = len(results) - succeeded

    print("\nBatch finished.")
    print(f"Total: {len(results)} | Succeeded: {succeeded} | Other: {failed}")
    print(f"Report saved to: {output_path.resolve()}")


if __name__ == "__main__":
    main()