## Corrections importantes

- Sauvegardes : restaurer la plus ancienne copie pouvait vider toute la base. C'est corrigé, et
  une copie abîmée est maintenant refusée sans toucher à vos données. Les copies faites à la
  main ne font plus disparaître les copies quotidiennes. Restaurer demande désormais le mot de
  passe du premier compte créé sur ce PC, puisque tous les comptes reviennent en arrière.
- Mekiki ne s'arrête plus de chercher en silence après une erreur imprévue (une cote
  Cardmarket mal formée, par exemple) : les recherches et la sauvegarde du jour continuent.
- Une mise à jour qui échouerait en cours de route ne peut plus bloquer le démarrage de Mekiki.
- L'application s'ouvre même si son moteur ne démarre pas, et le relance tout seul s'il
  s'arrête.
- Vendeurs bloqués à tort : « 代行OK、値下げ不可 » (intermédiaires acceptés, pas de remise) était lu
  comme un refus des intermédiaires. Ces vendeurs sont débloqués.

## Ventes et comptabilité

- La comptabilité compte chaque vente au taux de cotisation en vigueur le jour de la vente,
  même si vous le changez ensuite (fin de l'ACRE, par exemple).
- Rien n'est demandé à déclarer avant la date de début de votre activité.
- Les ventes eBay pas encore rapprochées apparaissent dans la comptabilité, à rapprocher avant
  de déclarer.
- Import eBay : une vente annulée (un retour) ne revient plus au prochain import, une même
  ligne n'est plus comptée deux fois, et une vente de plusieurs exemplaires se rapproche carte
  par carte.
- Une carte ou un lot vendus ne peuvent plus être supprimés : leurs ventes disparaîtraient de
  la comptabilité. Annulez d'abord la vente.
- Le registre des achats indique quand la TVA d'import est encore estimée, et « À faire »
  rappelle les lots dont la facture de TVA reste à saisir.
- Frais eBay par défaut plus réalistes pour un nouveau compte (11 % + 0,35 €) : vérifiez-les
  dans Paramètres.

## Recherche de cartes

- Prix eBay plus justes : les cartes gradées écrites « PSA10 », les lots, les autres versions
  de la carte (parallèle, manga, miroir) et les annonces en anglais ne faussent plus la
  médiane, et Luffy, Ace ou Teach trouvent enfin leurs ventes. eBay ne compte comme débouché
  qu'avec au moins 3 ventes réussies.
- One Piece : une parallèle n'est plus chiffrée au prix de la version manga.
- Titres mieux lus : « PSA10級 » et « 未鑑定 » sont des cartes non gradées, « パック産 » n'est pas un
  booster, « ノンパラ » est la version normale, la carte Master Ball n'est pas un miroir, et le
  filtre de rareté HR fonctionne.
- Une annonce vendue, ou dont le prix a monté, laisse sa place dans le colis. Les enchères
  restent hors du colis, et une réponse inattendue d'un site n'est plus prise pour une vente.
- Les recherches filtrées restent rapides, et un site qui bloque n'est plus redemandé pour
  chaque carte.

## Interface et mise en vente

- La fiche d'une carte ne montre plus le verdict de la carte précédente.
- Bloquer un vendeur depuis la fiche retire aussi son annonce des listes.
- « Acheté : ajouter au stock » explique quoi faire quand aucun lot n'est en cours d'achat.
- Les messages d'erreur sont plus clairs (Chrome absent, quota de traduction épuisé…).
- Mise en vente : une même carte ne peut plus être publiée deux fois par erreur, un état non
  reconnu bloque la publication au lieu de partir en « Near Mint », et la lecture des ventes
  eBay n'écrase plus un formulaire laissé ouvert.
- Traduction : les paragraphes sont gardés, et ce qui a déjà été traduit reste affiché même
  quand le quota gratuit s'épuise en cours de route.
