"""The one place this package touches a socket, and the record of having done so.

## An injectable seam, because the alternative is untestable authorization

Everything above this module - the OAuth exchange, the refresh, the paginated
walk, the 401 retry, the failure mapping - is logic worth testing and none of it
is worth testing against Google. So the only network call in the package goes
through `HttpTransport`, a protocol with a single method, and the test suite
supplies a fake that answers from a scripted table. `UrllibTransport` is the
real implementation and is the only class here that knows `urllib` exists.

That is also why a non-2xx response is *returned* rather than raised: status
codes carry meaning that the layer above has to interpret (a 401 is a refresh, a
403 is one of three different operator actions), and a transport that raised
would force that interpretation to happen inside an exception handler wrapped
around the wrong scope. Only a failure to complete the request at all - DNS,
TLS, timeout - becomes an `ApiError` here, because there is no status to read.

## What a call record may contain

`InstrumentedTransport` records that a call happened, what it cost and whether
it worked. It does not record headers, query strings or bodies, and this is the
single most important line in the module: the request carries an `Authorization`
header on every call and the query string of a token request carries the client
secret. A telemetry record built by copying the URL would put a credential in
the artifact, in the log, and ultimately in the repository, where the evidence
files are read by people who were never meant to hold the grant.

`_endpoint` therefore keeps scheme, host and path and discards query, params and
fragment. The endpoint in an artifact is `.../youtube/v3/videos`, never
`.../videos?id=...&access_token=...`. The trace records `response_bytes`, not the
response - a size is enough to see a truncated page, and the body may hold
private analytics.

A failed call is recorded too, with `status=None` and the exception's type name
as `error_kind`. The type name is safe; the exception message is not
necessarily, so it is not copied.
"""

from __future__ import annotations

import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol
from urllib.parse import urlsplit

from .errors import ApiError


DEFAULT_TIMEOUT = 30.0


@dataclass(frozen=True)
class HttpResponse:
    """A completed HTTP exchange, whatever its status."""

    status: int
    body: bytes
    headers: Mapping[str, str]

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300


class HttpTransport(Protocol):
    """The seam. One method, so a fake is three lines long."""

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        body: bytes | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> HttpResponse: ...


@dataclass(frozen=True)
class ApiCallTrace:
    """One call, described in terms that cannot hold a credential."""

    method: str
    endpoint: str
    status: int | None
    response_bytes: int | None
    latency_ms: int
    succeeded: bool
    error_kind: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "endpoint": self.endpoint,
            "status": self.status,
            "response_bytes": self.response_bytes,
            "latency_ms": self.latency_ms,
            "succeeded": self.succeeded,
            "error_kind": self.error_kind,
        }


class UrllibTransport:
    """Standard-library HTTPS, so production gains no dependency from this package."""

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        body: bytes | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> HttpResponse:
        request = urllib.request.Request(
            url, data=body, headers=dict(headers or {}), method=method.upper()
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return HttpResponse(
                    int(response.status), response.read(), dict(response.headers.items())
                )
        except urllib.error.HTTPError as exc:
            # A status carrying an error body is still an answer; the caller reads it.
            return HttpResponse(int(exc.code), exc.read(), dict(exc.headers.items()))
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            # No status to interpret, and the OS message may quote the URL we sent.
            raise ApiError(f"network request failed ({type(exc).__name__})") from None


class InstrumentedTransport:
    """Wraps a transport and keeps a secret-free record of every call made."""

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
        timeout: float = DEFAULT_TIMEOUT,
    ) -> HttpResponse:
        started = self.clock()
        endpoint = endpoint_of(url)
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
                    self._elapsed(started),
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
                self._elapsed(started),
                response.ok,
                "" if response.ok else "HttpError",
            )
        )
        return response

    def traces_since(self, index: int) -> tuple[ApiCallTrace, ...]:
        return tuple(self.traces[index:])

    def _elapsed(self, started: float) -> int:
        return max(0, round((self.clock() - started) * 1000))


def endpoint_of(url: str) -> str:
    """Scheme, host and path. The query string is where the credentials are."""
    parsed = urlsplit(url)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"


__all__ = [
    "DEFAULT_TIMEOUT",
    "ApiCallTrace",
    "HttpResponse",
    "HttpTransport",
    "InstrumentedTransport",
    "UrllibTransport",
    "endpoint_of",
]
