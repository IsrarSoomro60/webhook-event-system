import json

from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .auth import require_api_key
from .models import Event
from django.db.models import Count
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from rest_framework.pagination import PageNumberPagination

from .serializers import (
    EventListSerializer,
    EventDetailSerializer,
)


# Supported event types — anything else gets rejected with 400
SUPPORTED_EVENT_TYPES = {
    Event.EventType.USER_CREATED,
    Event.EventType.PAYMENT_COMPLETED,
}


@csrf_exempt
@require_POST
@require_api_key
def receive_webhook(request):
    # ── STEP 1: Parse the JSON body ──
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Malformed JSON'}, status=400)

    # ── STEP 2: Validate required fields ──
    required = ['event_id', 'event_type', 'timestamp', 'data']
    missing = [field for field in required if field not in body]
    if missing:
        return JsonResponse(
            {'error': f'Missing fields: {missing}'},
            status=400,
        )

    # ── STEP 3: Validate event type ──
    if body['event_type'] not in SUPPORTED_EVENT_TYPES:
        return JsonResponse(
            {'error': f'Unsupported event type: {body["event_type"]}'},
            status=400,
        )

    # ── STEP 4: Insert atomically — DB unique constraint catches duplicates ──
    try:
        with transaction.atomic():
            event = Event.objects.create(
                event_id=body['event_id'],
                event_type=body['event_type'],
                payload=body,
                status=Event.Status.RECEIVED,
            )
        return JsonResponse(
            {'message': 'Event accepted', 'event_id': event.event_id},
            status=202,
        )
    except IntegrityError:
        # Duplicate event_id already in DB — safe to ignore
        return JsonResponse(
            {'message': 'Duplicate event ignored', 'event_id': body['event_id']},
            status=200,
        )


@api_view(['GET'])
def list_events(request):
    qs = Event.objects.all().order_by('-received_at')

    event_type = request.query_params.get('event_type')
    status_filter = request.query_params.get('status')
    search = request.query_params.get('search')

    if event_type:
        qs = qs.filter(event_type=event_type)
    if status_filter:
        qs = qs.filter(status=status_filter)
    if search:
        qs = qs.filter(event_id__icontains=search)

    paginator = PageNumberPagination()
    paginator.page_size = 20
    page = paginator.paginate_queryset(qs, request)
    serializer = EventListSerializer(page, many=True)
    return paginator.get_paginated_response(serializer.data)


@api_view(['GET'])
def event_stats(request):
    counts = Event.objects.values('status').annotate(count=Count('id'))
    stats = {item['status']: item['count'] for item in counts}

    return Response({
        'total': Event.objects.count(),
        'processed': stats.get('PROCESSED', 0),
        'pending': stats.get('RECEIVED', 0) + stats.get('PENDING', 0),
        'processing': stats.get('PROCESSING', 0),
        'failed': stats.get('FAILED', 0) + stats.get('PERMANENTLY_FAILED', 0),
    })


@api_view(['GET'])
def event_detail(request, event_id):
    event = get_object_or_404(Event, event_id=event_id)
    serializer = EventDetailSerializer(event)
    return Response(serializer.data)


@api_view(['POST'])
def retry_event(request, event_id):
    event = get_object_or_404(Event, event_id=event_id)

    if event.status not in [
        Event.Status.FAILED,
        Event.Status.PERMANENTLY_FAILED,
    ]:
        return Response(
            {'error': f'Event not eligible for retry (status={event.status})'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    event.status = Event.Status.PENDING
    event.attempt_count = 0
    event.last_error = None
    event.save()

    return Response({
        'message': 'Event queued for retry',
        'event_id': event.event_id,
    })