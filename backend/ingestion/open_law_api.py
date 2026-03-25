from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, timedelta
from time import monotonic
from typing import Any
from xml.etree import ElementTree

import httpx
from pydantic import ConfigDict
from pydantic_settings import BaseSettings

from schemas.common import ObservationContext, parse_date_value
from storage.observability import get_logger, log_info


logger = get_logger(__name__)


class OpenLawApiSettings(BaseSettings):
    model_config = ConfigDict(env_prefix="LAW_API_", extra="ignore")

    oc: str = "test"
    base_url: str = "https://www.law.go.kr/DRF"
    timeout_seconds: float = 20.0
    max_retries: int = 3
    rate_limit_per_second: float = 5.0
    cache_ttl_seconds: int = 300


class AsyncRateLimiter:
    def __init__(self, rate_limit_per_second: float) -> None:
        self._interval = 0.0 if rate_limit_per_second <= 0 else 1.0 / rate_limit_per_second
        self._lock = asyncio.Lock()
        self._last_called = 0.0

    async def acquire(self) -> None:
        if self._interval == 0:
            return
        async with self._lock:
            now = monotonic()
            elapsed = now - self._last_called
            if elapsed < self._interval:
                await asyncio.sleep(self._interval - elapsed)
            self._last_called = monotonic()


def _xml_to_python(element: ElementTree.Element) -> Any:
    children = list(element)
    if not children:
        return element.text.strip() if element.text else ""
    grouped: dict[str, list[Any]] = {}
    for child in children:
        grouped.setdefault(child.tag, []).append(_xml_to_python(child))
    return {key: values if len(values) > 1 else values[0] for key, values in grouped.items()}


@dataclass(slots=True)
class ResponseCacheEntry:
    expires_at: float
    payload: Any


@dataclass
class OpenLawApiClient:
    settings: OpenLawApiSettings
    transport: httpx.AsyncBaseTransport | None = None
    _client: httpx.AsyncClient = field(init=False)
    _rate_limiter: AsyncRateLimiter = field(init=False)
    _cache: dict[tuple[str, tuple[tuple[str, str], ...]], ResponseCacheEntry] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=self.settings.base_url,
            timeout=self.settings.timeout_seconds,
            transport=self.transport,
        )
        self._rate_limiter = AsyncRateLimiter(self.settings.rate_limit_per_second)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def list_laws(
        self,
        context: ObservationContext,
        query: str | None = None,
        page: int = 1,
        display: int = 100,
    ) -> Any:
        params = {"target": "law", "type": "JSON", "page": page, "display": display}
        if query:
            params["query"] = query
        return await self._request("lawSearch.do", params, context)

    async def fetch_law_body(
        self,
        context: ObservationContext,
        law_id: str | None = None,
        mst: str | None = None,
    ) -> Any:
        params = {"target": "law", "type": "JSON"}
        if law_id:
            params["ID"] = law_id
        if mst:
            params["MST"] = mst
        if "ID" not in params and "MST" not in params:
            raise ValueError("law_id or mst must be provided")
        return await self._request("lawService.do", params, context)

    async def fetch_law_article_unit(
        self,
        context: ObservationContext,
        jo: str,
        law_id: str | None = None,
        mst: str | None = None,
    ) -> Any:
        params = {"target": "lawjosub", "type": "JSON", "JO": jo}
        if law_id:
            params["ID"] = law_id
        if mst:
            params["MST"] = mst
        if "ID" not in params and "MST" not in params:
            raise ValueError("law_id or mst must be provided")
        return await self._request("lawService.do", params, context)

    async def fetch_history_meta(
        self,
        context: ObservationContext,
        law_name: str | None,
        promulgated_at: date | None,
    ) -> Any | None:
        if not law_name and promulgated_at is None:
            return None

        params: dict[str, Any] = {"target": "law", "type": "JSON", "display": 20, "sort": "ddes"}
        if law_name:
            params["query"] = law_name
        if promulgated_at:
            date_text = promulgated_at.strftime("%Y%m%d")
            params["ancYd"] = f"{date_text}~{date_text}"
        return await self._request("lawSearch.do", params, context)

    async def _request(
        self,
        path: str,
        params: Mapping[str, Any],
        context: ObservationContext,
    ) -> Any:
        payload_params = {"OC": self.settings.oc, **params}
        cache_key = (
            path,
            tuple(sorted((key, str(value)) for key, value in payload_params.items())),
        )
        cached = self._cache.get(cache_key)
        now = monotonic()
        if cached and cached.expires_at > now:
            log_info(logger, "returning cached open api response", context, path=path)
            return cached.payload

        await self._rate_limiter.acquire()

        last_error: Exception | None = None
        for attempt in range(1, self.settings.max_retries + 1):
            try:
                log_info(logger, "requesting open api", context, path=path, attempt=attempt)
                response = await self._client.get(path, params=payload_params)
                if response.status_code == 429 or response.status_code >= 500:
                    raise httpx.HTTPStatusError(
                        f"retryable status code: {response.status_code}",
                        request=response.request,
                        response=response,
                    )
                response.raise_for_status()
                payload = self._parse_payload(response)
                self._cache[cache_key] = ResponseCacheEntry(
                    expires_at=now + self.settings.cache_ttl_seconds,
                    payload=payload,
                )
                return payload
            except (httpx.TimeoutException, httpx.HTTPStatusError, httpx.NetworkError) as error:
                last_error = error
                if attempt == self.settings.max_retries:
                    break
                await asyncio.sleep(0.3 * (2 ** (attempt - 1)))

        raise RuntimeError(f"open api request failed: {path}") from last_error

    @staticmethod
    def _parse_payload(response: httpx.Response) -> Any:
        content_type = response.headers.get("content-type", "")
        if "json" in content_type.lower():
            return response.json()

        text = response.text.strip()
        if text.startswith("{") or text.startswith("["):
            return json.loads(text)

        root = ElementTree.fromstring(text)
        return _xml_to_python(root)


def extract_law_name(payload: Any) -> str | None:
    if isinstance(payload, Mapping):
        for key in ("법령명한글", "법령명", "법령명_한글", "법령명한글명"):
            value = payload.get(key)
            if value:
                return str(value)
        for value in payload.values():
            found = extract_law_name(value)
            if found:
                return found
    if isinstance(payload, list):
        for item in payload:
            found = extract_law_name(item)
            if found:
                return found
    return None


def extract_promulgated_at(payload: Any) -> date | None:
    if isinstance(payload, Mapping):
        for key in ("공포일자", "공포일", "ancYd"):
            value = payload.get(key)
            parsed = parse_date_value(value)
            if parsed:
                return parsed
        for value in payload.values():
            found = extract_promulgated_at(value)
            if found:
                return found
    if isinstance(payload, list):
        for item in payload:
            found = extract_promulgated_at(item)
            if found:
                return found
    return None
