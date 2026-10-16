from django.db import models


class Event(models.Model):

    class EventType(models.TextChoices):
        USER_CREATED = "user.created", "User Created"
        PAYMENT_COMPLETED = "payment.completed", "Payment Completed"

    class Status(models.TextChoices):
        RECEIVED = "RECEIVED", "Received"
        PENDING = "PENDING", "Pending"
        PROCESSING = "PROCESSING", "Processing"
        PROCESSED = "PROCESSED", "Processed"
        FAILED = "FAILED", "Failed"
        PERMANENTLY_FAILED = "PERMANENTLY_FAILED", "Permanently Failed"

    event_id = models.CharField(
        max_length=255,
        unique=True,
        db_index=True,
    )

    event_type = models.CharField(
        max_length=100,
        choices=EventType.choices,
        db_index=True,
    )

    payload = models.JSONField()

    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.RECEIVED,
        db_index=True,
    )

    attempt_count = models.PositiveIntegerField(default=0)

    received_at = models.DateTimeField(auto_now_add=True)

    last_attempt_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    processed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    last_error = models.TextField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-received_at"]

    def __str__(self):
        return self.event_id


class EventAttempt(models.Model):

    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name="attempts",
    )

    attempt_number = models.PositiveIntegerField()

    status = models.CharField(
        max_length=30,
    )

    started_at = models.DateTimeField()

    finished_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    error = models.TextField(
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["attempt_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["event", "attempt_number"],
                name="unique_event_attempt",
            )
        ]

    def __str__(self):
        return f"{self.event.event_id} - Attempt {self.attempt_number}"