from starlette.types import ASGIApp, Receive, Scope, Send

from .config import ALLOWED_ORIGINS, IS_PRODUCTION


class SecurityAndCSRFMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers_dict = {k.lower(): v for k, v in scope.get("headers", [])}
        method = scope.get("method", "GET")
        mutating = method in {"POST", "PUT", "PATCH", "DELETE"}

        cookie_bytes = headers_dict.get(b"cookie", b"")
        cookie_str = cookie_bytes.decode("utf-8") if cookie_bytes else ""
        cookies = {}
        if cookie_str:
            for item in cookie_str.split(";"):
                parts = item.split("=", 1)
                if len(parts) == 2:
                    cookies[parts[0].strip()] = parts[1].strip()

        cookie_authenticated = "access_token" in cookies or "refresh_token" in cookies
        x_bff_token = headers_dict.get(b"x-bff-token", b"").decode("utf-8") if b"x-bff-token" in headers_dict else ""

        if mutating and cookie_authenticated and not x_bff_token:
            origin = headers_dict.get(b"origin", b"").decode("utf-8").rstrip("/") if b"origin" in headers_dict else ""
            if not origin or origin not in ALLOWED_ORIGINS:
                await send({
                    "type": "http.response.start",
                    "status": 403,
                    "headers": [(b"content-type", b"application/json")],
                })
                await send({
                    "type": "http.response.body",
                    "body": b'{"detail": "Origen no autorizado"}',
                })
                return

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers_map = {k.lower(): v for k, v in message.get("headers", [])}

                headers_map[b"x-content-type-options"] = b"nosniff"
                headers_map[b"x-frame-options"] = b"DENY"
                headers_map[b"referrer-policy"] = b"no-referrer"
                headers_map[b"permissions-policy"] = b"camera=(), microphone=(), geolocation=()"
                headers_map[b"cache-control"] = b"no-store"
                if IS_PRODUCTION:
                    headers_map[b"strict-transport-security"] = b"max-age=31536000; includeSubDomains"

                message["headers"] = list(headers_map.items())
            await send(message)

        await self.app(scope, receive, send_wrapper)
