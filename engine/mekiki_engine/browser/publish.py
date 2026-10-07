"""Publishing a card on Vinted or eBay by filling their listing forms in Mekiki's Chrome.

The steps follow the forms as they were on 8 October 2026. When a step fails, the form
stays open in Chrome, filled as far as it got, for the user to finish by hand.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path

from mekiki_engine.browser.chrome import ChromeError, Tab
from mekiki_engine.domain import Game

VINTED_NEW = "https://www.vinted.fr/items/new"
EBAY_NEW = "https://www.ebay.fr/sl/prelist/suggest"
# Vinted's catalog path to single cards, and its brand ids.
VINTED_CATEGORY_PATH = (
    "Loisirs et collections",
    "Cartes à collectionner",
    "Cartes à collectionner à l'unité",
)
VINTED_BRANDS = {Game.POKEMON: 191646, Game.ONE_PIECE: 89766}
VINTED_BRAND_NAMES = {Game.POKEMON: "Pokémon", Game.ONE_PIECE: "OnePiece"}
# Vinted conditions: 1 new without tag, 2 very good, 3 good, 4 satisfactory.
VINTED_CONDITIONS = {"mint": 1, "excellent": 2, "good": 3, "played": 4}
EBAY_CONDITIONS = {
    "mint": "Near Mint or Better (Quasi neuf ou mieux)",
    "excellent": "Lightly Played/Excellent (légers défauts)",
    "good": "Moderately Played/Very Good (état moyen)",
    "played": "Heavily Played/Poor (très abîmée)",
}
EBAY_GAMES = {Game.POKEMON: "Pokémon", Game.ONE_PIECE: "One Piece"}
STEP_TIMEOUT_S = 20


@dataclass(frozen=True, slots=True)
class Listing:
    game: Game
    title: str
    description: str
    price_cents: int
    photos: list[Path]
    condition: str | None
    grading: str | None


def condition_grade(condition: str | None) -> str:
    """The card's condition as one of four grades, near mint unless told otherwise."""
    text = (condition or "").lower()
    if re.search(r"\b(hp|heavily|poor|abîm|abim|damaged)", text):
        return "played"
    if re.search(r"\b(mp|moderately|good|bon état|bon etat|very good)\b", text) and not re.search(
        r"très bon|tres bon", text
    ):
        return "good"
    if re.search(r"\b(lp|lightly|excellent|ex|très bon|tres bon)\b", text):
        return "excellent"
    return "mint"


def euros(cents: int) -> str:
    """ "12,50": how both sites take a price."""
    return f"{cents / 100:.2f}".replace(".", ",")


def publish_vinted(tab: Tab, listing: Listing, *, submit: bool = True) -> str:
    """Fills Vinted's form and adds the item; returns the item's page.

    Without ``submit`` the form is only filled, e.g. to check these steps still work.
    """
    _step(tab.navigate, VINTED_NEW, step="ouverture du formulaire Vinted")
    if "/member/" in tab.url() or "signup" in tab.url():
        raise ChromeError("connectez-vous à Vinted dans la fenêtre Chrome de Mekiki")
    tab.wait_for(
        "!!document.querySelector('[data-testid=\"add-photos-input\"]')", timeout=STEP_TIMEOUT_S
    )

    if listing.photos:
        tab.set_files('[data-testid="add-photos-input"]', listing.photos)
    tab.type_text("#title", listing.title)
    tab.type_text("#description", listing.description)

    tab.click('[data-testid="catalog-select-dropdown-input"]')
    for name in VINTED_CATEGORY_PATH:
        _pause()
        tab.click_text(name, within='[data-testid="catalog-select-dropdown-content"]')
    tab.wait_for("!!document.querySelector('#brand')", timeout=STEP_TIMEOUT_S)

    # Vinted may already guess the brand from the title.
    if tab.evaluate("document.querySelector('#brand')?.value") != VINTED_BRAND_NAMES[listing.game]:
        _pick(tab, "#brand", f"#brand-radio-{VINTED_BRANDS[listing.game]}")
    grade = VINTED_CONDITIONS[condition_grade(listing.condition)]
    _pick(tab, "#condition", f"#condition-radio-{grade}")
    tab.type_text("#price", euros(listing.price_cents))
    # The smallest parcel: a card travels in a padded envelope.
    tab.click("#package_type_selector_1")
    # Each uploaded photo shows in an "image-wrapper-<n>" box once Vinted has it.
    _wait_uploads(tab, len(listing.photos), "[data-testid^='image-wrapper-'] img")

    if not submit:
        return tab.url()
    tab.click('[data-testid="upload-form-save-button"]')
    item_url = _wait_url(tab, r"vinted\.fr/items/\d+", step="enregistrement de l'annonce Vinted")
    return item_url.split("?")[0]


def publish_ebay(tab: Tab, listing: Listing, *, submit: bool = True) -> str:
    """Goes through eBay's listing steps and lists the card; returns the confirmation page.

    Without ``submit`` the form is only filled (eBay keeps it as a draft).
    """
    if listing.grading:
        raise ChromeError(
            "les cartes gradées se publient encore à la main sur eBay (organisme et note)"
        )
    _step(tab.navigate, EBAY_NEW, step="ouverture de la mise en vente eBay")
    if "signin" in tab.url():
        raise ChromeError("connectez-vous à eBay dans la fenêtre Chrome de Mekiki")
    search = 'input[placeholder="Dites-nous ce que vous vendez"]'
    tab.wait_for(f"!!document.querySelector('{search}')", timeout=STEP_TIMEOUT_S)
    tab.type_text(search, listing.title)
    tab.click('button[aria-label="Rechercher"]')

    # eBay only offers catalog products when it finds some; otherwise it asks the condition.
    _wait_text(
        tab, ("Continuer sans objet correspondant", "Non gradée"), step="choix du produit eBay"
    )
    if _shows_text(tab, "Continuer sans objet correspondant"):
        tab.click_text("Continuer sans objet correspondant")
    _wait_text(tab, "Non gradée", step="choix de l'état eBay")
    condition = EBAY_CONDITIONS[condition_grade(listing.condition)]
    _choose_and_continue(tab, "Non gradée", until=condition, step="choix de l'état eBay")
    _choose_and_continue(
        tab, condition, until=None, step="état de la carte eBay", url_part="/lstng"
    )

    tab.wait_for("!!document.querySelector('input[name=\"title\"]')", timeout=40)
    if listing.photos:
        tab.set_files("#fehelix-uploader", listing.photos)
    tab.type_text('input[name="title"]', listing.title)
    _choose_ebay_game(tab, listing.game)

    # The description editor is a frame; its HTML mode is a plain text area.
    tab.evaluate(
        "(() => { const box = document.querySelector('input[name=\"descriptionEditorMode\"]');"
        " if (box && !box.checked) box.click(); })()"
    )
    _pause()
    tab.type_text('textarea[name="description"]', _html(listing.description))
    tab.type_text('input[name="price"]', euros(listing.price_cents))
    # An uploaded photo becomes a thumbnail button whose background comes from ebayimg.
    _wait_uploads(
        tab, len(listing.photos), "[id^='uploader-thumbnails-ux__image'][style*='ebayimg']"
    )

    button = "button[aria-label^='Mettre en vente']"
    tab.wait_for(f'!!document.querySelector("{button}")', timeout=STEP_TIMEOUT_S)
    if not submit:
        return tab.url()
    tab.click(button)
    return _wait_url(
        tab,
        r"ebay\.fr/(sl/success|lstng/success|itm/\d+)|success",
        step="mise en vente eBay",
        errors="[role=alert], .page-notice--attention, .field__error",
    )


def _choose_and_continue(
    tab: Tab, choice: str, *, until: str | None, step: str, url_part: str | None = None
) -> None:
    """Picks an answer on one of eBay's question pages, then "Continuer" until the next
    page shows (``until`` text, or ``url_part`` in the address): the first click on
    "Continuer" can come before eBay has registered the choice."""
    for _attempt in range(3):
        tab.click_text(choice)
        _pause()
        tab.click_text("Continuer")
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if (until and _shows_text(tab, until)) or (url_part and url_part in tab.url()):
                return
            time.sleep(0.5)
    raise ChromeError(f"{step} : eBay n'est pas passé à l'étape suivante")


def _choose_ebay_game(tab: Tab, game: Game) -> None:
    """ "Jeu" is required: eBay suggests values under the field, else its list has them."""
    keyword = EBAY_GAMES[game]
    picked = tab.evaluate(
        f"""(() => {{
            const field = document.querySelector('button[name="attributes.Jeu"]');
            if (!field) return 'absent';
            if (field.innerText.trim() && field.innerText.trim() !== 'Jeu') return 'set';
            const chips = [...document.querySelectorAll('button')]
                .filter((b) => b.offsetParent && b.innerText.trim().startsWith({keyword!r}));
            if (chips.length) {{ chips[0].click(); return 'chip'; }}
            return 'list';
        }})()"""
    )
    if picked != "list":
        return
    tab.click('button[name="attributes.Jeu"]')
    _pause()
    tab.evaluate(
        f"""(() => {{
            const option = [...document.querySelectorAll('[role=option], li, button')]
                .find((o) => o.offsetParent && o.innerText.trim().startsWith({keyword!r}));
            if (option) option.click();
        }})()"""
    )


def _html(text: str) -> str:
    """Plain text as eBay's HTML description: one paragraph per block, line breaks kept."""
    escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    blocks = [block.replace("\n", "<br>") for block in escaped.split("\n\n") if block.strip()]
    return "".join(f"<p>{block}</p>" for block in blocks)


def _pick(tab: Tab, opener: str, option: str) -> None:
    """Opens a drop-down list and clicks one of its options once it shows.

    Right after another list closes, the first click on the next one can be swallowed:
    it is tried a few times.
    """
    visible = (
        f"(() => {{ const e = document.querySelector({option!r}); "
        "return !!e && (!!e.offsetParent || !!e.closest('label')?.offsetParent); })()"
    )
    for _attempt in range(3):
        if tab.evaluate(visible):
            break
        tab.click(opener)
        try:
            tab.wait_for(visible, timeout=4)
            break
        except ChromeError:
            continue
    else:
        raise ChromeError(f"choix introuvable dans la liste ({option})")
    tab.click(option)
    _pause()


def _wait_uploads(tab: Tab, count: int, selector: str) -> None:
    """Gives the photos time to upload before the form is sent."""
    if not count:
        return
    try:
        tab.wait_for(f'document.querySelectorAll("{selector}").length >= {count}', timeout=60)
    except ChromeError:
        # Some thumbnails render late; the site refuses the form itself if photos are missing.
        time.sleep(3)


def _shows_text(tab: Tab, *texts: str) -> bool:
    """Whether a visible button, label or list item starts with one of ``texts``."""
    return bool(
        tab.evaluate(
            "[...document.querySelectorAll('button, span, li, label')]"
            f".some((e) => e.offsetParent && {list(texts)!r}"
            ".some((t) => e.innerText.trim().startsWith(t)))"
        )
    )


def _wait_text(tab: Tab, texts: str | tuple[str, ...], *, step: str) -> None:
    wanted = (texts,) if isinstance(texts, str) else texts
    deadline = time.monotonic() + STEP_TIMEOUT_S
    while not _shows_text(tab, *wanted):
        if time.monotonic() > deadline:
            raise ChromeError(f"{step} : la page n'a pas affiché « {wanted[0]} »")
        time.sleep(0.5)


def _wait_url(tab: Tab, pattern: str, *, step: str, errors: str | None = None) -> str:
    """Waits for the page reached after sending a form; reports the form's errors otherwise."""
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        url = tab.url()
        if re.search(pattern, url) and "/items/new" not in url:
            return url
        time.sleep(1)
    messages = []
    if errors:
        messages = (
            tab.evaluate(
                f"[...document.querySelectorAll({errors!r})].filter((e) => e.offsetParent)"
                ".map((e) => e.innerText.trim()).filter(Boolean).slice(0, 3)"
            )
            or []
        )
    else:
        messages = (
            tab.evaluate(
                '[...document.querySelectorAll(\'[class*="error"], [data-testid*="error"]\')]'
                ".filter((e) => e.offsetParent).map((e) => e.innerText.trim()).filter(Boolean)"
                ".slice(0, 3)"
            )
            or []
        )
    detail = f" ({' ; '.join(messages)})" if messages else ""
    raise ChromeError(f"{step} : le site n'a pas confirmé la publication{detail}")


def _step(action, *args, step: str):  # type: ignore[no-untyped-def]
    try:
        return action(*args)
    except ChromeError as error:
        raise ChromeError(f"{step} : {error}") from error


def _pause() -> None:
    # Menus open with an animation; a click before it ends lands on nothing.
    time.sleep(0.8)
