from django.http import HttpResponseForbidden

BLOCKED_FRAGMENTS = (
    '.py', '.pyc', '.sqlite', '.sqlite3', '.db', '.env',
    '.git', '.log', '.bak', '.ini', '.json', '.yml', '.yaml',
    'manage.py', 'requirements.txt', 'settings.py', 'db.sqlite3',
)

BLOCKED_PREFIXES = ('/etc/', '/var/', '/home/', '/proc/', '/tmp/')

TRAVERSAL_MARKERS = ('..', '%2e%2e', '\\', '%5c')


def _is_sensitive_path(request):
    raw = request.path
    lowered = raw.lower()

    for frag in BLOCKED_FRAGMENTS:
        if frag in lowered:
            return True

    for prefix in BLOCKED_PREFIXES:
        if lowered.startswith(prefix):
            return True

    for marker in TRAVERSAL_MARKERS:
        if marker in raw:
            return True

    return False


class ProtectionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if _is_sensitive_path(request):
            return HttpResponseForbidden('<h1>403 Forbidden</h1>')

        response = self.get_response(request)

        response['X-Content-Type-Options'] = 'nosniff'
        response['X-Frame-Options'] = 'DENY'
        response['Referrer-Policy'] = 'same-origin'
        response['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'

        return response
