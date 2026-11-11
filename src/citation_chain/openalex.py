"""Minimal OpenAlex client, with explicit failures and rate-limit handling."""
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

BASE = "https://api.openalex.org"
_ID = re.compile(r"(?:https?://openalex\.org/)?(W\d+)$", re.I)


class OpenAlexError(RuntimeError):
    pass


def work_id(value: str) -> str:
    value = value.strip()
    match = _ID.fullmatch(value)
    if not match:
        raise ValueError(f"Not an OpenAlex work ID: {value}")
    return match.group(1).upper()


def normalize_doi(value: str) -> str:
    value = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", value.strip(), flags=re.I)
    value = re.sub(r"^doi:\s*", "", value, flags=re.I)
    if not value.lower().startswith("10.") or "/" not in value:
        raise ValueError("Expected an OpenAlex W-ID or a DOI (10.xxxx/...).")
    return "https://doi.org/" + value


class OpenAlex:
    def __init__(self, api_key: str | None = None, timeout: int = 25):
        self.api_key = api_key if api_key is not None else os.getenv("OPENALEX_API_KEY", "")
        self.timeout = timeout

    def _request(self, path: str, params: dict[str, Any] | None = None) -> dict:
        query = dict(params or {})
        url = BASE + path + ("?" + urllib.parse.urlencode(query) if query else "")
        headers = {"User-Agent": "citation-chaining/0.1 (scholarly research; OpenAlex)", "Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = "Bearer " + self.api_key
        request = urllib.request.Request(url, headers=headers)
        for retry in range(4):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    return json.load(response)
            except urllib.error.HTTPError as exc:
                if exc.code == 404:
                    raise OpenAlexError(f"Work not found: {path}") from exc
                if exc.code in (429, 500, 502, 503, 504) and retry < 3:
                    wait = float(exc.headers.get("Retry-After", 1 + 2 * retry))
                    time.sleep(min(max(wait, 0.5), 15))
                    continue
                info = exc.read(500).decode("utf-8", "replace")
                raise OpenAlexError(f"OpenAlex HTTP {exc.code}: {info[:300]}") from exc
            except (urllib.error.URLError, TimeoutError) as exc:
                if retry < 3:
                    time.sleep(1 + retry)
                    continue
                raise OpenAlexError(f"Could not reach OpenAlex: {exc}") from exc
        raise OpenAlexError("OpenAlex request failed after retries")

    def get(self, identifier: str) -> dict:
        identifier = identifier.strip()
        try:
            key = work_id(identifier)
        except ValueError:
            key = normalize_doi(identifier)
        return self._request("/works/" + urllib.parse.quote(key, safe="/:"))

    def search(self, title: str, count: int = 5) -> list[dict]:
        return self._request("/works", {"search": title, "per_page": min(20, max(1, count))}).get("results", [])

    def batch(self, ids: list[str]) -> list[dict]:
        if not ids:
            return []
        if len(ids) > 100:
            raise ValueError("batch() accepts at most 100 IDs")
        query = "|".join(work_id(i) for i in ids)
        result = self._request("/works", {"filter": "ids.openalex:" + query, "per_page": 100})
        return result.get("results", [])

    def citing_page(self, cited_id: str, cursor: str = "*", per_page: int = 100) -> dict:
        return self._request("/works", {"filter": "cites:" + work_id(cited_id), "per_page": min(max(1, per_page), 100), "cursor": cursor})
