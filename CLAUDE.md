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
- Pokémon sans code d'extension : le nom japonais de l'index doit figurer dans le titre (il
  départage les extensions de même taille et écarte les cartes anciennes absentes de l'index).
  Sans numéro, le nom suivi de la rareté suffit, mais seulement pour les ères SV et MEGA, que
  l'index couvre entièrement, ou quand le titre nomme l'extension (code ou nom japonais, même
  coupé par « … ») ; confiance « medium ». Mesurer toute règle de reconnaissance sur de vraies
  annonces avant de la garder.
- TCGdex n'a pas les cartes japonaises de beaucoup d'extensions (S10b, S4, S6a, S10D, XY,
  BW… : seulement l'impression chinoise, sans lien Cardmarket), et les produits japonais de
  Cardmarket n'ont pas de numéro. `tcgplayer.py` les relie par la liste numérotée de TCGplayer
  (export public TCGCSV, catégorie 85) : nom anglais identique, et versions rangées pareil par
  numéro, par `idProduct` et par prix sur les deux sites ; sinon rien n'est relié (811 cartes
  justes sur 811 vérifiées contre TCGdex). Le nom japonais vient de PokéAPI (`names.py`), donc
  seulement pour les Pokémon. Une panne de TCGCSV laisse l'index TCGdex intact.
  `INDEX_FORMAT` (`card_index.py`) force la reconstruction de l'index quand il change.
- Un colis trop court porte trop de frais fixes : `fill_parcel` le complète avec des annonces
  sous l'objectif qui relèvent son ROI ; sous l'objectif, `short_of_target` explique pourquoi.
  Chaque étape va dans `DiscoveryRun.log` (`note()`), affiché par `ActivityLog.vue`.
- Une annonce à moins de 20 % de la cote est presque toujours une reproduction ou un
  accessoire : elle est signalée et n'entre jamais dans un colis proposé.
- Une annonce réservée (« 様専用 », « 取り置き », « 即購入不可 »…) est écartée par `matching.py` :
  l'achat par Neokyo serait annulé. Les boosters aussi (« 1パック », « バラパック »…) : leur titre
  cite les cartes à tirer (« メガカイリューex MUR »), lu comme celui d'une carte. « 拡張パック »
  fait partie d'un nom d'extension et « ブースター » seul est Pyroli. L'état (`ListingCondition`, six niveaux des fripes
  japonaises) vient des résultats Mercari et Yahoo Fleamarket ; Rakuma ne le donne que sur la
  page de l'annonce : avec un état minimum, la découverte garde ses annonces et lit l'état sur
  la page de celles qui entrent dans le colis (`CONDITION_ON_PAGE`).
- `availability.py` demande au site si une annonce est encore en vente (Mercari, Rakuma) :
  à l'ouverture de sa fiche, et pour chaque carte du colis proposé par la découverte, une
  vendue cédant sa place à la suivante. Une requête par annonce, jamais en masse.
- Yahoo! JAPAN bloque l'Europe (403) : ne pas tenter de contourner le blocage.
- Vendeurs bloqués (`sellers.py`, table `blocked_sellers` commune aux comptes) : Neokyo refuse
  d'acheter chez certains vendeurs, et sa liste est derrière Cloudflare (jamais contournée).
  Mekiki les écarte par l'identifiant du vendeur (`sellerId` des résultats Mercari) ; la
  vérification d'une annonce du colis lit la description (refus d'intermédiaire : « 代行 »,
  « 転送 », « 業者お断り », mais pas « 海外発送不可 ») et les évaluations, et bloque le vendeur.
  L'utilisateur bloque les autres d'un clic (« Vendeur bloqué sur Neokyo »).
- Les tests n'accèdent jamais au réseau : `create_app(..., http_transport=..., source_factory=...)`
  et `background_jobs=False` (voir `engine/tests/conftest.py`).
- Rester poli avec les sites : pas de requêtes en parallèle vers un même site, intervalles de
  `PoliteClient`, jamais de compte ni de connexion sur les sites japonais.
- Cartes suivies (`tracking.py`) : liée à un produit Cardmarket japonais, une carte ne garde que
  les annonces de son impression exacte ; `names.py` traduit les noms français et anglais en
  japonais (PokéAPI pour les Pokémon, liste des personnages pour One Piece).

## Gestion (`engine/mekiki_engine/services/`)

- `backups.py` : copie quotidienne de la base (API de sauvegarde SQLite, à chaud) par la
  boucle du `ScannerWorker`, 30 gardées dans `backups/` ; une restauration copie d'abord l'état
  actuel et repasse les migrations. Restauration seulement si le moteur écoute en local.
- `books.py` : livre des recettes et registre des achats (CSV pour Excel : `;`, virgule
  décimale, BOM), chiffre d'affaires et cotisations par mois ou trimestre, échéances URSSAF
  (dernier jour du mois suivant), seuils réglables dans `AppSettings.business`. Mekiki ne
  déclare rien lui-même.
- `tasks.py` : la liste « À faire » (déclaration, ventes à expédier, lots en route, cartes à
  mettre en vente, bonnes affaires, stock qui dort, sauvegarde en échec). `key` change à chaque
  nouveauté : l'app n'envoie qu'une notification Windows par clé (plugin notification de Tauri).

## Revente (`engine/mekiki_engine/resale/`, `browser/`)

- `verdict.py` juge une carte (produit, annonce japonaise, carte en stock) sur Cardmarket et
  eBay : ventes réussies lues dans Chrome d'abord, sinon médiane des annonces en cours (API
  Browse, clés du compte). Les ventes réussies, triées des plus récentes, donnent aussi la
  fréquence de vente (ventes sur 30 et 90 jours). Vinted reste un débouché (ventes, publication)
  mais ses prix ne sont plus lus.
- `browser/` pilote une fenêtre Chrome hors écran (journal de ses étapes dans l'app), profil propre
  à Mekiki, par le protocole DevTools ; elle ne s'affiche que pour se connecter, finir un
  formulaire ou passer une vérification anti-robot. **Exception voulue par l'utilisateur** à la règle « jamais de connexion » : il s'y
  connecte lui-même à Vinted et eBay (Mekiki ne voit jamais de mot de passe). La lecture des
  ventes eBay part de l'ouverture de la fiche d'une carte (trois recherches d'une page au plus,
  1,5 à 3,5 s d'écart, gardées 6 h) ; la publication part d'un clic. Une page à la fois ; ne
  jamais contourner une vérification anti-robot.
- Chaque compte saisit ses clés eBay (jeu Production) dans Paramètres : vérifiées auprès
  d'eBay avant d'être gardées (réglage `ebay:{user_id}`), le Cert ID n'est jamais renvoyé.
  Les clés de `engine/.env` servent aux comptes sans clés. Aucun secret dans le dépôt.
- Vinted bloque l'adresse qui lit ses recherches (« Ta session a été bloquée ») : Mekiki ne les
  lit plus du tout. Ne pas y revenir, ni chercher à contourner le blocage.
- Ventes eBay : importées du rapport des commandes (CSV du Seller Hub, `services/ebay_report.py`,
  en-têtes anglais ou français, montants hors euros refusés), pas d'une connexion OAuth au compte
  vendeur. Une ligne rejoint la carte dont Mekiki a publié l'annonce (`items.listing_ref`, numéro
  d'objet eBay) ; `sales.external_ref` (« ebay:commande:objet ») évite les doublons et un rapport
  plus récent ne complète que l'expédition et le suivi ; les autres lignes attendent dans
  `pending_sales` (rapprochées à la main, ou écartées sans revenir à l'import suivant).

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
- Une mise à jour remplace `mekiki-engine.exe`, ce que Windows refuse tant qu'il tourne. Or le
  plugin updater ferme l'app par `std::process::exit` (sans `RunEvent::Exit`). D'où trois
  gardes : la fenêtre de mise à jour télécharge, appelle `stop_engine` (arrêt propre, puis
  `taskkill` si besoin, jusqu'à ce que le fichier soit libre), puis installe ; l'installateur
  NSIS tue aussi le moteur (`src-tauri/windows/hooks.nsh`) ; `start_engine` le relance si
  l'installation échoue.

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
- Ne pas tester un `taskkill /IM mekiki-engine.exe` sur la machine de développement : il
  arrête aussi le moteur de l'app installée, qui reste ouverte sans lui.
- Clés eBay refusées en `invalid_client` alors qu'elles sont bien copiées : le jeu Production
  reste désactivé tant que les notifications de suppression de compte ne sont pas réglées
  sur developer.ebay.com (l'exemption convient, Mekiki ne garde aucune donnée d'utilisateur).
