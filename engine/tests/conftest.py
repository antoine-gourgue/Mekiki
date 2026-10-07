import io
import zipfile
from collections.abc import Callable, Iterator
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from mekiki_engine.app import create_app
from mekiki_engine.config import load_config
from mekiki_engine.domain import Game, SourcePlatform
from mekiki_engine.scanner.sources.base import FoundListing, PoliteClient, SourceError

CARDMARKET_FILES = {
    "products_singles_6.json": {
        "version": 1,
        "createdAt": "2026-10-07T12:59:46+0200",
        "products": [
            {
                "idProduct": 719448,
                "name": "Charizard ex [Brave Wing | Explosive Vortex]",
                "idCategory": 51,
                "categoryName": "Pokémon Single",
                "idExpansion": 5328,
                "idMetacard": 422297,
                "dateAdded": "2023-06-16 10:00:00",
            },
            {
                "idProduct": 719654,
                "name": "Charizard ex [Brave Wing | Explosive Vortex]",
                "idCategory": 51,
                "categoryName": "Pokémon Single",
                "idExpansion": 5328,
                "idMetacard": 422297,
                "dateAdded": "2023-06-16 10:00:00",
            },
            {
                "idProduct": 719442,
                "name": "Bulbasaur [Leech Seed]",
                "idCategory": 51,
                "categoryName": "Pokémon Single",
                "idExpansion": 5328,
                "idMetacard": 2,
                "dateAdded": "2023-06-16 10:00:00",
            },
            {
                "idProduct": 700737,
                "name": "Pikachu [Thunder Shock]",
                "idCategory": 51,
                "categoryName": "Pokémon Single",
                "idExpansion": 5328,
                "idMetacard": 1,
                "dateAdded": "0000-00-00 00:00:00",
            },
        ],
    },
    "products_nonsingles_6.json": {
        "version": 1,
        "createdAt": "2026-10-07T12:59:46+0200",
        "products": [
            {
                "idProduct": 1,
                "name": "Pokémon Card 151 Booster",
                "idCategory": 52,
                "categoryName": "Pokémon Booster",
                "idExpansion": 5328,
                "idMetacard": 0,
                "dateAdded": "2023-06-16 10:00:00",
            }
        ],
    },
    "price_guide_6.json": {
        "version": 1,
        "createdAt": "2026-10-07T02:49:47+0200",
        "priceGuides": [
            {
                "idProduct": 719448,
                "idCategory": 51,
                "avg": 95.5,
                "low": 60,
                "trend": 92.1,
                "avg1": 99,
                "avg7": 94,
                "avg30": 90,
            },
            {
                "idProduct": 719654,
                "idCategory": 51,
                "avg": 382.53,
                "trend": 370.03,
                "avg30": 357.63,
            },
            {"idProduct": 719442, "idCategory": 51, "avg": 0.2, "trend": 0.15, "avg30": 0.2},
            {"idProduct": 700737, "idCategory": 51, "avg": 9.16, "low": 6.95, "trend": 8.64},
            {"idProduct": 999, "idCategory": 52, "avg": 3, "trend": 3},
        ],
    },
}


TCGDEX_SET = """const set: Set = {
	id: 'SV2a',
	name: { ja: 'ポケモンカード151' },
	cardCount: { official: 165 },
	thirdParty: { cardmarket: 5328 }
}
"""


def tcgdex_card(name: str, rarity: str, variants: str) -> str:
    return f"""const card: Card = {{
	set: Set,
	name: {{
		ja: "{name}",
		id: "Whatever",
	}},
	attacks: [{{ name: {{ ja: "ブレイブウイング" }}, damage: "60+" }}],
	variants: {variants},
	rarity: "{rarity}",
}};
"""


def tcgdex_archive() -> bytes:
    """A tiny copy of the tcgdex/cards-database repository: SV2a cards 001, 006 and 201."""
    files = {
        "data-asia/SV/SV2a.ts": TCGDEX_SET,
        "data-asia/SV/SV2a/001.ts": tcgdex_card(
            "フシギダネ",
            "Common",
            """[
		{ type: "normal", thirdParty: { cardmarket: 719442 } },
		{ type: "reverse", foil: "pokeball", thirdParty: { cardmarket: 837230 } },
		{ type: "reverse", foil: "masterball", thirdParty: { cardmarket: 837231 } },
	]""",
        ),
        "data-asia/SV/SV2a/006.ts": tcgdex_card(
            "リザードンex", "Double rare", '[{ type: "holo", thirdParty: { cardmarket: 719448 } }]'
        ),
        "data-asia/SV/SV2a/201.ts": tcgdex_card(
            "リザードンex",
            "Special illustration rare",
            '[{ type: "holo", thirdParty: { cardmarket: 719654 } }]',
        ),
        # A Chinese-only card shares the set and must be ignored.
        "data-asia/SV/SV2a/202.ts": tcgdex_card("x", "Common", "[]").replace("ja:", "'zh-tw':"),
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, text in files.items():
            archive.writestr(f"cards-database-master/{name}", text)
    return buffer.getvalue()


def cardmarket_handler(request: httpx.Request) -> httpx.Response:
    """Fake Cardmarket file server and fake GitHub for the TCGdex card index."""
    if request.url.host == "api.github.com":
        return httpx.Response(200, text="0123456789abcdef")
    if request.url.host == "codeload.github.com":
        return httpx.Response(200, content=tcgdex_archive())
    name = request.url.path.rsplit("/", 1)[-1]
    if name not in CARDMARKET_FILES:
        # Cardmarket answers 403 rather than 404 for missing files.
        return httpx.Response(403, text="<Error><Code>AccessDenied</Code></Error>")
    etag = f'"{name}"'
    if request.headers.get("If-None-Match") == etag:
        return httpx.Response(304)
    return httpx.Response(200, json=CARDMARKET_FILES[name], headers={"ETag": etag})


class FakeSource:
    """Stands in for a marketplace: returns ``listings[platform]`` or raises ``failures``."""

    def __init__(self, marketplace: "FakeMarketplace", platform: SourcePlatform) -> None:
        self.marketplace = marketplace
        self.platform = platform

    def search(
        self,
        query: str,
        *,
        limit: int,
        price_min_jpy: int | None = None,
        price_max_jpy: int | None = None,
        page: int = 0,
    ) -> list[FoundListing]:
        self.marketplace.queries.append((self.platform, query))
        if page:
            return []
        if self.platform in self.marketplace.failures:
            raise SourceError("bloqué (test)")
        return list(self.marketplace.listings.get(self.platform, []))[:limit]


class FakeMarketplace:
    def __init__(self) -> None:
        self.listings: dict[SourcePlatform, list[FoundListing]] = {}
        self.failures: set[SourcePlatform] = set()
        self.queries: list[tuple[SourcePlatform, str]] = []

    def factory(self) -> Callable[[SourcePlatform, PoliteClient, Game], FakeSource]:
        return lambda platform, _client, _game: FakeSource(self, platform)


@pytest.fixture
def marketplace() -> FakeMarketplace:
    return FakeMarketplace()


@pytest.fixture
def client(tmp_path: Path, marketplace: FakeMarketplace) -> Iterator[TestClient]:
    app = create_app(
        load_config(data_dir=str(tmp_path), background_jobs=False),
        http_transport=httpx.MockTransport(cardmarket_handler),
        source_factory=marketplace.factory(),
    )
    # Tests must not wait between fake requests.
    app.state.http.intervals_s = {}
    app.state.http.default_interval_s = 0
    # The context manager runs the lifespan, which releases the SQLite file at the end.
    with TestClient(app, base_url="http://127.0.0.1:18421") as test_client:
        sign_in(test_client, "ash@example.com")
        yield test_client


def sign_in(client: TestClient, email: str, password: str = "pikachu-2026") -> dict[str, object]:
    """Registers an account and sends its token with every following request."""
    response = client.post(
        "/auth/register",
        json={"email": email, "password": password, "display_name": email.split("@")[0]},
    )
    assert response.status_code == 201, response.text
    client.headers["Authorization"] = f"Bearer {response.json()['token']}"
    return response.json()
