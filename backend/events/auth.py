from functools import wraps
from django.conf import settings
from django.http import JsonResponse


def require_api_key(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        if not api_key or api_key != settings.WEBHOOK_API_KEY:
            return JsonResponse(
                {'error': 'Invalid or missing API key'},
                status=401
            )
        return view_func(request, *args, **kwargs)
    return wrapper