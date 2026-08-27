"""Shared outbound HTTP retry policy and error types."""

from __future__ import annotations

import random
import time
from collections.abc import Callable

import requests


class UpstreamError(requests.RequestException):
    """An upstream request failed after the configured retry policy."""

    def __init__(self, source: str, message: str, *, status_code: int | None = None):
        super().__init__(f"{source}: {message}")
        self.source = source
        self.status_code = status_code


class UpstreamValidationError(ValueError):
    """An upstream response was syntactically valid but unusable."""


def request_with_retry(
    request_func: Callable,
    *,
    source: str,
    method: str,
    url: str,
    timeout: float,
    retries: int = 3,
    backoff_base: float = 1.0,
    backoff_func: Callable[[int], float] | None = None,
    return_last_response: bool = False,
    transport_error_factory: Callable[[Exception], Exception] | None = None,
    **kwargs,
):
    """Perform one request with common timeout, connection, and 5xx handling."""
    if retries < 1:
        raise ValueError("retries must be at least 1")

    for attempt in range(retries):
        try:
            response = request_func(url, timeout=timeout, **kwargs)
        except (requests.Timeout, requests.ConnectionError) as exc:
            if attempt == retries - 1:
                if transport_error_factory is not None:
                    raise transport_error_factory(exc) from None
                raise UpstreamError(source, str(exc)) from exc
            time.sleep(backoff_func(attempt) if backoff_func else _backoff(backoff_base, attempt))
            continue

        status_code = getattr(response, "status_code", 200)
        if status_code == 429 or status_code >= 500:
            if attempt == retries - 1:
                if return_last_response:
                    return response
                raise UpstreamError(
                    source,
                    f"HTTP {status_code}",
                    status_code=status_code,
                )
            retry_after = getattr(response, "headers", {}).get("Retry-After")
            wait = (
                float(retry_after)
                if retry_after
                else backoff_func(attempt) if backoff_func else _backoff(backoff_base, attempt)
            )
            time.sleep(wait)
            continue
        return response

    raise AssertionError("unreachable")


def _backoff(base: float, attempt: int) -> float:
    return base * (2**attempt) + random.uniform(0, 0.5)
