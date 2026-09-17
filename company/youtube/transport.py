"""Small injectable HTTPS transport with secret-free call telemetry."""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Callable, Mapping, Protocol
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from .errors import ApiError


@dataclass(frozen=True)
class HttpResponse:
    status: int
    body: bytes
    headers: Mapping[str, str]


class HttpTransport(Protocol):
    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        body: bytes | None = None,
        timeout: float = 30.0,
    ) -> HttpResponse: ...


@dataclass(frozen=True)
class ApiCallTrace:
    method: str
    endpoint: str
    status: int | None
    response_bytes: int | None
    latency_ms: int
    succeeded: bool
    error_kind: str = ""


class UrllibTransport:
    """Standard-library transport; no dependency is added to production."""

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        body: bytes | None = None,
        timeout: float = 30.0,
    ) -> HttpResponse:
        request = urllib.request.Request(
            url, data=body, headers=dict(headers or {}), method=method.upper()
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = response.read()
                return HttpResponse(
                    int(response.status), payload, dict(response.headers.items())
                )
        except urllib.error.HTTPError as exc:
            return HttpResponse(int(exc.code), exc.read(), dict(exc.headers.items()))
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ApiError(f"network request failed: {type(exc).__name__}") from None


class InstrumentedTransport:
    """Records counts/sizes/failures without recording headers, query, or body."""

    def __init__(
        self,
        inner: HttpTransport,
        *,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self.inner = inner
        self.clock = clock
        self.traces: list[ApiCallTrace] = []

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        body: bytes | None = None,
        timeout: float = 30.0,
    ) -> HttpResponse:
        started = self.clock()
        endpoint = _endpoint(url)
        try:
            response = self.inner.request(
                method, url, headers=headers, body=body, timeout=timeout
            )
        except Exception as exc:
            self.traces.append(
                ApiCallTrace(
                    method.upper(),
                    endpoint,
                    None,
                    None,
                    max(0, round((self.clock() - started) * 1000)),
                    False,
                    type(exc).__name__,
                )
            )
            raise
        self.traces.append(
            ApiCallTrace(
                method.upper(),
                endpoint,
                response.status,
                len(response.body),
                max(0, round((self.clock() - started) * 1000)),
                200 <= response.status < 300,
                "" if 200 <= response.status < 300 else "HttpError",
            )
        )
        return response


def _endpoint(url: str) -> str:
    parsed = urlsplit(url)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"


__all__ = [
    "ApiCallTrace",
    "HttpResponse",
    "HttpTransport",
    "InstrumentedTransport",
    "UrllibTransport",
]
