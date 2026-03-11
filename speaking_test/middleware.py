from django.core.cache import cache
from django.utils import timezone


class OnlineTrackingMiddleware:
    """Track online users via cache"""
    ONLINE_KEY = 'online_users'
    TIMEOUT = 300  # 5 minutes

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Track session as active
        session_key = request.session.session_key
        if session_key:
            online_sessions = cache.get(self.ONLINE_KEY, set())
            online_sessions.add(session_key)
            cache.set(self.ONLINE_KEY, online_sessions, self.TIMEOUT)

        response = self.get_response(request)
        return response


def get_online_count():
    online = cache.get(OnlineTrackingMiddleware.ONLINE_KEY, set())
    return len(online)
