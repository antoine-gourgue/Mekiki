"""Card names typed in French or English, turned into what Japanese listings write.

Japanese titles name Pokémon in katakana ("リザードンex") and One Piece characters in their
Japanese spelling ("ルフィ"); searching "Dracaufeu" or "Luffy" on Mercari finds almost
nothing. Pokémon names come from PokéAPI's species list, downloaded once a month; One Piece
has no such open list, so the main characters are spelled out below.
"""

from __future__ import annotations

import csv
import io
import json
import re
import threading
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from mekiki_engine.domain import Game
from mekiki_engine.models import PokemonSpecies, SettingRow
from mekiki_engine.scanner.sources.base import PoliteClient, SourceError

SPECIES_URL = (
    "https://raw.githubusercontent.com/PokeAPI/pokeapi/master/data/v2/csv/pokemon_species_names.csv"
)
STATE_KEY = "names:pokemon"
MAX_AGE = timedelta(days=30)
# PokéAPI language ids; 1 is Japanese in kana, the script listing titles use.
LANGUAGE_IDS = {"1": "ja", "9": "en", "5": "fr", "6": "de", "7": "es", "8": "it"}
LATIN_LANGUAGES = ("en", "fr", "de", "es", "it")

Target = Literal["ja", "en", "fr"]

# Written after the Pokémon's name on Japanese cards, without a space: "リザードンex".
SUFFIXES = {
    "ex": "ex",
    "gx": "GX",
    "v": "V",
    "vmax": "VMAX",
    "vstar": "VSTAR",
    "break": "BREAK",
}
MEGA_WORDS = {"mega", "mega-"}
# Regional forms: English puts the region first ("Alolan Vulpix"), French after
# ("Goupix d'Alola"), Japanese first and attached ("アローラロコン").
FRENCH_REGIONS = {
    "alola": "d'Alola",
    "galar": "de Galar",
    "hisui": "d'Hisui",
    "paldea": "de Paldea",
}
REGIONS = {
    "alola": ("アローラ", "Alolan"),
    "galar": ("ガラル", "Galarian"),
    "hisui": ("ヒスイ", "Hisuian"),
    "paldea": ("パルデア", "Paldean"),
}
REGION_ADJECTIVES = {
    "alolan": "alola",
    "galarian": "galar",
    "hisuian": "hisui",
    "paldean": "paldea",
}

# One Piece characters: (names people type, Japanese spelling in titles, Cardmarket word).
# The short Japanese forms match more titles: "ルフィ" is in "モンキー・D・ルフィ".
ONE_PIECE_CHARACTERS: tuple[tuple[tuple[str, ...], str, str], ...] = (
    (("luffy", "monkey d luffy"), "ルフィ", "Luffy"),
    (("zoro", "roronoa zoro"), "ゾロ", "Zoro"),
    (("nami",), "ナミ", "Nami"),
    (("usopp", "sogeking"), "ウソップ", "Usopp"),
    (("sanji", "vinsmoke sanji"), "サンジ", "Sanji"),
    (("chopper", "tony tony chopper"), "チョッパー", "Chopper"),
    (("robin", "nico robin"), "ロビン", "Robin"),
    (("franky",), "フランキー", "Franky"),
    (("brook",), "ブルック", "Brook"),
    (("jinbe", "jinbei", "jimbei"), "ジンベエ", "Jinbe"),
    (("shanks",), "シャンクス", "Shanks"),
    (("ace", "portgas d ace"), "エース", "Ace"),
    (("sabo",), "サボ", "Sabo"),
    (("law", "trafalgar law", "trafalgar d water law"), "ロー", "Law"),
    (("kid", "eustass kid", "eustass captain kid"), "キッド", "Kid"),
    (("killer",), "キラー", "Killer"),
    (("yamato",), "ヤマト", "Yamato"),
    (("uta",), "ウタ", "Uta"),
    (("vivi", "nefertari vivi", "nefeltari vivi"), "ビビ", "Vivi"),
    (("hancock", "boa hancock"), "ハンコック", "Hancock"),
    (("kaido", "kaidou"), "カイドウ", "Kaido"),
    (("big mom", "charlotte linlin", "linlin"), "リンリン", "Linlin"),
    (("katakuri", "charlotte katakuri"), "カタクリ", "Katakuri"),
    (("whitebeard", "barbe blanche", "edward newgate", "newgate"), "ニューゲート", "Newgate"),
    (("blackbeard", "barbe noire", "marshall d teach", "teach"), "ティーチ", "Teach"),
    (("mihawk", "dracule mihawk"), "ミホーク", "Mihawk"),
    (("crocodile",), "クロコダイル", "Crocodile"),
    (("doflamingo", "donquixote doflamingo"), "ドフラミンゴ", "Doflamingo"),
    (("buggy",), "バギー", "Buggy"),
    (("smoker",), "スモーカー", "Smoker"),
    (("koby", "coby"), "コビー", "Koby"),
    (("garp", "monkey d garp"), "ガープ", "Garp"),
    (("sengoku",), "センゴク", "Sengoku"),
    (("akainu", "sakazuki"), "サカズキ", "Sakazuki"),
    (("kizaru", "borsalino"), "ボルサリーノ", "Borsalino"),
    (("aokiji", "kuzan"), "クザン", "Kuzan"),
    (("fujitora", "issho"), "イッショウ", "Issho"),
    (("ryokugyu", "aramaki"), "アラマキ", "Aramaki"),
    (("roger", "gol d roger", "gold roger"), "ロジャー", "Roger"),
    (("rayleigh", "silvers rayleigh"), "レイリー", "Rayleigh"),
    (("marco",), "マルコ", "Marco"),
    (("carrot",), "キャロット", "Carrot"),
    (("perona",), "ペローナ", "Perona"),
    (("reiju", "vinsmoke reiju"), "レイジュ", "Reiju"),
    (("oden", "kozuki oden", "kouzuki oden"), "おでん", "Oden"),
    (("hiyori", "kozuki hiyori", "kouzuki hiyori"), "日和", "Hiyori"),
    (("kinemon", "kin'emon"), "錦えもん", "Kin'emon"),
    (("momonosuke", "kozuki momonosuke"), "モモの助", "Momonosuke"),
    (("bonney", "jewelry bonney"), "ボニー", "Bonney"),
    (("hawkins", "basil hawkins"), "ホーキンス", "Hawkins"),
    (("bartolomeo",), "バルトロメオ", "Bartolomeo"),
    (("cavendish",), "キャベンディッシュ", "Cavendish"),
    (("rebecca",), "レベッカ", "Rebecca"),
    (("moria", "gecko moria"), "モリア", "Moria"),
    (("ivankov", "emporio ivankov"), "イワンコフ", "Ivankov"),
    (("dragon", "monkey d dragon"), "ドラゴン", "Dragon"),
    (("imu",), "イム", "Imu"),
    (("vegapunk",), "ベガパンク", "Vegapunk"),
    (("kuma", "bartholomew kuma"), "くま", "Kuma"),
    (("lucci", "rob lucci"), "ルッチ", "Lucci"),
    (("enel", "eneru"), "エネル", "Enel"),
    (("arlong",), "アーロン", "Arlong"),
    (("tashigi",), "たしぎ", "Tashigi"),
    (("shirahoshi",), "しらほし", "Shirahoshi"),
    (("sugar",), "シュガー", "Sugar"),
)

# Phones type apostrophes as U+2019 ("right single quotation mark").
_CURLY_APOSTROPHE = chr(0x2019)
_SEPARATORS = re.compile(r"[.\-_/·,]+")
_SPACES = re.compile(r"\s+")
_JAPANESE = re.compile(r"[぀-ヿ㐀-鿿]")


@dataclass(frozen=True, slots=True)
class Name:
    ja: str
    en: str
    fr: str | None = None


class NameBook:
    """Names in Latin letters → their Japanese and English spellings, for one game."""

    def __init__(self, entries: Iterable[tuple[str, Name]]) -> None:
        self.names: dict[tuple[str, ...], Name] = {}
        for typed, name in entries:
            words = tuple(key(typed).split())
            if words:
                self.names.setdefault(words, name)
        self.longest = max((len(words) for words in self.names), default=0)

    def translate(self, text: str, target: Target) -> str | None:
        """``text`` with every known name replaced, or None when no name was found."""
        if _JAPANESE.search(text):
            return None
        originals = text.split()
        words = [key(word) for word in originals]
        out: list[str] = []
        found = False
        index = 0
        while index < len(words):
            prefix_region = REGION_ADJECTIVES.get(words[index])
            mega = words[index] in MEGA_WORDS
            start = index + (1 if prefix_region or mega else 0)
            match = self._match(words, start)
            if match is None:
                out.append(originals[index])
                index += 1
                continue
            name, used = match
            index = start + used
            region = prefix_region
            # French puts the region after the name: "goupix d'alola", "miaouss de galar".
            if index < len(words) and words[index].startswith("d'") and words[index][2:] in REGIONS:
                region, index = words[index][2:], index + 1
            elif index + 1 < len(words) and words[index] == "de" and words[index + 1] in REGIONS:
                region, index = words[index + 1], index + 2
            suffix = ""
            if index < len(words) and words[index] in SUFFIXES:
                suffix, index = SUFFIXES[words[index]], index + 1
            out.append(_spell(name, target, mega=mega, region=region, suffix=suffix))
            found = True
        return " ".join(out) if found else None

    def _match(self, words: list[str], start: int) -> tuple[Name, int] | None:
        for size in range(min(self.longest, len(words) - start), 0, -1):
            name = self.names.get(tuple(words[start : start + size]))
            if name is not None:
                return name, size
        return None


def _spell(name: Name, target: Target, *, mega: bool, region: str | None, suffix: str) -> str:
    if target == "ja":
        head = ("メガ" if mega else "") + (REGIONS[region][0] if region else "")
        return f"{head}{name.ja}{suffix}"
    if target == "fr":
        words = [("Méga-" if mega else "") + (name.fr or name.en)]
        words += [FRENCH_REGIONS[region]] if region else []
        return " ".join(words) + (f" {suffix}" if suffix else "")
    words = [*(["Mega"] if mega else []), *([REGIONS[region][1]] if region else []), name.en]
    return " ".join(words) + (f" {suffix}" if suffix else "")


def key(text: str) -> str:
    """Lowercase, without accents nor punctuation: "M. Mime" → "m mime"."""
    text = unicodedata.normalize("NFKC", text).lower().replace(_CURLY_APOSTROPHE, "'")
    stripped = "".join(
        char
        for char in unicodedata.normalize("NFD", text)
        if not (unicodedata.combining(char) and char < "　")
    )
    return _SPACES.sub(" ", _SEPARATORS.sub(" ", stripped)).strip()


_books: dict[Game, tuple[str, NameBook]] = {}
_books_lock = threading.Lock()


def name_book(session: Session, game: Game) -> NameBook:
    """The game's book, rebuilt only when the downloaded names changed."""
    version = _version(session) if game is Game.POKEMON else "static"
    with _books_lock:
        cached = _books.get(game)
        if cached and cached[0] == version:
            return cached[1]
    if game is Game.ONE_PIECE:
        book = NameBook(
            (typed, Name(ja=ja, en=en))
            for aliases, ja, en in ONE_PIECE_CHARACTERS
            for typed in aliases
        )
    else:
        book = NameBook(_species_entries(session))
    with _books_lock:
        _books[game] = (version, book)
    return book


def translate(session: Session, game: Game, text: str, target: Target) -> str | None:
    return name_book(session, game).translate(text, target)


def _species_entries(session: Session) -> Iterable[tuple[str, Name]]:
    for species in session.scalars(select(PokemonSpecies)):
        if not species.ja or not species.en:
            continue
        name = Name(ja=unicodedata.normalize("NFKC", species.ja), en=species.en, fr=species.fr)
        for language in LATIN_LANGUAGES:
            typed = getattr(species, language)
            if typed:
                yield typed, name


def refresh(session: Session, client: PoliteClient, *, force: bool = False) -> str | None:
    """Downloads the Pokémon names once a month; returns an error message, if any."""
    state = _load_state(session)
    fetched_at = state.get("fetched_at")
    if not force and fetched_at and _age(fetched_at) < MAX_AGE and species_count(session):
        return None
    try:
        text = client.request("GET", SPECIES_URL, timeout=60).text
        rows = parse_species(text)
        if not rows:
            raise SourceError("liste vide")
        session.execute(delete(PokemonSpecies))
        session.add_all(
            PokemonSpecies(id=species_id, **names) for species_id, names in rows.items()
        )
        state = {"fetched_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), "error": None}
    except SourceError as error:
        session.rollback()
        state["error"] = f"Noms des Pokémon (PokéAPI) : {error}"
    _save_state(session, state)
    return state["error"]


def parse_species(text: str) -> dict[int, dict[str, str]]:
    rows: dict[int, dict[str, str]] = {}
    for row in csv.DictReader(io.StringIO(text)):
        language = LANGUAGE_IDS.get(row.get("local_language_id", ""))
        if language and row.get("name") and row.get("pokemon_species_id", "").isdigit():
            rows.setdefault(int(row["pokemon_species_id"]), {})[language] = row["name"]
    return rows


def species_count(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(PokemonSpecies)) or 0


def _version(session: Session) -> str:
    return str(_load_state(session).get("fetched_at")) + f":{species_count(session)}"


def _load_state(session: Session) -> dict[str, str | None]:
    row = session.get(SettingRow, STATE_KEY)
    return json.loads(row.value) if row else {}


def _save_state(session: Session, state: dict[str, str | None]) -> None:
    row = session.get(SettingRow, STATE_KEY)
    if row is None:
        session.add(SettingRow(key=STATE_KEY, value=json.dumps(state)))
    else:
        row.value = json.dumps(state)
    session.commit()


def _age(timestamp: str) -> timedelta:
    fetched = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    return datetime.now(UTC) - fetched
