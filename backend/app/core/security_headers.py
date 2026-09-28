from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, enable_hsts: bool = False):
        super().__init__(app)
        self.enable_hsts = enable_hsts

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        content_security_policy = "default-src 'none'; frame-ancestors 'none'"
        if request.url.path in {"/docs", "/redoc", "/docs/oauth2-redirect"}:
            content_security_policy = (
                "default-src 'none'; frame-ancestors 'none'; "
                "connect-src 'self'; "
                "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "img-src 'self' data: https://fastapi.tiangolo.com; "
                "font-src 'self' https://cdn.jsdelivr.net"
            )
        response.headers["Content-Security-Policy"] = content_security_policy
        if self.enable_hsts:
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        return response