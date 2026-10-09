import json
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from conftest import FakeMarketplace
from fastapi.testclient import TestClient

from mekiki_engine.domain import SourcePlatform
from mekiki_engine.scanner import availability
from mekiki_engine.scanner.sources.base import PoliteClient
from mekiki_engine.services import translation
from mekiki_engine.services.translation import chunks

DESCRIPTION = "美品です。\nスリーブに入れて保管していました。\n\n即購入OKです！"


@pytest.fixture(autouse=True)
def fresh_cache() -> None:
    translation._cache.clear()


class FakeTranslators:
    """MyMemory and DeepL: each text comes back as "FR(…)"."""

    def __init__(self, *, quota_left: bool = True, deepl_key: str = "good-key:fx") -> None:
        self.quota_left = quota_left
        self.deepl_key = deepl_key
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.host == "api.mymemory.translated.net":
            if not self.quota_left:
                return httpx.Response(200, json={"quotaFinished": True, "responseStatus": 429})
            text = parse_qs(urlsplit(str(request.url)).query)["q"][0]
            return httpx.Response(
                200, json={"responseData": {"translatedText": f"FR({text})"}, "responseStatus": 200}
            )
        assert request.url.host == "api-free.deepl.com"
        if request.headers["Authorization"] != f"DeepL-Auth-Key {self.deepl_key}":
            return httpx.Response(403, json={"message": "Wrong key"})
        if request.url.path.endswith("/usage"):
            return httpx.Response(200, json={"character_count": 0, "character_limit": 500000})
        [text] = json.loads(request.content)["text"]
        return httpx.Response(200, json={"translations": [{"text": f"DEEPL({text})"}]})


def use(client: TestClient, fake: FakeTranslators) -> None:
    client.app.state.http = PoliteClient(  # type: ignore[attr-defined]
        intervals_s={}, default_interval_s=0, transport=httpx.MockTransport(fake)
    )


def test_long_texts_are_cut_between_sentences_within_the_byte_limit() -> None:
    sentence = "これはとても長い説明文です。"
    pieces = chunks(sentence * 40, 480)

    assert all(len(piece.encode()) <= 480 for piece in pieces)
    assert all(piece.endswith("。") for piece in pieces)
    assert "".join(pieces) == sentence * 40
    # Short lines travel together, blank ones are dropped.
    assert chunks(DESCRIPTION, 480) == [
        "美品です。\nスリーブに入れて保管していました。\n即購入OKです！"
    ]


def test_descriptions_are_translated_for_free_then_kept(client: TestClient) -> None:
    fake = FakeTranslators()
    use(client, fake)

    first = client.post("/translate", json={"text": DESCRIPTION})
    again = client.post("/translate", json={"text": DESCRIPTION})

    assert first.json()["provider"] == "mymemory"
    assert first.json()["text"].startswith("FR(美品です。")
    assert again.json() == first.json()
    assert len(fake.requests) == 1


def test_a_spent_free_quota_says_how_to_go_on(client: TestClient) -> None:
    use(client, FakeTranslators(quota_left=False))

    response = client.post("/translate", json={"text": DESCRIPTION})

    assert response.status_code == 502
    assert "ajoutez une clé DeepL" in response.json()["detail"]


def test_a_deepl_key_is_checked_kept_secret_and_used(client: TestClient) -> None:
    fake = FakeTranslators()
    use(client, fake)
    assert client.get("/settings/translation").json()["deepl_configured"] is False

    refused = client.put("/settings/translation", json={"key": "wrong-key-123:fx"})
    saved = client.put("/settings/translation", json={"key": "good-key:fx"})
    translated = client.post("/translate", json={"text": DESCRIPTION}).json()

    assert refused.status_code == 422
    assert saved.json() == {"provider": "deepl", "deepl_configured": True}
    assert "good-key" not in saved.text
    assert translated == {"provider": "deepl", "text": f"DEEPL({DESCRIPTION.strip()})"}
    assert client.delete("/settings/translation").json()["deepl_configured"] is False


def test_mercari_listings_come_with_their_description(
    client: TestClient, marketplace: FakeMarketplace
) -> None:
    marketplace.item_details["m1000000"] = {"description": "  美品です。\r\n即購入OK  "}

    checked = client.get("/listings/mercari/m1000000/availability").json()

    assert checked["description"] == "美品です。\n即購入OK"


def test_rakuma_listings_come_with_their_description() -> None:
    page = (
        '<meta property="product:availability" content="in stock">'
        '<div class="item__description only__pc"><h4>商品説明</h4>'
        '<div class="item__description__line-limited">'
        '<span class="notranslate-otft"> 美品です。<br>即購入OK &amp; 送料無料</span>\n'
        "</div></div>"
    )
    client = PoliteClient(
        intervals_s={},
        default_interval_s=0,
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, text=page)),
    )

    checked = availability.check_listing(client, SourcePlatform.RAKUMA, "a" * 32)

    assert checked.description == "美品です。\n即購入OK & 送料無料"
