import time
import traceback

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from events.models import Event, EventAttempt
from events.processing import process_event


class Command(BaseCommand):
    help = 'Background worker that processes pending webhook events'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Worker started. Press Ctrl+C to stop.'))

        while True:
            try:
                processed_any = self.process_one_event()
            except KeyboardInterrupt:
                self.stdout.write(self.style.WARNING('\nWorker stopped.'))
                break
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Worker loop error: {e}'))
                traceback.print_exc()
                processed_any = False

            if not processed_any:
                time.sleep(2)

    # ────────────────────────────────────────────────────────
    def process_one_event(self):

        max_attempts = settings.MAX_RETRY_ATTEMPTS

        with transaction.atomic():
            event = (
                Event.objects
                .select_for_update(skip_locked=True)
                .filter(
                    status__in=[
                        Event.Status.RECEIVED,
                        Event.Status.PENDING,
                        Event.Status.FAILED,
                    ],
                    attempt_count__lt=max_attempts,
                )
                .order_by('received_at')
                .first()
            )

            if event is None:
                return False

            event.status = Event.Status.PROCESSING
            event.attempt_count += 1
            event.last_attempt_at = timezone.now()
            event.save()

            EventAttempt.objects.update_or_create(
                event=event,
                attempt_number=event.attempt_count,
                defaults={
                    'status': 'STARTED',
                    'started_at': timezone.now(),
                    'finished_at': None,
                    'error': None,
                },
            )

            current_attempt_number = event.attempt_count

        self.stdout.write(
            f'[Attempt {current_attempt_number}] Processing {event.event_id} '
            f'({event.event_type})'
        )

        try:
            process_event(event)

            event.status = Event.Status.PROCESSED
            event.processed_at = timezone.now()
            event.last_error = None
            event.save()

            EventAttempt.objects.filter(
                event=event,
                attempt_number=current_attempt_number,
            ).update(
                status='SUCCESS',
                finished_at=timezone.now(),
            )

            self.stdout.write(self.style.SUCCESS(f'  ✔ Processed {event.event_id}'))

        except Exception as e:
            error_msg = f'{type(e).__name__}: {str(e)}'
            event.last_error = error_msg

            if event.attempt_count >= max_attempts:
                event.status = Event.Status.PERMANENTLY_FAILED
                self.stdout.write(self.style.ERROR(
                    f'  ✘ Permanently failed {event.event_id} '
                    f'after {event.attempt_count} attempts'
                ))
            else:
                event.status = Event.Status.FAILED
                self.stdout.write(self.style.WARNING(
                    f'  ✘ Failed {event.event_id} '
                    f'(attempt {event.attempt_count}/{max_attempts}) — will retry'
                ))

            event.save()

            EventAttempt.objects.filter(
                event=event,
                attempt_number=current_attempt_number,
            ).update(
                status='FAILED',
                finished_at=timezone.now(),
                error=error_msg,
            )

        return True