from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Protocol

import httpx

from mekiki_engine.domain import SourcePlatform

# A desktop browser identity: the marketplaces serve their regular pages and APIs to it.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
)


class SourceError(RuntimeError):
    """A marketplace could not be searched (blocked, changed format, network down…)."""


@dataclass(frozen=True, slots=True)
class FoundListing:
    source: SourcePlatform
    external_id: str
    title: str
    price_jpy: int
    url: str
    thumbnail_url: str | None = None
    # None when the results do not say who pays the Japanese shipping.
    shipping_included: bool | None = None
    listed_at: str | None = None
    ends_at: str | None = None
    bids: int | None = None


class Source(Protocol):
    platform: SourcePlatform

    def search(
        self,
        query: str,
        *,
        limit: int,
        price_min_jpy: int | None = None,
        price_max_jpy: int | None = None,
        page: int = 0,
    ) -> list[FoundListing]:
        """Newest listings first; an empty query lists the whole card category.

        ``page`` 0 is the first page of results; a short page means there are no more.
        """
        ...


# Yahoo! JAPAN has refused visitors from the EEA and the UK since 2022, with a notice page.
EEA_BLOCK_MARKER = "欧州経済領域"
EEA_BLOCK_MESSAGE = (
    "Yahoo! JAPAN bloque l'accès depuis l'Europe : cherchez plutôt via Neokyo, "
    "qui donne accès à Yahoo Auctions et Yahoo Fleamarket"
)

# Seconds between two requests to the same host. Mercari's API gets the most room: it is
# undocumented and its maintainers never published a limit.
HOST_INTERVALS_S = {"api.mercari.jp": 6.0}
DEFAULT_INTERVAL_S = 3.0


class PoliteClient:
    """Shared HTTP client that leaves a minimum delay between two requests to one host.

    The scanner runs a few dozen searches per hour from a home connection; spacing them
    keeps it far below anything that looks like abuse.
    """

    def __init__(
        self,
        *,
        intervals_s: dict[str, float] | None = None,
        default_interval_s: float = DEFAULT_INTERVAL_S,
        timeout_s: float = 20.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.intervals_s = HOST_INTERVALS_S if intervals_s is None else intervals_s
        self.default_interval_s = default_interval_s
        self._last_call: dict[str, float] = {}
        self._lock = threading.Lock()
        self.http = httpx.Client(
            timeout=timeout_s,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT, "Accept-Language": "ja,en;q=0.8"},
            transport=transport,
        )

    def request(self, method: str, url: str, **kwargs: object) -> httpx.Response:
        host = httpx.URL(url).host
        # Book the next free slot for this host, then wait outside the lock so a background
        # scan of one site never delays a manual search on another.
        with self._lock:
            interval = self.intervals_s.get(host, self.default_interval_s)
            slot = max(time.monotonic(), self._last_call.get(host, -interval) + interval)
            self._last_call[host] = slot
        time.sleep(max(0.0, slot - time.monotonic()))
        try:
            response = self.http.request(method, url, **kwargs)  # type: ignore[arg-type]
        except httpx.HTTPError as error:
            raise SourceError(f"{host} : {error.__class__.__name__}") from error
        if response.status_code == 429:
            raise SourceError(f"{host} limite les requêtes (429), réessayez plus tard")
        if response.status_code == 403 and EEA_BLOCK_MARKER in response.text:
            raise SourceError(EEA_BLOCK_MESSAGE)
        if response.status_code >= 400:
            raise SourceError(f"{host} a répondu {response.status_code}")
        return response

    def close(self) -> None:
        self.http.close()


def search_safely(
    source: Source,
    query: str,
    *,
    limit: int,
    price_min_jpy: int | None = None,
    price_max_jpy: int | None = None,
    page: int = 0,
) -> list[FoundListing]:
    """Runs ``source.search``, turning any unexpected failure into a ``SourceError``.

    Marketplace pages change without notice; a parsing bug on one site must cost its results,
    not the whole scan or discovery.
    """
    try:
        return source.search(
            query,
            limit=limit,
            price_min_jpy=price_min_jpy,
            price_max_jpy=price_max_jpy,
            page=page,
        )
    except SourceError:
        raise
    except Exception as error:
        raise SourceError(f"réponse inattendue ({error.__class__.__name__} : {error})") from error
