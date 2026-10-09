import json
from datetime import date, timedelta
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from conftest import sign_in
from fastapi.testclient import TestClient

from mekiki_engine.browser.service import Browsers
from mekiki_engine.domain import Game, SalePlatform
from mekiki_engine.models import CardmarketProduct, Item
from mekiki_engine.resale import drafts
from mekiki_engine.resale.ebay import (
    INSIGHTS_SCOPE,
    INSIGHTS_URL,
    SEARCH_URL,
    TOKEN_URL,
    EbayBrowse,
)
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


def test_dotted_one_piece_names_are_searched_and_matched_as_sellers_write_them(
    client: TestClient,
) -> None:
    from mekiki_engine.resale.service import card_names

    product = CardmarketProduct(
        id_product=8, game=Game.ONE_PIECE.value, name="Monkey.D.Luffy (OP05-119)"
    )
    with client.app.state.session_factory() as session:  # type: ignore[attr-defined]
        session.add(product)
        session.commit()
        found = card_names(session, product, "Monkey.D.Luffy")

    assert found == ["Luffy"]
    assert drafts.search_query(product.name, "OP05-119") == "Monkey D Luffy OP05-119"


def test_the_printing_tells_which_listings_of_the_number_count() -> None:
    from mekiki_engine.resale.service import printing_version
    from mekiki_engine.scanner.tracking import Printing

    assert printing_version(None) is None
    assert printing_version(Printing(Game.ONE_PIECE, code="op05-119")) == "regular"
    assert printing_version(Printing(Game.ONE_PIECE, code="op05-119", version="manga")) == "manga"
    assert printing_version(Printing(Game.POKEMON, number=25, total=165)) == "regular"
    pokeball = Printing(Game.POKEMON, number=25, total=165, mirror="pokeball")
    assert printing_version(pokeball) == "pokeball"


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


class FakeEbaySearch(FakeEbay):
    """Answers a card search with other printings, a lot and a graded copy among its own."""

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if str(request.url) == TOKEN_URL:
            return httpx.Response(200, json={"access_token": "app-token", "expires_in": 7200})
        titles = {
            "a": "Pikachu 201/165 SAR japonaise",
            "b": "Pikachu 201/165 SAR japanese NM",
            "c": "Pikachu 173/165 AR",
            "d": "Lot de 3 Pikachu 201/165",
            "e": "PSA 10 Pikachu 201/165",
        }
        prices = {"a": "40.00", "b": "44.00", "c": "9.00", "d": "95.00", "e": "250.00"}
        items = [ebay_summary(i, prices[i]) | {"title": title} for i, title in titles.items()]
        return httpx.Response(200, json={"total": 5, "itemSummaries": items})


def test_ebay_listings_count_only_the_card_once_its_number_is_known() -> None:
    from mekiki_engine.resale.service import ebay_prices

    prices = ebay_prices(browse(FakeEbaySearch()), "Pikachu 201/165", "201/165", ["Pikachu"])

    assert [listing.item_id for listing in prices.listings] == ["a", "b"]
    assert prices.median_cents == 4200
    assert prices.total == 5


def test_a_page_in_place_of_ebay_s_results_is_an_ebay_error(client: TestClient) -> None:
    from mekiki_engine.resale.service import ebay_prices

    def portal(request: httpx.Request) -> httpx.Response:
        if str(request.url) == TOKEN_URL:
            return httpx.Response(200, json={"access_token": "app-token", "expires_in": 7200})
        return httpx.Response(200, text="<html>Maintenance</html>")

    prices = ebay_prices(browse(portal), "Pikachu 201/165", "201/165")  # type: ignore[arg-type]
    client.app.state.ebay = browse(portal)  # type: ignore[arg-type,attr-defined]
    verdict = client.get("/resale/verdict", params={"q": "Pikachu 201/165"})

    assert prices.configured is True
    assert "page" in (prices.error or "")
    assert verdict.status_code == 200


def test_a_listing_sold_several_times_counts_each_sale(client: TestClient, tmp_path) -> None:  # type: ignore[no-untyped-def]
    class FakeRepeatedSales(FakeInsights):
        def __call__(self, request: httpx.Request) -> httpx.Response:
            if str(request.url).startswith(INSIGHTS_URL):
                lately = (date.today() - timedelta(days=3)).isoformat()
                sales = [
                    ebay_sale("1", "Pikachu 201/165 SAR", "40.00", lately)
                    | {"totalSoldQuantity": 4},
                    ebay_sale("2", "Pikachu 201/165 SAR", "44.00", lately),
                ]
                return httpx.Response(200, json={"total": 2, "itemSales": sales})
            return super().__call__(request)

    use_fake_ebay(client, FakeRepeatedSales(granted=True))
    client.app.state.browsers = Browsers(tmp_path, session_factory=NoChrome)  # type: ignore[attr-defined]
    client.put("/settings/ebay", json={"client_id": "A-PRD-1", "client_secret": "PRD-1"})
    body = {"query": "Pikachu 201/165", "card_number": "201/165", "names": ["Pikachu"]}

    sold = client.post("/browser/ebay/sold", json=body).json()

    assert sold["relevant_count"] == 2
    assert sold["sales_90_days"] == 5


def test_lots_and_slabs_never_count_even_without_the_number() -> None:
    from mekiki_engine.resale.service import ebay_prices

    prices = ebay_prices(browse(FakeEbaySearch()), "Pikachu")

    assert [listing.item_id for listing in prices.listings] == ["a", "b", "c"]


def test_asking_prices_inform_but_never_make_an_outlet(client: TestClient) -> None:
    client.app.state.ebay = browse(FakeEbaySearch())  # type: ignore[attr-defined]

    result = client.get("/resale/verdict", params={"q": "Pikachu 201/165"}).json()

    assert result["prices"]["ebay"]["median_cents"] == 4200
    assert result["outlets"] == []
    assert result["verdict"] == "unknown"
    assert any("des prix demandés, pas des ventes" in s["text"] for s in result["signals"])


def use_fake_ebay(client: TestClient, fake: object) -> None:
    client.app.state.http = PoliteClient(  # type: ignore[attr-defined]
        intervals_s={},
        default_interval_s=0,
        transport=httpx.MockTransport(fake),  # type: ignore[arg-type]
    )


def test_each_account_saves_its_own_ebay_keys(client: TestClient) -> None:
    fake = FakeEbay()
    use_fake_ebay(client, fake)
    assert client.get("/settings/ebay").json()["configured"] is False

    saved = client.put(
        "/settings/ebay", json={"client_id": "Antoine-Mekiki-PRD-1", "client_secret": "PRD-s3cret"}
    )
    prices = client.get("/resale/prices", params={"q": "Pikachu 201/165"}).json()

    assert saved.status_code == 200
    assert saved.json() == {
        "configured": True,
        "source": "account",
        "client_id": "Antoine-Mekiki-PRD-1",
        "marketplace": "EBAY_FR",
        "sold_api": True,
    }
    assert "s3cret" not in saved.text
    assert prices["ebay"]["configured"] is True
    # The keys checked, Marketplace Insights asked once, then the Browse API's token.
    assert fake.token_calls == 3

    sign_in(client, "autre@exemple.fr")
    assert client.get("/settings/ebay").json()["configured"] is False


def test_sandbox_or_refused_ebay_keys_are_not_saved(client: TestClient) -> None:
    sandbox = client.put(
        "/settings/ebay", json={"client_id": "Antoine-Mekiki-SBX-1", "client_secret": "SBX-1"}
    )
    use_fake_ebay(client, lambda _request: httpx.Response(401, json={"error": "invalid_client"}))
    refused = client.put(
        "/settings/ebay", json={"client_id": "Antoine-Mekiki-PRD-1", "client_secret": "faux"}
    )

    assert sandbox.status_code == 422
    assert "Sandbox" in sandbox.json()["detail"]
    assert refused.status_code == 422
    # eBay's reason, explained: wrong keys, or a Production keyset still disabled.
    assert "Marketplace Account Deletion" in refused.json()["detail"]
    assert client.get("/settings/ebay").json()["configured"] is False


def test_ebay_out_of_reach_is_not_blamed_on_the_keys(client: TestClient) -> None:
    use_fake_ebay(client, lambda _request: httpx.Response(503, text="maintenance"))

    refused = client.put(
        "/settings/ebay", json={"client_id": "Antoine-Mekiki-PRD-1", "client_secret": "PRD-1"}
    )

    assert refused.status_code == 422
    assert refused.json()["detail"].startswith("Clés non vérifiées : eBay ne répond pas")


def test_saved_ebay_keys_keep_their_secret_and_can_be_removed(client: TestClient) -> None:
    use_fake_ebay(client, FakeEbay())
    client.put("/settings/ebay", json={"client_id": "A-PRD-1", "client_secret": "PRD-1"})

    again = client.put("/settings/ebay", json={"client_id": "A-PRD-1"})
    removed = client.delete("/settings/ebay")

    assert again.status_code == 200
    assert removed.json()["configured"] is False


def ebay_sale(item_id: str, title: str, price: str, day: str) -> dict[str, object]:
    return {
        "itemId": item_id,
        "title": title,
        "lastSoldPrice": {"value": price, "currency": "EUR"},
        "lastSoldDate": f"{day}T14:02:00.000Z",
        "totalSoldQuantity": 1,
        "itemWebUrl": f"https://www.ebay.fr/itm/{item_id}",
        "image": {"imageUrl": f"https://i.ebayimg.com/{item_id}.jpg"},
    }


class FakeInsights(FakeEbay):
    """eBay granting Marketplace Insights, or refusing its scope to the keys."""

    def __init__(self, granted: bool) -> None:
        super().__init__()
        self.granted = granted
        self.scopes: list[str] = []
        self.sold_searches: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if str(request.url) == TOKEN_URL:
            scope = parse_qs(request.content.decode())["scope"][0]
            self.scopes.append(scope)
            if scope == INSIGHTS_SCOPE and not self.granted:
                return httpx.Response(400, json={"error": "invalid_scope"})
        if str(request.url).startswith(INSIGHTS_URL):
            self.sold_searches.append(request.url.params["q"])
            sales = [
                ebay_sale("1", "Pikachu 201/165 SAR japonaise", "40.00", "2026-10-02"),
                ebay_sale("2", "Pikachu 201/165 SAR Japanese NM", "44.00", "2026-10-06"),
                ebay_sale("3", "PSA 10 Pikachu 201/165", "250.00", "2026-09-20"),
                ebay_sale("usd", "Pikachu 201/165", "30.00", "2026-10-01")
                | {"lastSoldPrice": {"value": "30.00", "currency": "USD"}},
            ]
            return httpx.Response(200, json={"total": 4, "itemSales": sales})
        return super().__call__(request)


def test_sold_listings_need_the_marketplace_insights_scope() -> None:
    refused, granted = FakeInsights(granted=False), FakeInsights(granted=True)
    without = browse(refused)

    assert without.sold("Pikachu 201/165") is None
    assert without.sold("Pikachu 201/165") is None
    sales = browse(granted).sold("Pikachu 201/165")

    # eBay is asked once whether the keys may read sold listings.
    assert refused.scopes == [INSIGHTS_SCOPE]
    assert refused.sold_searches == []
    assert sales is not None
    assert [(sale.item_id, sale.price_cents, sale.sold_on) for sale in sales] == [
        ("1", 4000, "2026-10-02"),
        ("2", 4400, "2026-10-06"),
        ("3", 25000, "2026-09-20"),
    ]


class NoChrome:
    def __init__(self, _profile: object) -> None:
        raise AssertionError("Chrome must not open when eBay's API gives the sales")


def test_sales_come_from_the_api_without_chrome_when_ebay_allows_it(
    client: TestClient, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    fake = FakeInsights(granted=True)
    use_fake_ebay(client, fake)
    client.app.state.browsers = Browsers(tmp_path, session_factory=NoChrome)  # type: ignore[attr-defined]
    client.put("/settings/ebay", json={"client_id": "A-PRD-1", "client_secret": "PRD-1"})
    body = {"query": "Pikachu 201/165", "card_number": "201/165", "names": ["Pikachu"]}

    sold = client.post("/browser/ebay/sold", json=body).json()
    again = client.post("/browser/ebay/sold", json=body).json()

    assert sold["source"] == "api"
    assert sold["relevant_count"] == 2
    assert sold["median_cents"] == 4200
    assert sold["listings"][0]["detail"] == "Vendu le 6 oct. 2026"
    assert again == sold
    assert fake.sold_searches == ["Pikachu 201/165"]


def test_keys_without_the_api_still_read_sales_in_chrome(client: TestClient, tmp_path) -> None:  # type: ignore[no-untyped-def]
    use_fake_ebay(client, FakeInsights(granted=False))
    status = client.put("/settings/ebay", json={"client_id": "A-PRD-1", "client_secret": "PRD-1"})
    opened: list[object] = []

    def no_window(profile: object) -> object:
        opened.append(profile)
        raise AssertionError("Chrome opened")

    client.app.state.browsers = Browsers(tmp_path, session_factory=no_window)  # type: ignore[attr-defined]
    with pytest.raises(AssertionError):
        client.post("/browser/ebay/sold", json={"query": "Pikachu 201/165"})

    assert status.json()["sold_api"] is False
    assert len(opened) == 1
