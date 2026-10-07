# Mekiki

Application desktop d'achat-revente de cartes TCG (Pokémon, One Piece) achetées au Japon via
Neokyo et revendues en Europe. `engine/` est le moteur Python (FastAPI + SQLite) ;
`desktop/` est l'interface Nuxt 4 + Nuxt UI 4 empaquetée avec Tauri 2, qui lance le moteur
comme sidecar en release seulement.

## Conventions

- Commentaires du code **en anglais**, seulement pour expliquer un *pourquoi*. Textes de
  l'interface **en français**.
- Pas de bannières décoratives. Docstrings/JSDoc là où elles apportent quelque chose
  (composables, contrat d'API, props partagées).
- Commits conventionnels, en anglais, sujet en minuscules, **sans ligne `Co-Authored-By`**.
  Un commit par étape logique.
- **Argent en entiers** : centimes d'euro (`*_cents`) et yens (`*_jpy`). `Decimal` seulement
  pour les calculs intermédiaires, arrondi une fois par composante (`ROUND_HALF_UP`).
  Les taux transitent en nombres : `*_percent` en pourcentage (12.3), `roi` en fraction.
- Repo public : ne jamais committer de base SQLite (`.data/`, `*.sqlite3*`).
- Ne pas copier de code de GoupixDex (pas de licence).

## Vérifications avant chaque push

```bash
cd engine && uv run ruff check && uv run ruff format --check && uv run pytest
cd desktop && npm run lint && npm run format:check && npm run typecheck && npm run generate
```

## Règles métier

- Le cas de référence (colis de 10 cartes à 8 000 ¥ → 62,67 € de coût de revient, vente à
  90 € sur Cardmarket → net 73,93 €, ROI 17,97 %) est verrouillé par
  `engine/tests/test_landed_cost.py`, `test_sale.py` et `test_api.py`. Il doit toujours passer.
- Le coût de revient n'est jamais stocké : il est recalculé à chaque lecture, pour qu'une
  facture de TVA saisie après une vente corrige sa marge. Les frais de plateforme,
  l'emballage et le taux de cotisation sont en revanche figés au moment de la vente.
- Le schéma SQLite évolue par migrations avant seulement (`engine/mekiki_engine/migrations/`,
  `mNNNN_*.py`), jamais en modifiant une migration existante.
- `desktop/app/types/engine.ts` reflète `engine/mekiki_engine/schemas.py` : les modifier
  ensemble.

## Pièges connus (Windows, octobre 2026)

- Smart App Control bloque les binaires récents sans réputation : le Python géré par uv,
  les extensions Cython de SQLAlchemy 2.1, le lanceur `.venv/Scripts/mekiki-engine.exe`.
  D'où le Python officiel signé (python.org), SQLAlchemy limité à `<2.1` (qui retombe en
  Python pur), et `uv run python -m mekiki_engine` plutôt que `uv run mekiki-engine`.
- Nuxt est bloqué en `~4.5.2` : en 4.6.0, `nuxt generate` échoue au prérendu sous Windows
  (le renderer est externalisé et ses imports virtuels ne sont pas résolus).
- TypeScript reste en 6.x : `vue-tsc` dépend de l'API JavaScript de TypeScript, absente de
  TypeScript 7.
- Dans Tauri, un lien `target="_blank"` n'ouvre rien : passer par `openExternal()`
  (`desktop/app/utils/external.ts`).
