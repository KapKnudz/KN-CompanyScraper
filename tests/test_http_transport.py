import requests

import pytest

from kncompanyscraper.http_transport import UpstreamError, request_with_retry


class Response:
    def __init__(self, status_code, headers=None):
        self.status_code = status_code
        self.headers = headers or {}


def test_retries_rate_limit_and_server_errors_then_returns_success(monkeypatch):
    responses = [Response(429, {"Retry-After": "2"}), Response(503), Response(200)]
    calls = []
    sleeps = []

    def request(url, timeout, **kwargs):
        calls.append((url, timeout, kwargs))
        return responses.pop(0)

    monkeypatch.setattr("kncompanyscraper.http_transport.time.sleep", sleeps.append)

    result = request_with_retry(
        request,
        source="test upstream",
        method="GET",
        url="https://example.test/data",
        timeout=4,
        retries=3,
        backoff_func=lambda attempt: attempt + 0.5,
        params={"q": "x"},
    )

    assert result.status_code == 200
    assert len(calls) == 3
    assert sleeps == [2.0, 1.5]


def test_retries_transport_errors_and_maps_exhaustion(monkeypatch):
    calls = []
    sleeps = []

    def request(url, timeout, **kwargs):
        calls.append(url)
        raise requests.Timeout("timed out")

    monkeypatch.setattr("kncompanyscraper.http_transport.time.sleep", sleeps.append)

    with pytest.raises(UpstreamError, match="test upstream") as error:
        request_with_retry(
            request,
            source="test upstream",
            method="GET",
            url="https://example.test/data",
            timeout=4,
            retries=3,
            backoff_func=lambda attempt: attempt + 1,
        )

    assert len(calls) == 3
    assert sleeps == [1, 2]
    assert error.value.status_code is None


def test_returns_last_retry_response_when_requested(monkeypatch):
    response = Response(500)
    monkeypatch.setattr("kncompanyscraper.http_transport.time.sleep", lambda _: None)

    result = request_with_retry(
        lambda url, **kwargs: response,
        source="test upstream",
        method="GET",
        url="https://example.test/data",
        timeout=4,
        retries=2,
        backoff_func=lambda attempt: 0,
        return_last_response=True,
    )

    assert result is response
