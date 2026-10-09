"""Japanese listing descriptions in French.

DeepL translates best: each account may save its own key (a free DeepL API account), checked
before it is kept. Without one, MyMemory's free API translates a few descriptions a day (about
5 000 characters, 500 bytes per request). A text is never sent twice: translations are kept
while the engine runs.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from dataclasses import dataclass
from typing import Literal

from mekiki_engine.scanner.sources.base import PoliteClient, SourceError

DEEPL_FREE_URL = "https://api-free.deepl.com/v2"
DEEPL_PRO_URL = "https://api.deepl.com/v2"
MYMEMORY_URL = "https://api.mymemory.translated.net/get"
# MyMemory takes 500 bytes per request; Japanese takes three per character.
MYMEMORY_MAX_BYTES = 480
# Longer descriptions are cut: the start says what matters, and the free quotas are small.
MAX_CHARACTERS = 2000
CACHE_SIZE = 300
# Where a sentence ends: "。", "!", "?" and their full-width forms.
SENTENCE_ENDS = "。!?" + chr(0xFF01) + chr(0xFF1F)

Provider = Literal["deepl", "mymemory"]


class TranslationError(SourceError):
    """The translation could not be made; the message says why, in French."""


@dataclass(frozen=True, slots=True)
class Translation:
    text: str
    provider: Provider


_cache: OrderedDict[tuple[str, str], Translation] = OrderedDict()
_cache_lock = threading.Lock()


def translate(client: PoliteClient, text: str, *, deepl_key: str | None = None) -> Translation:
    text = text.strip()[:MAX_CHARACTERS]
    provider: Provider = "deepl" if deepl_key else "mymemory"
    key = (provider, text)
    with _cache_lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
    if not text:
        return Translation("", provider)
    translated = _deepl(client, deepl_key, text) if deepl_key else _mymemory(client, text)
    result = Translation(translated, provider)
    with _cache_lock:
        _cache[key] = result
        while len(_cache) > CACHE_SIZE:
            _cache.popitem(last=False)
    return result


def check_deepl_key(client: PoliteClient, key: str) -> None:
    """Asks DeepL for the key's usage: raises ``TranslationError`` when it refuses the key."""
    response = client.request(
        "GET", f"{_deepl_url(key)}/usage", headers=_deepl_headers(key), accept=(401, 403)
    )
    if response.status_code in (401, 403):
        raise TranslationError("DeepL refuse cette clé : copiez-la depuis votre compte DeepL API")


def _deepl(client: PoliteClient, key: str, text: str) -> str:
    response = client.request(
        "POST",
        f"{_deepl_url(key)}/translate",
        headers=_deepl_headers(key),
        json={"text": [text], "source_lang": "JA", "target_lang": "FR"},
        accept=(401, 403, 456),
    )
    if response.status_code == 456:
        raise TranslationError("quota DeepL du mois atteint")
    if response.status_code in (401, 403):
        raise TranslationError("DeepL refuse la clé enregistrée dans Paramètres")
    translations = response.json().get("translations") or []
    if not translations:
        raise TranslationError("DeepL n'a rien renvoyé")
    return str(translations[0].get("text") or "")


def _deepl_url(key: str) -> str:
    # Keys of the free plan end with ":fx" and have their own address.
    return DEEPL_FREE_URL if key.endswith(":fx") else DEEPL_PRO_URL


def _deepl_headers(key: str) -> dict[str, str]:
    return {"Authorization": f"DeepL-Auth-Key {key}"}


def _mymemory(client: PoliteClient, text: str) -> str:
    parts = []
    for chunk in chunks(text, MYMEMORY_MAX_BYTES):
        response = client.request(
            "GET", MYMEMORY_URL, params={"q": chunk, "langpair": "ja|fr"}, accept=(429,)
        )
        data = response.json() if response.status_code != 429 else {}
        if response.status_code == 429 or data.get("quotaFinished"):
            raise TranslationError(
                "traductions gratuites du jour épuisées : ajoutez une clé DeepL dans Paramètres"
            )
        if int(data.get("responseStatus") or 200) != 200:
            raise TranslationError(str(data.get("responseDetails") or "MyMemory a refusé"))
        parts.append(str((data.get("responseData") or {}).get("translatedText") or ""))
    return "\n".join(parts)


def chunks(text: str, max_bytes: int) -> list[str]:
    """``text`` in pieces of at most ``max_bytes`` in UTF-8, cut between lines or sentences."""
    pieces: list[str] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        while len(line.encode()) > max_bytes:
            cut = _cut(line, max_bytes)
            pieces.append(line[:cut])
            line = line[cut:]
        pieces.append(line)
    grouped: list[str] = []
    for piece in pieces:
        if grouped and len(f"{grouped[-1]}\n{piece}".encode()) <= max_bytes:
            grouped[-1] = f"{grouped[-1]}\n{piece}"
        else:
            grouped.append(piece)
    return grouped


def _cut(line: str, max_bytes: int) -> int:
    """Where to cut a line too long: after the last sentence end that fits, else at the limit."""
    size = 0
    last_end = 0
    for index, char in enumerate(line):
        size += len(char.encode())
        if size > max_bytes:
            return last_end or index
        if char in SENTENCE_ENDS:
            last_end = index + 1
    return len(line)
