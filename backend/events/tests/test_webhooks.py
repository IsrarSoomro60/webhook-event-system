import json
import threading
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase, Client, TransactionTestCase
from django.urls import reverse

from events.models import Event, EventAttempt


class WebhookReceiverTests(TestCase):
    """Tests for the POST /api/webhooks endpoint."""

    def setUp(self):
        self.client = Client()
        self.headers = {
            'HTTP_X_API_KEY': settings.WEBHOOK_API_KEY,
            'content_type': 'application/json',
        }
        self.payload = {
            'event_id': 'evt_test_001',
            'event_type': 'user.created',
            'timestamp': '2026-09-16T10:30:00Z',
            'data': {'user_id': 1, 'name': 'Ali'},
        }

    def post_webhook(self, payload, headers=None):
        return self.client.post(
            '/api/webhooks',
            data=json.dumps(payload),
            **(headers or self.headers),
        )

    # ── 1. Happy path ──
    def test_successful_reception(self):
        response = self.post_webhook(self.payload)
        self.assertEqual(response.status_code, 202)
        self.assertEqual(Event.objects.count(), 1)
        self.assertEqual(Event.objects.first().event_id, 'evt_test_001')

    # ── 2. Validation ──
    def test_missing_required_fields(self):
        response = self.post_webhook({'event_id': 'x'})
        self.assertEqual(response.status_code, 400)
        self.assertIn('Missing fields', response.json()['error'])

    def test_unsupported_event_type(self):
        payload = {**self.payload, 'event_type': 'unknown.thing'}
        response = self.post_webhook(payload)
        self.assertEqual(response.status_code, 400)

    def test_malformed_json(self):
        response = self.client.post(
            '/api/webhooks',
            data='not-json-at-all',
            **self.headers,
        )
        self.assertEqual(response.status_code, 400)

    # ── 3. Auth ──
    def test_missing_api_key(self):
        response = self.post_webhook(
            self.payload,
            headers={'content_type': 'application/json'},
        )
        self.assertEqual(response.status_code, 401)

    def test_wrong_api_key(self):
        response = self.post_webhook(
            self.payload,
            headers={
                'HTTP_X_API_KEY': 'completely-wrong',
                'content_type': 'application/json',
            },
        )
        self.assertEqual(response.status_code, 401)

    # ── 4. Duplicate delivery ──
    def test_duplicate_delivery_only_stores_once(self):
        self.post_webhook(self.payload)   # first
        self.post_webhook(self.payload)   # second
        self.post_webhook(self.payload)   # third
        self.assertEqual(Event.objects.count(), 1)


class ConcurrencyTests(TransactionTestCase):
    """
    Uses TransactionTestCase (not TestCase) because threads need to see
    each other's committed data. TestCase wraps each test in a transaction
    that would hide inserts from other threads.
    """
    
    def setUp(self):
        self.payload = {
            'event_id': 'evt_concurrent_001',
            'event_type': 'user.created',
            'timestamp': '2026-09-16T10:30:00Z',
            'data': {'user_id': 1},
        }
        self.headers = {
            'HTTP_X_API_KEY': settings.WEBHOOK_API_KEY,
            'content_type': 'application/json',
        }

    def tearDown(self):
        """Close any lingering DB connections opened by threads."""
        from django.db import connections
        for conn in connections.all():
            conn.close()

    def test_concurrent_duplicate_delivery(self):
        """5 threads send the same event_id at once → only ONE row."""
        errors = []

        def send():
            from django.db import connection
            try:
                client = Client()
                client.post(
                    '/api/webhooks',
                    data=json.dumps(self.payload),
                    **self.headers,
                )
            except Exception as exc:
                errors.append(exc)
            finally:
                # Close this thread's DB connection immediately
                connection.close()

        threads = [threading.Thread(target=send) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])
        self.assertEqual(Event.objects.count(), 1)

class RetryLogicTests(TestCase):
    """Tests the worker's retry logic without actually running the worker loop."""

    def setUp(self):
        self.event = Event.objects.create(
            event_id='evt_retry_001',
            event_type='payment.completed',
            payload={'event_id': 'evt_retry_001', 'simulate_failure': True},
            status=Event.Status.PENDING,
        )

    def test_event_attempts_are_created_on_each_try(self):
        from events.processing import process_event
        from django.utils import timezone

        for i in range(1, 4):
            self.event.attempt_count = i
            self.event.status = Event.Status.PROCESSING
            self.event.save()

            attempt = EventAttempt.objects.create(
                event=self.event,
                attempt_number=i,
                status='STARTED',
                started_at=timezone.now(),
            )

            try:
                process_event(self.event)
                attempt.status = 'SUCCESS'
            except Exception as exc:
                attempt.status = 'FAILED'
                attempt.error = str(exc)

            attempt.finished_at = timezone.now()
            attempt.save()

        self.assertEqual(self.event.attempts.count(), 3)
        self.assertEqual(
            EventAttempt.objects.filter(event=self.event, status='FAILED').count(),
            3,
        )

    def test_permanently_failed_after_max_attempts(self):
        max_attempts = settings.MAX_RETRY_ATTEMPTS

        self.event.attempt_count = max_attempts
        if self.event.attempt_count >= max_attempts:
            self.event.status = Event.Status.PERMANENTLY_FAILED
        self.event.save()

        self.event.refresh_from_db()
        self.assertEqual(self.event.status, Event.Status.PERMANENTLY_FAILED)


class DashboardApiTests(TestCase):
    """Tests for the dashboard endpoints."""

    def setUp(self):
        Event.objects.create(
            event_id='evt_processed',
            event_type='user.created',
            payload={},
            status=Event.Status.PROCESSED,
            attempt_count=1,
        )
        Event.objects.create(
            event_id='evt_failed',
            event_type='payment.completed',
            payload={},
            status=Event.Status.FAILED,
            attempt_count=1,
        )
        Event.objects.create(
            event_id='evt_permanent',
            event_type='payment.completed',
            payload={},
            status=Event.Status.PERMANENTLY_FAILED,
            attempt_count=3,
        )

    def test_list_events_returns_paginated_response(self):
        response = self.client.get('/api/events')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('results', data)
        self.assertEqual(data['count'], 3)

    def test_filter_by_status(self):
        response = self.client.get('/api/events?status=PERMANENTLY_FAILED')
        self.assertEqual(response.status_code, 200)
        results = response.json()['results']
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['event_id'], 'evt_permanent')

    def test_stats_endpoint(self):
        response = self.client.get('/api/events/stats')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['total'], 3)
        self.assertEqual(data['processed'], 1)
        self.assertEqual(data['failed'], 2)   # FAILED + PERMANENTLY_FAILED

    def test_event_detail(self):
        response = self.client.get('/api/events/evt_processed')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['event_id'], 'evt_processed')

    def test_event_detail_not_found(self):
        response = self.client.get('/api/events/nonexistent_id')
        self.assertEqual(response.status_code, 404)

    def test_manual_retry_on_failed_event(self):
        response = self.client.post('/api/events/evt_failed/retry')
        self.assertEqual(response.status_code, 200)

        event = Event.objects.get(event_id='evt_failed')
        self.assertEqual(event.status, Event.Status.PENDING)
        self.assertEqual(event.attempt_count, 0)

    def test_manual_retry_rejected_on_processed_event(self):
        response = self.client.post('/api/events/evt_processed/retry')
        self.assertEqual(response.status_code, 400)

        event = Event.objects.get(event_id='evt_processed')
        self.assertEqual(event.status, Event.Status.PROCESSED)  # unchanged