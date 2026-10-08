# Mekiki

Application desktop d'achat-revente de cartes TCG (Pokémon, One Piece) achetées au Japon via
Neokyo et revendues en Europe. `engine/` est le moteur Python (FastAPI + SQLite) ;
`desktop/` est l'interface Nuxt 4 + Nuxt UI 4 empaquetée avec Tauri 2, qui lance le moteur
comme sidecar en release seulement. Chaque revendeur a son compte (`auth.py`, jeton porteur) :
toute donnée (lots, cartes suivies, favoris, paramètres) appartient à un `user_id`.

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

## Scanner (`engine/mekiki_engine/scanner/`)

- `cardmarket.py` importe les fichiers publics de Cardmarket (Pokémon = 6, One Piece = 18),
  avec ETag. Cote de revente : avg30, sinon avg7, avg, avg1, trend ; jamais `low`.
- `sources/` : une classe par site. Mercari passe par l'API JSON de son site avec une preuve
  DPoP signée localement (`ecdsa`, pur Python à cause de Smart App Control).
- `matching.py` décide si un titre japonais est la carte suivie (numéro, mots requis ou
  exclus, cartes gradées) ; `pricing.py` chiffre une annonce comme une carte d'un colis type.
- Découverte (`discovery.py`) : recherches larges dans la catégorie, `identify.py` lit le titre
  (extension + numéro, code One Piece, miroir, parallèle/manga), `resolver.py` trouve le
  produit Cardmarket. Pokémon passe par `card_index.py` (archive TCGdex, rafraîchie chaque
  semaine) ; One Piece par le nom Cardmarket (« (OP05-119) ») dans les extensions japonaises
  (« Non-English » / « Asia Region Legal »), les versions étant rangées par `idProduct`.
- Une annonce à moins de 20 % de la cote est presque toujours une reproduction ou un
  accessoire : elle est signalée et n'entre jamais dans un colis proposé.
- Une annonce réservée (« 様専用 », « 取り置き », « 即購入不可 »…) est écartée par `matching.py` :
  l'achat par Neokyo serait annulé. L'état (`ListingCondition`, six niveaux des fripes
  japonaises) vient des résultats Mercari et Yahoo Fleamarket ; Rakuma ne le donne que sur la
  page de l'annonce.
- `availability.py` demande au site si une annonce est encore en vente (Mercari, Rakuma) :
  à l'ouverture de sa fiche, et pour chaque carte du colis proposé par la découverte, une
  vendue cédant sa place à la suivante. Une requête par annonce, jamais en masse.
- Yahoo! JAPAN bloque l'Europe (403) : ne pas tenter de contourner le blocage.
- Les tests n'accèdent jamais au réseau : `create_app(..., http_transport=..., source_factory=...)`
  et `background_jobs=False` (voir `engine/tests/conftest.py`).
- Rester poli avec les sites : pas de requêtes en parallèle vers un même site, intervalles de
  `PoliteClient`, jamais de compte ni de connexion sur les sites japonais.
- Cartes suivies (`tracking.py`) : liée à un produit Cardmarket japonais, une carte ne garde que
  les annonces de son impression exacte ; `names.py` traduit les noms français et anglais en
  japonais (PokéAPI pour les Pokémon, liste des personnages pour One Piece).

## Revente (`engine/mekiki_engine/resale/`, `browser/`)

- `verdict.py` juge une carte (produit, annonce japonaise, carte en stock) sur chaque
  débouché : cote Cardmarket, eBay (API Browse si clés, sinon ventes lues dans Chrome), Vinted.
  Les ventes réussies eBay, triées des plus récentes, donnent aussi la fréquence de vente
  (ventes sur 30 et 90 jours).
- `browser/` pilote une fenêtre Chrome hors écran (journal de ses étapes dans l'app), profil propre
  à Mekiki, par le protocole DevTools ; elle ne s'affiche que pour se connecter, finir un
  formulaire ou passer une vérification anti-robot. **Exception voulue par l'utilisateur** à la règle « jamais de connexion » : il s'y
  connecte lui-même à Vinted et eBay (Mekiki ne voit jamais de mot de passe). Chaque action part
  d'un clic dans l'app, une page à la fois ; ne jamais contourner une vérification anti-robot.
- Les secrets (clés eBay…) sont dans `engine/.env`, jamais dans le dépôt.

## Releases

- Chaque push sur `main` lance `.github/workflows/release.yml` : la CI (`ci.yml`, appelée en
  workflow réutilisable), puis l'installateur NSIS signé pour la mise à jour, `latest.json`
  pour le plugin updater et la copie `Mekiki-Setup.exe` du lien de la page d'accueil. La
  version vaut `X.Y` de `desktop/package.json` + le numéro d'exécution du workflow ;
  `npm run version:set -- X.Y.0` (dans `desktop/`) change la base.
- Ne jamais changer `identifier` dans `desktop/src-tauri/tauri.conf.json`
  (`io.github.antoine-gourgue.mekiki`) : il fixe le dossier de données de l'app installée
  (`%APPDATA%\io.github.antoine-gourgue.mekiki`, base et photos), que les mises à jour
  conservent. Le changer ferait repartir chaque installation d'une base vide.
- La clé privée de signature des mises à jour ne quitte pas la machine (`~/.tauri/`) et le
  secret GitHub `TAURI_SIGNING_PRIVATE_KEY` ; ne jamais la committer.
- Les notes de version sont en français dans `desktop/release-notes.md` : la release et la
  fenêtre de mise à jour de l'app les affichent. Avant chaque push qui change l'app, les
  réécrire pour dire ce qui change pour l'utilisateur (titres `##`, puces `-`), sans jargon.

## Pièges connus (Windows, octobre 2026)

- Smart App Control bloque les binaires récents sans réputation : le Python géré par uv,
  les extensions Cython de SQLAlchemy 2.1, le lanceur `.venv/Scripts/mekiki-engine.exe`, et la
  compilation Rust. D'où le Python officiel signé (python.org), SQLAlchemy limité à `<2.1` (qui
  retombe en Python pur), et `uv run python -m mekiki_engine` plutôt que `uv run mekiki-engine`.
  Sur la machine de développement, il est désactivé depuis le 7 octobre 2026 pour Tauri ; un
  utilisateur qui l'a activé verra l'installateur non signé bloqué.
- Lancer `chrome.exe --version` sous Windows ouvre une fenêtre au lieu d'afficher la version :
  lire la version du fichier (`(Get-Item …chrome.exe).VersionInfo`).
- Nuxt est bloqué en `~4.5.2` : en 4.6.0, `nuxt generate` échoue au prérendu sous Windows
  (le renderer est externalisé et ses imports virtuels ne sont pas résolus).
- TypeScript reste en 6.x : `vue-tsc` dépend de l'API JavaScript de TypeScript, absente de
  TypeScript 7.
- Dans Tauri, un lien `target="_blank"` n'ouvre rien : passer par `openExternal()`
  (`desktop/app/utils/external.ts`).
