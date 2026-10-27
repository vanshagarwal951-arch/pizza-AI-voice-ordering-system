"""Security middleware for FastAPI application."""

from __future__ import annotations

from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""

    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)

        # Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Referrer policy
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Frame protection - allow same origin for dashboard
        response.headers["X-Frame-Options"] = "SAMEORIGIN"

        # Permissions policy - disable unused features
        response.headers["Permissions-Policy"] = (
            "geolocation=(), "
            "microphone=(self), "  # Allow microphone for voice ordering
            "camera=(), "
            "payment=(), "
            "usb=()"
        )

        # Content Security Policy
        # Allow self, inline styles (for dashboard), WebSocket, and external TTS/STT providers
        csp_directives = [
            "default-src 'self'",
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net",  # LiveKit SDK from CDN
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",  # Inline + Google Fonts
            "connect-src 'self' ws: wss: https://*.livekit.cloud https://api.groq.com https://api.deepgram.com",
            "img-src 'self' data:",
            "font-src 'self' data: https://fonts.gstatic.com",  # Google Fonts files
            "frame-ancestors 'self'",
            "base-uri 'self'",
            "form-action 'self'",
        ]
        response.headers["Content-Security-Policy"] = "; ".join(csp_directives)

        return response


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """Limit request body size to prevent DoS attacks."""

    def __init__(self, app: ASGIApp, max_size: int = 1024 * 1024):  # 1MB default
        super().__init__(app)
        self.max_size = max_size

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Check Content-Length header if present
        content_length = request.headers.get("content-length")
        if content_length:
            if int(content_length) > self.max_size:
                return Response(
                    content='{"detail":"Request body too large"}',
                    status_code=413,
                    media_type="application/json",
                )

        response = await call_next(request)
        return response
