from rest_framework import serializers
from .models import Event, EventAttempt


class EventAttemptSerializer(serializers.ModelSerializer):
    class Meta:
        model = EventAttempt
        fields = [
            'attempt_number',
            'status',
            'started_at',
            'finished_at',
            'error',
        ]


class EventListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Event
        fields = [
            'event_id',
            'event_type',
            'status',
            'attempt_count',
            'received_at',
            'processed_at',
        ]


class EventDetailSerializer(serializers.ModelSerializer):
    attempts = EventAttemptSerializer(many=True, read_only=True)

    class Meta:
        model = Event
        fields = [
            'event_id',
            'event_type',
            'status',
            'payload',
            'attempt_count',
            'received_at',
            'last_attempt_at',
            'processed_at',
            'last_error',
            'created_at',
            'updated_at',
            'attempts',           # nested history
        ]