# Mekiki

> 目利き : « avoir l'œil », savoir juger la vraie valeur d'un objet.

Application desktop perso pour l'achat-revente de cartes TCG **Pokémon** et **One Piece** :
achat au Japon via le proxy Neokyo (Mercari, Rakuma, Yahoo Auctions, Yahoo Fleamarket), revente
en Europe sur Cardmarket, eBay, Vinted et Leboncoin.

Pour l'instant : le stock et la **rentabilité réelle**. Coût de revient complet par carte (prix,
frais Neokyo, envoi, TVA à l'import, douane, frais de dossier), net de vente par plateforme
(commission, envoi, emballage, cotisations URSSAF), marge et ROI. Plus tard : un scanner de
bonnes affaires et la détection de la hype.

## Architecture

| Dossier | Rôle |
|---|---|
| `engine/` | Moteur local en Python ≥ 3.12 (uv) : FastAPI + SQLite sur `127.0.0.1:18421` |
| `desktop/` | Interface Nuxt 4 + Nuxt UI 4 en SPA, empaquetée avec Tauri 2 |

En release, le moteur est compilé avec PyInstaller et lancé par Tauri comme sidecar ; sa base
SQLite est stockée dans le dossier de données de l'app. En développement, on le lance à part.

## Développement

Prérequis : [uv](https://docs.astral.sh/uv/), Node.js 24, et pour Tauri
[Rust et les dépendances système](https://tauri.app/start/prerequisites/).

```bash
# Terminal 1 : le moteur (données dans engine/.data)
cd engine
uv sync
uv run python -m mekiki_engine

# Terminal 2 : l'interface dans le navigateur (http://localhost:3000)…
cd desktop
npm install
npm run dev

# … ou dans la fenêtre Tauri
npm run tauri:dev
```

## Build de l'application

```bash
cd engine
uv sync --group bundle
uv run python scripts/build_sidecar.py   # → desktop/src-tauri/binaries/

cd ../desktop
npm run tauri:build
```

## Vérifications avant chaque push

```bash
cd engine && uv run ruff check && uv run ruff format --check && uv run pytest
cd desktop && npm run lint && npm run format:check && npm run typecheck && npm run generate
```

La CI GitHub Actions lance les mêmes commandes.

## Données

La base SQLite contient le stock et les ventes : elle ne doit jamais être commitée
(`.data/` et `*.sqlite3*` sont dans le `.gitignore`).
