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
from mekiki_engine.scanner.sources.base import (
    FoundListing,
    PoliteClient,
    SiteBlocked,
    SourceError,
)

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
            # Eevee Heroes (S6a): Japanese cards on Cardmarket, none in TCGdex.
            {
                "idProduct": 565900,
                "name": "Pikachu V [Thunderbolt]",
                "idCategory": 51,
                "categoryName": "Pokémon Single",
                "idExpansion": 4239,
                "idMetacard": 0,
                "dateAdded": "2021-05-21 11:50:26",
            },
            {
                "idProduct": 566300,
                "name": "Pikachu V [Thunderbolt]",
                "idCategory": 51,
                "categoryName": "Pokémon Single",
                "idExpansion": 4239,
                "idMetacard": 0,
                "dateAdded": "2021-05-21 11:50:26",
            },
            {
                "idProduct": 566301,
                "name": "Pikachu V [Thunderbolt]",
                "idCategory": 51,
                "categoryName": "Pokémon Single",
                "idExpansion": 4239,
                "idMetacard": 0,
                "dateAdded": "2021-05-21 11:50:26",
            },
            {
                "idProduct": 565901,
                "name": "Leafeon V [Leaf Blade]",
                "idCategory": 51,
                "categoryName": "Pokémon Single",
                "idExpansion": 4239,
                "idMetacard": 0,
                "dateAdded": "2021-05-21 11:50:26",
            },
            {
                "idProduct": 566302,
                "name": "Leafeon V [Leaf Blade]",
                "idCategory": 51,
                "categoryName": "Pokémon Single",
                "idExpansion": 4239,
                "idMetacard": 0,
                "dateAdded": "2021-05-21 11:50:26",
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
            },
            {
                "idProduct": 2,
                "name": "Eevee Heroes Booster",
                "idCategory": 52,
                "categoryName": "Pokémon Booster",
                "idExpansion": 4239,
                "idMetacard": 0,
                "dateAdded": "2021-05-21 11:50:26",
            },
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
            {"idProduct": 565900, "idCategory": 51, "avg30": 3},
            {"idProduct": 566300, "idCategory": 51, "avg30": 30},
            {"idProduct": 566301, "idCategory": 51, "avg30": 200},
            {"idProduct": 565901, "idCategory": 51, "avg30": 2},
            {"idProduct": 566302, "idCategory": 51, "avg30": 60},
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


# A set TCGdex only has in Chinese: no Japanese card, no Cardmarket expansion.
TCGDEX_CHINESE_SET = """const set: Set = {
	id: 'S6a',
	name: { ja: 'イーブイヒーローズ', 'zh-tw': '伊布英雄' },
	cardCount: { official: 69 }
}
"""


def tcgplayer_card(product_id: int, name: str, number: str, rarity: str) -> dict[str, object]:
    return {
        "productId": product_id,
        "name": f"{name} - {number}",
        "extendedData": [
            {"name": "Number", "value": number},
            {"name": "Rarity", "value": rarity},
        ],
    }


# TCGCSV's export of TCGplayer's Japanese Eevee Heroes. Leafeon V's versions are not in the
# same order by price as on Cardmarket: they must stay unlinked.
TCGCSV_FILES = {
    "groups": [{"groupId": 23637, "name": "S6a: Eevee Heroes"}],
    "23637/products": [
        {"productId": 1, "name": "Eevee Heroes Booster Box", "extendedData": []},
        tcgplayer_card(10, "Pikachu V", "047/069", "Double Rare"),
        tcgplayer_card(11, "Pikachu V", "084/069", "Super Rare"),
        tcgplayer_card(12, "Pikachu V", "085/069", "Super Rare"),
        tcgplayer_card(20, "Leafeon V", "010/069", "Double Rare"),
        tcgplayer_card(21, "Leafeon V", "080/069", "Super Rare"),
    ],
    "23637/prices": [
        {"productId": 10, "marketPrice": 2.5},
        {"productId": 11, "marketPrice": 25.0},
        {"productId": 12, "marketPrice": 180.0, "lowPrice": 150.0},
        {"productId": 20, "marketPrice": 50.0},
        {"productId": 21, "marketPrice": 1.0},
    ],
}


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
        "data-asia/S/S6a.ts": TCGDEX_CHINESE_SET,
        "data-asia/S/S6a/047.ts": tcgdex_card("x", "Double rare", "[]").replace("ja:", "'zh-tw':"),
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
    """Fake Cardmarket file server and fake GitHub for the TCGdex index and PokéAPI names."""
    if request.url.host == "raw.githubusercontent.com":
        from test_names import SPECIES

        return httpx.Response(200, text=SPECIES)
    if request.url.host == "api.github.com":
        return httpx.Response(200, text="0123456789abcdef")
    if request.url.host == "codeload.github.com":
        return httpx.Response(200, content=tcgdex_archive())
    if request.url.host == "tcgcsv.com":
        path = request.url.path.removeprefix("/tcgplayer/85/")
        if path not in TCGCSV_FILES:
            return httpx.Response(404, text="Not Found")
        return httpx.Response(200, json={"success": True, "results": TCGCSV_FILES[path]})
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
        if self.platform in self.marketplace.blocked_sites:
            raise SiteBlocked("limite les requêtes (test)")
        if query in self.marketplace.failing_queries:
            raise SourceError("page en erreur (test)")
        return list(self.marketplace.listings.get(self.platform, []))[:limit]


class FakeMarketplace:
    def __init__(self) -> None:
        self.listings: dict[SourcePlatform, list[FoundListing]] = {}
        self.failures: set[SourcePlatform] = set()
        # Sites answering 429 or 403: a scan must not ask them again for the next card.
        self.blocked_sites: set[SourcePlatform] = set()
        self.failing_queries: set[str] = set()
        self.queries: list[tuple[SourcePlatform, str]] = []
        # Mercari listings answered as sold when the engine checks them.
        self.sold: set[str] = set()
        self.checked: list[str] = []
        # Rakuma listings' condition, as their page writes it ("未使用に近い").
        self.rakuma_conditions: dict[str, str] = {}
        # Rakuma listings' seller: shop id, and the sun, cloud and rain ratings.
        self.rakuma_sellers: dict[str, tuple[str, int, int, int]] = {}
        self.tcgcsv_down = False
        # Extra fields of Mercari items, as their API gives them: seller, description.
        self.item_details: dict[str, dict[str, object]] = {}

    def handle(self, request: httpx.Request) -> httpx.Response:
        """Mercari's item API and Rakuma's item pages; everything else as cardmarket_handler."""
        if request.url.host == "api.mercari.jp" and request.url.path == "/items/get":
            item_id = request.url.params["id"]
            self.checked.append(item_id)
            status = "sold_out" if item_id in self.sold else "on_sale"
            data = {
                "id": item_id,
                "status": status,
                "item_condition": {"id": 3},
                **self.item_details.get(item_id, {}),
            }
            return httpx.Response(200, json={"result": "OK", "data": data})
        if request.url.host == "tcgcsv.com" and self.tcgcsv_down:
            return httpx.Response(503, text="Service Unavailable")
        if request.url.host == "item.fril.jp":
            item_id = request.url.path.strip("/")
            self.checked.append(item_id)
            condition = self.rakuma_conditions.get(item_id, "")
            page = (
                '<meta property="product:availability" content="in stock">'
                f"<table><tr><th>商品の状態</th><td>{condition}</td></tr></table>"
            )
            if item_id in self.rakuma_sellers:
                shop, sun, cloud, rain = self.rakuma_sellers[item_id]
                page += (
                    '<a class="shopinfo-wrap shop_link clearfix"\n'
                    f' href="https://fril.jp/shop/{shop}"></a>'
                    f'<i class="icon-sun icon_review_sun"></i><span>{sun}</span>'
                    f'<i class="icon-cloud icon_review_cloud"></i><span>{cloud}</span>'
                    f'<i class="icon-rain icon_review_rain"></i><span>{rain}</span>'
                )
            return httpx.Response(200, text=page)
        return cardmarket_handler(request)

    def factory(self) -> Callable[[SourcePlatform, PoliteClient, Game], FakeSource]:
        return lambda platform, _client, _game: FakeSource(self, platform)


@pytest.fixture
def marketplace() -> FakeMarketplace:
    return FakeMarketplace()


@pytest.fixture
def client(tmp_path: Path, marketplace: FakeMarketplace) -> Iterator[TestClient]:
    app = create_app(
        load_config(data_dir=str(tmp_path), background_jobs=False),
        http_transport=httpx.MockTransport(marketplace.handle),
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
