"""
Scrape run tracking for Huspy Market Intel.
Every scrape gets a run_id. Every record knows which run it came from.
"""

import json
import os
import uuid
from datetime import datetime, timezone


RUNS_FILE = os.path.join(os.path.dirname(__file__), "data", "scrape_runs.json")


def load_runs() -> list:
    if os.path.exists(RUNS_FILE):
        with open(RUNS_FILE) as f:
            return json.load(f)
    return []


def save_runs(runs: list):
    os.makedirs(os.path.dirname(RUNS_FILE), exist_ok=True)
    with open(RUNS_FILE, "w") as f:
        json.dump(runs, f, indent=2)


def start_run(run_type: str, notes: str = "") -> dict:
    """Start a new scrape run. Returns run record."""
    run = {
        "run_id": str(uuid.uuid4())[:8],
        "run_type": run_type,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": None,
        "status": "running",
        "records_scraped": 0,
        "records_accepted": 0,
        "records_rejected": 0,
        "credits_used": 0,
        "notes": notes,
    }
    runs = load_runs()
    runs.append(run)
    save_runs(runs)
    return run


def complete_run(run_id: str, status: str = "success", **kwargs):
    """Mark a run as complete with stats."""
    runs = load_runs()
    for run in runs:
        if run["run_id"] == run_id:
            run["completed_at"] = datetime.now(timezone.utc).isoformat()
            run["status"] = status
            for k, v in kwargs.items():
                if k in run:
                    run[k] = v
            break
    save_runs(runs)


def get_last_run(run_type: str = None) -> dict | None:
    """Get the most recent run, optionally filtered by type."""
    runs = load_runs()
    if run_type:
        runs = [r for r in runs if r["run_type"] == run_type]
    return runs[-1] if runs else None


def print_runs(limit: int = 10):
    """Print recent runs."""
    runs = load_runs()[-limit:]
    print(f"\n{'Run ID':<10} {'Type':<25} {'Status':<10} {'Accepted':>10} {'Rejected':>10} {'Credits':>10} {'Started'}")
    print("-" * 100)
    for r in reversed(runs):
        print(f"{r['run_id']:<10} {r['run_type']:<25} {r['status']:<10} {r.get('records_accepted', ''):>10} {r.get('records_rejected', ''):>10} {r.get('credits_used', ''):>10} {r['started_at'][:19]}")
