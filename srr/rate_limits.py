"""Admission control for Django views; DRF throttling does not cover these routes."""

from django.http import HttpResponse

from research.limits import LimitExceeded, configured, consume


class RateLimitMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            self.check(request)
        except LimitExceeded as exc:
            response = HttpResponse(str(exc), status=429, content_type="text/plain")
            response["Retry-After"] = str(exc.retry_after)
            return response
        return self.get_response(request)

    @staticmethod
    def check(request):
        if request.method == "POST" and request.path in {"/accounts/login/", "/admin/login/"}:
            # Never trust a client-supplied forwarding header as a rate-limit identity.
            consume(
                "login-ip",
                request.META.get("REMOTE_ADDR", "unknown"),
                configured("LOGIN_ATTEMPTS_PER_WINDOW", 20),
                300,
            )
            username = request.POST.get("username", "").strip().casefold()[:150]
            if username:
                consume("login-account", username, configured("LOGIN_ATTEMPTS_PER_WINDOW", 20), 300)
        if request.user.is_authenticated:
            if request.method == "POST":
                # Cancellation remains available even after exhausting the action budget.
                if request.path.startswith("/research/") and request.POST.get("action") == "stop":
                    return
                consume(
                    "user-writes", request.user.pk, configured("USER_WRITES_PER_MINUTE", 60), 60
                )
            elif request.method in {"GET", "HEAD"} and (
                request.GET.get("tab") == "passages"
                and request.GET.get("q")
                or request.path.startswith("/workspaces/")
                and request.GET.get("q")
            ):
                consume(
                    "user-search", request.user.pk, configured("USER_SEARCHES_PER_MINUTE", 30), 60
                )
