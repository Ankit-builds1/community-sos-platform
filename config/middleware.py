from django.http import JsonResponse


class HealthCheckMiddleware:
    """Answer /healthz before ALLOWED_HOSTS is checked: hosting platforms call it on
    internal hostnames that Django would otherwise reject with 400."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path == "/healthz":
            return JsonResponse({"status": "ok"})
        return self.get_response(request)
