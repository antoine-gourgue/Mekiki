# Mekiki

> 目利き : « avoir l'œil », savoir juger la vraie valeur d'un objet.

Application desktop d'achat-revente de cartes TCG **Pokémon** et **One Piece** : achat au
Japon via le proxy Neokyo (Mercari, Rakuma, Yahoo Auctions, Yahoo Fleamarket), revente en
Europe sur Cardmarket, eBay, Vinted et Leboncoin. Chaque revendeur a son compte.

**[Télécharger Mekiki pour Windows](https://github.com/antoine-gourgue/Mekiki/releases/latest/download/Mekiki-Setup.exe)**
(installateur, mises à jour proposées dans l'app).

- **Stock et rentabilité réelle** : coût de revient complet par carte (prix, frais Neokyo,
  envoi, TVA à l'import, douane, frais de dossier), net de vente par plateforme (commission,
  envoi, emballage, cotisations URSSAF), marge et ROI. Photos de chaque carte.
- **Trouver des cartes** : on choisit le jeu, le budget du colis, le nombre de cartes et la
  profondeur de recherche ; l'app parcourt des milliers d'annonces Mercari et Rakuma, reconnaît
  chaque carte dans son titre japonais, la compare à sa cote Cardmarket et compose le colis le
  plus rentable, avec le lien Neokyo de chaque annonce. Favoris et panier pour préparer un colis.
- **Recherche et cartes suivies** : un nom tapé en français ou en anglais (« Dracaufeu ex »,
  « Luffy ») est cherché en japonais. Une carte suivie ne garde que les annonces de son
  impression exacte (extension, numéro, miroir, version parallèle ou manga) ; le scanner les
  cherche de plusieurs façons, sur plusieurs pages.
- **Faut-il l'acheter ?** : Ctrl+K cherche partout (pages, stock, colis, favoris, catalogue
  Cardmarket) ; chaque carte s'ouvre dans un panneau latéral avec un verdict, la revente sur
  Cardmarket, eBay et Vinted, le prix maximum à payer au Japon et des signaux d'alerte.
- **Vinted et eBay** : dans une fenêtre Chrome propre à Mekiki où l'utilisateur se connecte
  lui-même, l'app lit les annonces Vinted et les ventes réussies eBay d'une carte. Une annonce
  peut être préparée (titre, description, prix, photos) pour eBay et Vinted.

## Architecture

| Dossier | Rôle |
|---|---|
| `engine/` | Moteur en Python ≥ 3.12 (uv) : FastAPI + SQLite, comptes et données par revendeur |
| `desktop/` | Interface Nuxt 4 + Nuxt UI 4 en SPA, empaquetée avec Tauri 2 |

En release, le moteur est compilé avec PyInstaller et lancé par Tauri comme sidecar ; sa base
SQLite est stockée dans le dossier de données de l'app. En développement, on le lance à part.

Le moteur peut aussi tourner sur un serveur pour plusieurs revendeurs : `MEKIKI_HOST=0.0.0.0`,
`MEKIKI_ALLOWED_HOSTS` (noms de domaine acceptés) et `MEKIKI_ALLOWED_ORIGINS` (origines de
l'interface). Les secrets se mettent dans `engine/.env` (ignoré par git, voir `.env.example`),
par exemple les clés d'une application eBay pour les annonces eBay en direct.

## Développement

Prérequis : [uv](https://docs.astral.sh/uv/), Node.js 24, Google Chrome (lecture des prix
Vinted et eBay), et pour Tauri [Rust et les dépendances système](https://tauri.app/start/prerequisites/).

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

## Publier une version

Chaque push sur `main` (hors documentation) lance `.github/workflows/release.yml` : les
vérifications de la CI, puis le moteur et l'installateur Windows (NSIS, en français, sans
droits administrateur), la signature de la mise à jour et la release `vX.Y.N`. `X.Y` vient de
`desktop/package.json`, `N` du numéro d'exécution du workflow, si bien que chaque version est
plus récente que la précédente. Les apps installées la proposent au démarrage.

Pour passer à une nouvelle version majeure ou mineure, changer la base :
`npm run version:set -- 0.2.0` dans `desktop/`, puis commit et push.

Une fois pour toutes, le dépôt GitHub doit avoir le secret `TAURI_SIGNING_PRIVATE_KEY` : le
contenu de la clé privée créée par `npx tauri signer generate` (sa clé publique est dans
`desktop/src-tauri/tauri.conf.json`). Sans lui, le workflow ne publie rien et le signale. Sans signature de code Windows, SmartScreen avertit au
premier lancement de l'installateur (« Informations complémentaires » puis « Exécuter quand
même »).

Pour construire l'installateur en local :

```bash
cd engine
uv sync --group bundle
uv run python scripts/build_sidecar.py   # → desktop/src-tauri/binaries/

cd ../desktop
npm run tauri:build   # avec TAURI_SIGNING_PRIVATE_KEY dans l'environnement
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

## Recherche sur les sites japonais

Le moteur interroge Mercari et Rakuma comme le ferait leur site pour un visiteur anonyme :
aucun compte, quelques secondes entre deux requêtes vers un même site. L'achat reste manuel,
via le lien Neokyo de chaque annonce.

Yahoo! JAPAN (Auctions et Fleamarket) refuse les visiteurs de l'Union européenne depuis 2022 :
ces deux sources ne fonctionnent que hors d'Europe et sont désactivées par défaut. La page
Recherche propose la même recherche sur Neokyo, qui donne accès à Yahoo.

## Vinted et eBay

Ni Vinted ni eBay n'ouvrent leurs prix de vente aux logiciels, et leurs conditions
d'utilisation interdisent les robots. À la demande de l'utilisateur, Mekiki pilote donc une
fenêtre Chrome, avec un profil à part où il se connecte lui-même ; chaque lecture part d'un
clic, une page à la fois. La fenêtre travaille hors de l'écran (l'app en montre un aperçu en
direct) et n'apparaît que pour se connecter, terminer un formulaire ou passer une
vérification anti-robot, toujours laissée à l'utilisateur. L'usage reste à ses risques
vis-à-vis de ces sites.

Données utilisées : les fichiers publics de Cardmarket (catalogue et cotes), la base
[TCGdex](https://github.com/tcgdex/cards-database) (licence MIT), qui relie les cartes
Pokémon japonaises (extension, numéro) à leur produit Cardmarket, et les noms des Pokémon de
[PokéAPI](https://github.com/PokeAPI/pokeapi).
