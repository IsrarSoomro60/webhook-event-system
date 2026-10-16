# Webhook Event Processing & Monitoring System

A full-stack system that receives webhook events from external services, processes them reliably in the background, handles duplicates and failures gracefully, and provides a real-time dashboard for monitoring the complete event lifecycle.

---

## Overview

External services (like Stripe or GitHub) send **webhook events** to your server whenever something happens — a user signs up, a payment completes, etc. These deliveries are unreliable: the same event can arrive multiple times, sometimes concurrently, and processing can fail for various reasons.

This system solves that by:

- Receiving events through an authenticated HTTP endpoint
- Storing them reliably in PostgreSQL
- Processing them asynchronously via a background worker
- Handling duplicate deliveries safely (even under concurrency)
- Automatically retrying failed events up to a configurable limit
- Providing a React dashboard to monitor everything

---

## Architecture

```
┌──────────────────┐
│  Webhook         │
│  Simulator       │  ← sends test events
└────────┬─────────┘
         │  HTTP POST (with X-API-Key)
         ▼
┌──────────────────┐
│  Webhook API     │  ← validates, saves, returns fast
│  (Django)        │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  PostgreSQL      │  ← events + attempt history
└────────┬─────────┘
         │  polls for work
         ▼
┌──────────────────┐
│  Background      │  ← management command worker
│  Worker          │     runs in a separate process
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  Event           │  ← business logic
│  Processing      │     updates status, logs attempts
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  React           │  ← stats, table, detail view
│  Dashboard       │     manual retry, filters, search
└──────────────────┘
```

**Request lifecycle:**
```
RECEIVED → PENDING → PROCESSING → PROCESSED
                        ↓ (failure)
                      FAILED → retry → PROCESSING → ...
                        ↓ (max attempts reached)
                    PERMANENTLY_FAILED
```

---

## Stack

- **Backend:** Django 5, Django REST Framework, PostgreSQL
- **Frontend:** React (Vite), Tailwind CSS, Axios
- **Simulator:** Python + `requests`
- **Testing:** Django's built-in test framework

---

## Setup

### 1. Prerequisites

- Python 3.11+
- Node.js 18+
- PostgreSQL 14+

### 2. Clone & install backend

```bash
git clone <your-repo-url>
cd webhook-event-system/backend
python -m venv myenv
source myenv/bin/activate       # Windows: .\myenv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 3. Configure environment

Copy `.env.example` to `.env` and fill in your values:

```env
DJANGO_SECRET_KEY=<generate with: python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())">
DB_NAME=webhook_db
DB_USER=postgres
DB_PASSWORD=your_password
DB_HOST=localhost
DB_PORT=5432
WEBHOOK_API_KEY=change-me-in-production
MAX_RETRY_ATTEMPTS=3
RETRY_DELAY_SECONDS=10
```

⚠️ **Never commit your real `.env` file.** Only `.env.example` is committed.

### 4. Create the database

```bash
createdb webhook_db
python manage.py migrate
```

### 5. Start the backend

**Terminal 1 — Django server:**
```bash
python manage.py runserver
```

**Terminal 2 — Background worker:**
```bash
python manage.py run_worker
```

⚠️ The worker is a long-running process. Keep it running in its own terminal.

### 6. Start the frontend

```bash
cd ../frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

### 7. Run the simulator

```bash
cd ../webhook-simulator
python simulator.py single         # send one event
python simulator.py duplicate      # send same event_id 3× sequentially
python simulator.py concurrent     # send same event_id from 3 threads at once
python simulator.py failure        # payment.completed with simulate_failure=true
python simulator.py multi          # send both supported event types
```

---

## API Documentation

### `POST /api/webhooks`

Receives a webhook event from an external service.

**Headers:**
```
Content-Type: application/json
X-API-Key: <your-api-key>
```

**Body:**
```json
{
  "event_id": "evt_10291",
  "event_type": "user.created",
  "timestamp": "2026-09-16T10:30:00Z",
  "data": {
    "user_id": 123,
    "name": "Ali Ahmed",
    "email": "ali@example.com"
  }
}
```

**Responses:**

| Code | Meaning |
|---|---|
| `202 Accepted` | New event accepted; will be processed asynchronously |
| `200 OK` | Duplicate — event already exists, safely ignored |
| `400 Bad Request` | Invalid JSON, missing fields, or unsupported event type |
| `401 Unauthorized` | Missing or invalid API key |
| `405 Method Not Allowed` | Non-POST request |

---

### `GET /api/events`

List events with pagination, filtering, and search.

**Query params:**

| Param | Example | Purpose |
|---|---|---|
| `page` | `2` | Page number (default: 1) |
| `status` | `PERMANENTLY_FAILED` | Filter by status |
| `event_type` | `user.created` | Filter by event type |
| `search` | `evt_10` | Substring match on event_id |

**Response:** DRF-paginated JSON with `count`, `next`, `previous`, `results[]`.

---

### `GET /api/events/{event_id}`

Full details of one event including its complete attempt history.

**Response includes:**
- Event metadata (type, status, timestamps, attempt count, last error)
- Original payload
- `attempts[]` — one entry per processing attempt with timestamps and error text

---

### `GET /api/events/stats`

Aggregated counts for the dashboard overview.

```json
{
  "total": 47,
  "processed": 30,
  "pending": 5,
  "processing": 2,
  "failed": 10
}
```

**Note:** `pending` combines `RECEIVED + PENDING`. `failed` combines `FAILED + PERMANENTLY_FAILED`.

---

### `POST /api/events/{event_id}/retry`

Manually re-queue a failed event.

**Eligible statuses:** `FAILED`, `PERMANENTLY_FAILED`

**Effect:** Resets `status` to `PENDING`, `attempt_count` to `0`, clears `last_error`.

**Response:**

| Code | Meaning |
|---|---|
| `200 OK` | Event queued for retry |
| `400 Bad Request` | Event not eligible for retry (wrong status) |
| `404 Not Found` | No event with that ID |

---

## Design Decisions

### How duplicates are handled

Each event has a **unique `event_id`** enforced at the database level via a `UNIQUE` constraint. When a duplicate arrives:

1. `Event.objects.create()` attempts an INSERT
2. PostgreSQL rejects it with `IntegrityError`
3. The view catches the exception and returns `200 OK`

This is **atomic and race-condition-proof** — no application-level "check then insert" logic, which would have a TOCTOU vulnerability.

### How concurrent requests are handled

Two identical requests arriving in the same millisecond both try to insert the same `event_id`. PostgreSQL serializes them at the storage level: one wins, one raises `IntegrityError`. The loser returns `200 OK`. **No lock, no race, no duplicate row.**

This is verified by `test_concurrent_duplicate_delivery`, which spawns 5 threads hitting the endpoint simultaneously and asserts only 1 row exists afterward.

### How background processing works

The API **never** processes events inline. It only saves and returns. Processing happens in a separate long-running process started via:

```bash
python manage.py run_worker
```

The worker runs an infinite loop:
1. Atomically claim ONE ready event using `select_for_update(skip_locked=True)`
2. Update its status to `PROCESSING`, increment `attempt_count`, create an `EventAttempt` row
3. Release the DB lock, then process outside the transaction (long work shouldn't hold locks)
4. Update the event status and the attempt row based on success or failure

**Why `select_for_update(skip_locked=True)`?** Multiple worker processes can run safely in parallel. Each locks its own event, and others skip locked rows instead of waiting. This means horizontal scaling is possible without duplicate processing.

### How retries work

When processing fails:
- The error is recorded in `Event.last_error` and in a new/updated `EventAttempt` row
- If `attempt_count < MAX_RETRY_ATTEMPTS` → status becomes `FAILED`. The worker's query filter picks up `FAILED` events on the next cycle, retrying automatically.
- If `attempt_count >= MAX_RETRY_ATTEMPTS` → status becomes `PERMANENTLY_FAILED`. The worker will not pick it up again.

`MAX_RETRY_ATTEMPTS` is configurable via `.env`.

The `EventAttempt` table logs every attempt with `started_at`, `finished_at`, `status` (STARTED / SUCCESS / FAILED), and the error text. This gives the dashboard a full processing history.

### How authentication works

The webhook endpoint requires an `X-API-Key` header matching `settings.WEBHOOK_API_KEY`. The key is loaded from `.env` and never committed to the repository.

**Why API key over HMAC signature?** API key is simpler to implement and reason about, appropriate for this scope. An HMAC signature (signing the raw body with a shared secret) would provide stronger tamper protection and is noted as a future improvement.

### How failed/stuck processing is handled

If the worker crashes while an event is `PROCESSING`, the event remains in that state indefinitely — the worker's query filter (`RECEIVED`, `PENDING`, `FAILED`) will not pick it up again.

**Current behavior:** Stuck events require manual intervention (status reset in the admin or a script).

**Planned improvement:** A "reaper" job that periodically scans for events stuck in `PROCESSING` for longer than a threshold (e.g., 5 minutes) and resets them to `FAILED` so they get retried.

### Notable trade-offs & limitations

- **Polling worker vs. message queue:** The worker uses a simple polling loop over PostgreSQL rather than Redis/Celery. Simpler to deploy and reason about; less efficient at scale but fine for the expected load. Redis + Celery is a natural upgrade path.
- **No dead-letter queue:** Permanently failed events stay in the main table. A separate DLQ table would be cleaner for large volumes.
- **Manual retry resets attempt history:** When you retry a `PERMANENTLY_FAILED` event, `attempt_count` resets to 0. Attempts from the previous cycle remain in `EventAttempt`, but new attempts reuse numbers 1, 2, 3. Preserving a continuous numbering across retry cycles would require adding a `retry_cycle` counter — noted as an improvement.
- **Dashboard is not real-time:** The React app polls on user action (Refresh button) rather than using WebSockets/SSE. This was intentional to stay within the timebox.
- **No rate limiting on the webhook endpoint:** A production deployment would add per-IP or per-key throttling.

---

## Testing

Tests live in `backend/events/tests/test_webhooks.py`.

```bash
cd backend
python manage.py test events.tests -v 2
```

**Coverage:**

| Category | Tests |
|---|---|
| Webhook reception | Valid event, malformed JSON, missing fields, unsupported type |
| Authentication | Missing API key, wrong API key |
| Duplicate delivery | Same event_id sent 3× sequentially → 1 row |
| Concurrency | 5 threads send same event_id simultaneously → 1 row |
| Retry logic | Attempts logged, max-attempts triggers PERMANENTLY_FAILED |
| Dashboard APIs | List, pagination, filter, stats, detail, 404 |
| Manual retry | Successful retry, rejection on ineligible status |

**All 17 tests pass.**

---

## Project Structure

```
webhook-event-system/
├── backend/
│   ├── config/                 # Django project settings & root urls
│   ├── events/
│   │   ├── migrations/
│   │   ├── management/
│   │   │   └── commands/
│   │   │       └── run_worker.py       # Background worker
│   │   ├── tests/
│   │   │   └── test_webhooks.py        # 17 automated tests
│   │   ├── auth.py                     # API key decorator
│   │   ├── models.py                   # Event, EventAttempt
│   │   ├── processing.py               # Business logic
│   │   ├── serializers.py              # DRF serializers
│   │   ├── urls.py                     # App routes
│   │   └── views.py                    # Receiver + dashboard APIs
│   ├── manage.py
│   ├── requirements.txt
│   ├── .env.example
│   └── .env                    # (not committed)
├── frontend/
│   ├── src/
│   │   ├── api.js              # Axios client
│   │   ├── App.jsx             # Dashboard
│   │   └── EventDetailModal.jsx
│   └── package.json
├── webhook-simulator/
│   └── simulator.py            # 5 test scenarios
└── README.md
```

---

## Future Improvements

- **Redis + Celery** for a proper queue-based worker
- **Real-time dashboard** via WebSockets or Server-Sent Events
- **Stuck-event reaper** for automatic recovery from worker crashes
- **HMAC signature auth** in addition to API key
- **Rate limiting** on the webhook endpoint
- **Docker Compose** for one-command local setup
- **Dead-letter queue** for permanently failed events
- **Structured logging** with correlation IDs to trace an event end-to-end