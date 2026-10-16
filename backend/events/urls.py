from django.urls import path
from . import views

urlpatterns = [
    # Webhook receiver (Phase 4)
    path('webhooks', views.receive_webhook, name='receive_webhook'),

    # Dashboard APIs (Phase 7)
    path('events', views.list_events, name='list_events'),
    path('events/stats', views.event_stats, name='event_stats'),
    path('events/<str:event_id>', views.event_detail, name='event_detail'),
    path('events/<str:event_id>/retry', views.retry_event, name='retry_event'),
]