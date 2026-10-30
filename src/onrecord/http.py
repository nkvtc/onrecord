"""One shared, polite HTTP client.

These are public-interest government servers. Identify ourselves, go slowly,
back off when told to.
"""

from __future__ import annotations

import os
import time

import httpx

USER_AGENT = os.environ.get(
    "ONRECORD_USER_AGENT", "onrecord/0.1 (open-source civic data project; polite crawler)"
)


# Longest we'll wait when a server says "retry after N seconds".
MAX_RETRY_WAIT = 60


class Http:
    def __init__(self, min_interval: float = 0.5, retries: int = 3, timeout: float = 60.0):
        self.client = httpx.Client(
            headers={"User-Agent": USER_AGENT},
            timeout=timeout,
            follow_redirects=True,
        )
        self.min_interval = min_interval
        self.retries = retries
        self._last = 0.0

    def request(self, method: str, url: str, **kwargs) -> httpx.Response:
        for attempt in range(self.retries + 1):
            wait = self.min_interval - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            try:
                resp = self.client.request(method, url, **kwargs)
            except httpx.TransportError:
                if attempt == self.retries:
                    raise
                time.sleep(2**attempt)
                continue
            if resp.status_code in (429, 500, 502, 503, 504) and attempt < self.retries:
                retry_after = resp.headers.get("Retry-After", "")
                delay = float(retry_after) if retry_after.isdigit() else 2**attempt
                if delay > MAX_RETRY_WAIT:
                    # e.g. a daily quota is used up: fail this source now instead of
                    # stalling every other source for hours. The next run retries.
                    resp.raise_for_status()
                time.sleep(delay)
                continue
            resp.raise_for_status()
            return resp
        raise RuntimeError("unreachable")

    def get(self, url: str, **kwargs) -> httpx.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs) -> httpx.Response:
        return self.request("POST", url, **kwargs)

    def close(self) -> None:
        self.client.close()
