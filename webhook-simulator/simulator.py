import argparse
import json
import threading
import uuid
from datetime import datetime, timezone

import requests


API_URL = "http://localhost:8000/api/webhooks"
API_KEY = "supersecretapikey"

HEADERS = {
    "Content-Type": "application/json",
    "X-API-Key": API_KEY,
}


def send_event(payload):
    try:
        response = requests.post(API_URL, json=payload, headers=HEADERS, timeout=5)
        print(f"[{response.status_code}] {payload['event_id']} → {response.text}")
    except Exception as e:
        print(f"[ERROR] {payload['event_id']} → {e}")


def make_payload(event_type="user.created", simulate_failure=False, event_id=None):
    return {
        "event_id": event_id or f"evt_{uuid.uuid4().hex[:8]}",
        "event_type": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "simulate_failure": simulate_failure,
        "data": {
            "user_id": 123,
            "name": "Ali Ahmed",
            "email": "ali@example.com",
        },
    }


# ─────────────────────────────────────────────────────────
# SCENARIOS
# ─────────────────────────────────────────────────────────

def scenario_single():
    print("\n--- Scenario: SINGLE event ---")
    send_event(make_payload())


def scenario_duplicate():
    print("\n--- Scenario: DUPLICATE (same event_id sent 3 times sequentially) ---")
    payload = make_payload(event_id="evt_duplicate_001")
    for i in range(3):
        print(f"Send #{i + 1}")
        send_event(payload)


def scenario_concurrent():
    print("\n--- Scenario: CONCURRENT (same event_id from 3 threads at once) ---")
    payload = make_payload(event_id="evt_concurrent_001")
    threads = [
        threading.Thread(target=send_event, args=(payload,))
        for _ in range(3)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()


def scenario_failure():
    print("\n--- Scenario: FAILURE (payment.completed with simulate_failure=true) ---")
    payload = make_payload(
        event_type="payment.completed",
        simulate_failure=True,
        event_id="evt_fail_001",
    )
    send_event(payload)


def scenario_multi():
    print("\n--- Scenario: MULTI (both supported event types) ---")
    send_event(make_payload(event_type="user.created"))
    send_event(make_payload(event_type="payment.completed"))


# ─────────────────────────────────────────────────────────
# CLI ENTRYPOINT
# ─────────────────────────────────────────────────────────

SCENARIOS = {
    "single": scenario_single,
    "duplicate": scenario_duplicate,
    "concurrent": scenario_concurrent,
    "failure": scenario_failure,
    "multi": scenario_multi,
}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Webhook simulator")
    parser.add_argument(
        "scenario",
        choices=SCENARIOS.keys(),
        help="Which scenario to run",
    )
    args = parser.parse_args()
    SCENARIOS[args.scenario]()