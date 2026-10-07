import json
from urllib.parse import parse_qs, urlsplit

import httpx
from conftest import sign_in
from fastapi.testclient import TestClient

from mekiki_engine.domain import Game, SalePlatform
from mekiki_engine.models import CardmarketProduct, Item
from mekiki_engine.resale import drafts
from mekiki_engine.resale.ebay import SEARCH_URL, TOKEN_URL, EbayBrowse
from mekiki_engine.scanner.sources.base import PoliteClient


def ebay_summary(item_id: str, price: str, currency: str = "EUR") -> dict[str, object]:
    return {
        "itemId": item_id,
        "title": f"Pikachu 201/165 {item_id}",
        "price": {"value": price, "currency": currency},
        "itemWebUrl": f"https://www.ebay.fr/itm/{item_id}",
        "image": {"imageUrl": f"https://i.ebayimg.com/{item_id}.jpg"},
        "condition": "Occasion",
        "shippingOptions": [{"shippingCost": {"value": "2.50", "currency": "EUR"}}],
        "itemLocation": {"country": "FR"},
    }


class FakeEbay:
    def __init__(self) -> None:
        self.token_calls = 0
        self.searches: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if str(request.url) == TOKEN_URL:
            self.token_calls += 1
            return httpx.Response(200, json={"access_token": "app-token", "expires_in": 7200})
        assert str(request.url).startswith(SEARCH_URL)
        self.searches.append(request)
        items = [ebay_summary("a", "30.00"), ebay_summary("b", "12.50"), ebay_summary("c", "18")]
        items.append(ebay_summary("usd", "5.00", currency="USD"))
        return httpx.Response(200, json={"total": 41, "itemSummaries": items})


def browse(fake: FakeEbay) -> EbayBrowse:
    client = PoliteClient(intervals_s={}, default_interval_s=0, transport=httpx.MockTransport(fake))
    return EbayBrowse(client, "client-id", "client-secret", "EBAY_FR")


def make_item(**fields: object) -> Item:
    values: dict[str, object] = {
        "game": "pokemon",
        "name": "Pikachu",
        "set_code": "sv2a",
        "card_number": "201/165",
        "rarity": "SAR",
        "language": "ja",
        "condition": "Near Mint",
        "price_jpy": 1000,
    }
    return Item(**(values | fields))


def test_search_queries_keep_the_name_and_the_printed_number() -> None:
    assert drafts.search_query("Primal Kyogre EX [Tidal Storm]", "201/165") == (
        "Primal Kyogre EX 201/165"
    )
    assert drafts.search_query("Nami (OP05-001)", "OP05-001") == "Nami OP05-001"
    assert drafts.number_in_label("SV2a 201/165 · SAR") == "201/165"
    assert drafts.number_in_label("OP05-119 · parallèle") == "OP05-119"
    assert drafts.number_in_label(None) is None


def test_drafts_describe_the_card_and_suggest_a_price() -> None:
    product = CardmarketProduct(id_product=1, game="pokemon", name="Pikachu", avg30_cents=4200)

    draft = drafts.item_draft(make_item(), product, SalePlatform.VINTED)

    assert draft.title == "Pikachu 201/165 SAR SV2A - Carte Pokémon japonaise"
    assert "Rareté : SAR" in draft.description
    assert "État : Near Mint" in draft.description
    assert (draft.price_cents, draft.price_source) == (4200, "avg30")

    listed = drafts.item_draft(make_item(listing_price_cents=5000), product, SalePlatform.EBAY)
    assert (listed.price_cents, listed.price_source) == (5000, "listing")
    assert drafts.item_draft(make_item(), None, SalePlatform.EBAY).price_cents is None


def test_draft_titles_fit_ebay_and_skip_a_repeated_set_code() -> None:
    one_piece = make_item(
        game="one_piece", name="Monkey.D.Luffy", set_code="OP05", card_number="OP05-119"
    )
    assert drafts.item_draft(one_piece, None, SalePlatform.EBAY).title == (
        "Monkey.D.Luffy OP05-119 SAR - Carte One Piece japonaise"
    )

    long_name = make_item(name="Pikachu " * 12, grading="PSA 10")
    title = drafts.item_draft(long_name, None, SalePlatform.EBAY).title
    assert len(title) <= drafts.TITLE_MAX
    assert title.startswith("PSA 10 Pikachu")


def test_ebay_search_keeps_euro_listings_and_caches_the_token_and_results() -> None:
    fake = FakeEbay()
    ebay = browse(fake)

    result = ebay.search("Pikachu 201/165")
    again = ebay.search("pikachu 201/165 ")

    assert again is result
    assert fake.token_calls == 1
    assert len(fake.searches) == 1
    request = fake.searches[0]
    assert request.headers["Authorization"] == "Bearer app-token"
    assert request.headers["X-EBAY-C-MARKETPLACE-ID"] == "EBAY_FR"
    params = parse_qs(urlsplit(str(request.url)).query)
    assert params["category_ids"] == ["183454"]
    assert result.total == 41
    assert result.prices == [1250, 1800, 3000]
    assert result.median_cents == 1800
    assert result.listings[0].shipping_cents == 250


def test_resale_prices_without_ebay_keys_still_give_links(client: TestClient) -> None:
    response = client.get("/resale/prices", params={"q": " Pikachu  201/165 · SAR"})

    assert response.status_code == 200
    body = response.json()
    assert body["ebay"] == {
        "configured": False,
        "error": None,
        "total": 0,
        "min_cents": None,
        "median_cents": None,
        "max_cents": None,
        "listings": [],
    }
    assert body["query"] == "Pikachu 201/165 SAR"
    assert "LH_Sold=1" in body["links"]["ebay_sold"]
    assert body["links"]["vinted"].startswith("https://www.vinted.fr/catalog?search_text=Pikachu")
    assert client.get("/resale/prices").status_code == 422


def test_resale_prices_use_ebay_when_configured(client: TestClient) -> None:
    fake = FakeEbay()
    client.app.state.ebay = browse(fake)  # type: ignore[attr-defined]
    with client.app.state.session_factory() as session:  # type: ignore[attr-defined]
        session.add(
            CardmarketProduct(id_product=9, game=Game.POKEMON.value, name="Pikachu [Thunder]")
        )
        session.commit()

    body = client.get(
        "/resale/prices", params={"product_id": 9, "label": "SV2a 201/165 · SAR"}
    ).json()

    assert body["query"] == "Pikachu 201/165"
    assert body["ebay"]["configured"] is True
    assert body["ebay"]["median_cents"] == 1800
    assert [listing["item_id"] for listing in body["ebay"]["listings"]] == ["a", "b", "c"]


def test_listing_drafts_are_private_to_the_account(client: TestClient) -> None:
    lot = client.post("/lots", json={"label": "Colis"}).json()
    item = client.post(
        f"/lots/{lot['id']}/items",
        json={"game": "pokemon", "name": "Pikachu", "card_number": "201/165", "price_jpy": 900},
    ).json()

    draft = client.get(f"/items/{item['id']}/listing-draft", params={"platform": "vinted"})
    assert draft.status_code == 200
    assert draft.json()["new_listing_url"] == "https://www.vinted.fr/items/new"
    assert draft.json()["query"] == "Pikachu 201/165"
    bad_platform = client.get(f"/items/{item['id']}/listing-draft", params={"platform": "x"})
    assert bad_platform.status_code == 422

    sign_in(client, "misty@example.com")
    other = client.get(f"/items/{item['id']}/listing-draft", params={"platform": "ebay"})
    assert other.status_code == 404
    assert json.loads(other.text)["detail"].startswith("item")


def test_env_files_fill_missing_variables_only(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from mekiki_engine.config import load_env_file

    env = tmp_path / ".env"
    env.write_text(
        "# eBay\nMEKIKI_EBAY_CLIENT_ID='app-id'\nMEKIKI_EBAY_CLIENT_SECRET=from-file\nnot a line\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("MEKIKI_EBAY_CLIENT_ID", raising=False)
    monkeypatch.setenv("MEKIKI_EBAY_CLIENT_SECRET", "from-env")

    load_env_file(env)
    load_env_file(tmp_path / "missing.env")

    import os

    assert os.environ["MEKIKI_EBAY_CLIENT_ID"] == "app-id"
    assert os.environ["MEKIKI_EBAY_CLIENT_SECRET"] == "from-env"
