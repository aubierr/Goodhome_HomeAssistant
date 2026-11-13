# Changelog

Toutes les modifications notables de ce projet seront documentées dans ce fichier.

Le format est basé sur [Keep a Changelog](https://keepachangelog.com/fr/1.0.0/),
et ce projet adhère au [Semantic Versioning](https://semver.org/lang/fr/).

## [2.2.12] - 2026-11-13

### Documentation
- 📚 [docs/BLUETOOTH.md](docs/BLUETOOTH.md) repris : résumé « En bref » en tête, nouvelle section « Conformité avec l'application officielle » (comparaison avec GoodHome Connect 2.1.4 décompilée : UUID, MTU, ordre du checksum, ACK/NACK, `cmdID`, appairage, attributs, écarts sans conséquence), et formats de la programmation horaire (`ble_get_prog` / `ble_set_prog`) et de l'OTA (`ble_ota` / `ble_ota_next`) regroupés dans « Fonctions non prises en charge ». Aucun changement de code

## [2.2.11] - 2026-11-13

### Corrigé
- 🔑 **Cloud : renouvellement du token comme l'application officielle.** L'intégration appelait `POST /v1/auth/refresh`, route absente de l'application ; elle utilise maintenant `GET /v1/auth/token` avec les en-têtes `access-token` et `refresh-token`. Le repli sur une nouvelle connexion reste en place. Vérifié sur l'API réelle : la nouvelle route répond HTTP 200 avec un `token` (sans repli sur le login), alors que l'ancienne route répondait HTTP 404 — le renouvellement échouait donc à chaque fois et l'intégration se reconnectait par login
- 📶 **Bluetooth local : un NACK est renvoyé quand le checksum d'une trame reçue est faux**, comme le fait l'application, et le message corrompu est ignoré au lieu d'être pris en compte

### Documentation
- 📚 `docs/MODES.md` aligné sur l'énumération `TARGET_MODE` de l'application (GoodHome Connect 2.1.4, décompilée) : noms officiels, corrections sur les modes 4, 8 et 70, valeurs de l'application sans entité (11, 31 à 35, 40 à 45, 50, 71, 99) et différence sur l'arrêt du radiateur
- 📚 `docs/BLUETOOTH.md` : le NACK sur checksum invalide

## [2.2.10] - 2026-11-13

### Ajouté
- 🏷️ **Bluetooth local : le radiateur nomme l'appareil « Home Assistant »**, avec le vrai format de la commande `system.bluetooth_set_mobile_device_name`, relevé dans l'application GoodHome Connect (`params` est le nom, une chaîne). Envoyé juste après l'appairage ; les appareils appairés avant et après sont écrits dans le journal (niveau info). Non encore vérifié sur un radiateur réel : une erreur est ignorée sans gêner l'appairage

## [2.2.9] - 2026-11-13

### Retiré
- ⏪ **Bluetooth local : l'envoi du nom « Home Assistant » au radiateur est retiré** (2.2.7 et 2.2.8). Le format de la commande `system.bluetooth_set_mobile_device_name` est inconnu et le radiateur ne l'a pas prise en compte ; le journal des appareils appairés ajouté en 2.2.8 disparaît avec lui

## [2.2.8] - 2026-11-13

### Modifié
- 🔍 **Bluetooth local : liste des appareils appairés dans le journal.** Après l'appairage, l'intégration lit `system.bluetooth_get_paired_devices` avant et après l'envoi du nom « Home Assistant », et écrit ces listes et la réponse du radiateur dans le journal (niveau info), pour trouver le vrai format de la commande de nommage, qui ne fonctionne pas encore sur un radiateur réel

## [2.2.7] - 2026-11-13

### Ajouté
- 🏷️ **Bluetooth local : le radiateur nomme l'appareil « Home Assistant »** dans sa liste de mobiles appairés (Réglage → Connexion → Paramètres avancés → Dissocier un mobile), au lieu d'une adresse. Le nom est envoyé juste après l'appairage, avec la commande `system.bluetooth_set_mobile_device_name` de l'application ; son format n'est pas encore vérifié sur un radiateur réel, et une erreur est ignorée sans gêner l'appairage

## [2.2.6] - 2026-11-13

### Corrigé
- 🔁 **Bluetooth local : une relecture qui échoue est retentée une fois**, sur une connexion neuve après une courte pause. Un proxy ESP32 saturé (erreurs GATT 133/143) ne rend plus un radiateur indisponible après une seule absence de réponse

### Modifié
- ⚡ **Bluetooth local : le démarrage n'attend plus les radiateurs**. La première lecture se fait en arrière-plan : un radiateur lent ou injoignable ne bloque plus l'installation de l'intégration, ses entités apparaissent dès sa première réponse et la relecture périodique réessaie sinon

## [2.2.5] - 2026-11-11

### Ajouté
- ⚡ **Compteur d'énergie de chaque radiateur** (`sensor.xxx_energy`, en kWh) : il cumule la puissance calculée (cycle de chauffe × puissance nominale) au fil du temps, garde sa valeur après un redémarrage de Home Assistant et s'ajoute directement au **tableau de bord énergie**, sans capteur d'intégration manuel. Rien n'est compté tant que le radiateur est indisponible

## [2.2.4] - 2026-11-11

### Modifié
- 📝 **Marche à suivre d'appairage** alignée sur l'application : Réglage → Connexion → Ajouter un mobile → Nouveau mobile → Suivant (écrans d'appairage, messages d'erreur, README et documentation, dans les 6 langues)

### Ajouté
- 🔔 **Rappel à la suppression d'un radiateur en Bluetooth local** : une notification demande de dissocier aussi le mobile sur le radiateur (Réglage → Connexion → Paramètres avancés → Dissocier un mobile → sélectionnez le mobile → Dissocier)

## [2.2.3] - 2026-11-04

### Corrigé
- 🌡️ **Avertissements de Home Assistant 2026.11 sur le thermostat** (`_attr_temperature_unit`, `current_temperature`, `target_temperature`, qui cesseront de fonctionner en 2027.11) : le thermostat utilise les nouveaux noms `native_*`. Les versions plus anciennes de Home Assistant restent prises en charge
- 📡 **Reconnexion en Bluetooth local**, surtout à travers un proxy ESPHome :
  - après un redémarrage de Home Assistant, une recherche active est demandée en attendant le radiateur : les proxys en mode `auto` écoutent en passif, et le message « not seen over Bluetooth recently » pouvait rester plusieurs minutes
  - un radiateur appairé est aussi reconnu à son nom : son adresse peut changer à travers un proxy
  - après un échange sans réponse ou raté, la connexion est refaite au lieu de réutiliser une liaison ouverte mais muette

## [2.2.2] - 2026-11-03

### Corrigé
- 📡 **Appairage et connexion à travers un proxy Bluetooth ESPHome**, vérifiés sur un vrai radiateur (ESPHome 2026.10, `io_capability: none`) :
  - avec des proxys seuls, le radiateur en mode appairage n'était jamais trouvé (« not seen over Bluetooth recently »), alors qu'il venait d'être entendu
  - l'appairage est demandé après la connexion (la demande pendant la connexion n'arrive pas jusqu'au proxy), sans agent BlueZ
  - la clé gardée par l'ESP32 d'un essai précédent est oubliée avant d'appairer
  - le chiffrement se terminant après la connexion, la première demande est renvoyée pendant 30 s, à l'appairage comme à chaque reconnexion (avant : « No answer from radiator »)

## [2.2.1] - 2026-11-01

Aucun changement de fonctionnement par rapport à la 2.2.0 : la 2.2.1 contient la correction des tests de validation.

### Corrigé
- ✅ Deux tests du mode Bluetooth échouaient sous Linux (validation GitHub) : l'oubli d'appairage BlueZ est simulé, et l'appareil est retrouvé sans `async_get_device`, refusé par les dernières versions de Home Assistant

## [2.2.0] - 2026-11-01

Les comptes cloud déjà configurés ne changent pas : mêmes entités, même fonctionnement.

### Ajouté
- 📶 **Mode Bluetooth local**, sans compte ni cloud : à l'ajout de l'intégration, un menu propose « Compte GoodHome (cloud) » ou « Bluetooth local (adaptateur nécessaire) »
- 🔗 Appairage guidé : le radiateur est d'abord mis en mode appairage (Réglages → Connexion → Ajouter), puis choisi sous son nom et appairé automatiquement. Chaque radiateur devient une entrée, nommée d'après sa pièce, avec les mêmes entités qu'en mode cloud
- 🔎 Radiateurs `GOODHOME-*` en mode appairage détectés automatiquement (carte dans **Découvertes**) ; tant qu'aucun radiateur n'est visible sous son nom, Valider relance la recherche. Un radiateur déjà appairé est listé avec son nom et son adresse, un radiateur déjà ajouté n'est plus proposé
- ⚡ En local, une commande est confirmée en une dizaine de secondes (45 s à 2 min en cloud), et un changement fait sur le radiateur arrive tout de suite par notification
- 🗓️ En local, un mode manuel permanent coupe le planning du radiateur (`noprog`) et le retour en `auto` le rallume : sinon le radiateur reprend son planning au bout de quelques secondes. Le mode est envoyé avec sa température, comme dans l'application
- 🛡️ Appairage robuste : ancien appairage oublié avant chaque essai, annonces de l'adresse oubliée ignorées, connexion sans redémarrage juste après l'appairage malgré l'adresse figée par Bleak
- 🗑️ En local, supprimer l'appareil d'un radiateur supprime aussi son entrée
- 💬 Erreurs d'appairage expliquées : radiateur introuvable (trop loin), appairage refusé (pas en mode appairage), échec avec le détail technique
- 📵 Sans adaptateur Bluetooth capable de se connecter, l'ajout en local l'indique clairement au lieu d'une liste vide
- ♻️ Supprimer un radiateur local permet de le redécouvrir (carte **Découvertes**) sans redémarrer Home Assistant
- 📡 Recherche Bluetooth active demandée tant qu'aucun radiateur n'est visible en mode appairage et pendant l'appairage, pour les radiateurs lointains (Home Assistant récent)
- 🩺 Radiateur introuvable ou connexion impossible : l'explication de Home Assistant (récepteurs, signal, connexions occupées) est ajoutée au message d'erreur (Home Assistant récent)
- 📖 [docs/BLUETOOTH.md](docs/BLUETOOTH.md) : protocole Bluetooth retrouvé dans l'application GoodHome Connect (service, trames, commandes, changement de mode, encodage des valeurs, pièges de l'appairage, limites connues, pistes d'amélioration)
- 🩺 Diagnostics : mode de connexion (`connection`) ; en local, adresse Bluetooth, numéro de série et nom du Wi-Fi sont masqués

### Modifié
- 🧭 Le formulaire de connexion au compte cloud est précédé du menu de choix du mode
- 📖 README : bouton d'installation HACS en haut de page, étapes d'installation détaillées et bouton « Ajouter l'intégration »
- 🧪 147 tests, 86 % du code. L'agent d'appairage BlueZ, qui ne fonctionne que sous Linux avec un adaptateur, est vérifié sur de vrais radiateurs et non par les tests

### Limites connues du mode local
- 📡 Portée du Bluetooth : vers −80 dBm, la connexion peut demander plusieurs essais, et l'appairage peut échouer faute d'annonce récente ; rapprocher l'adaptateur ou ajouter un proxy Bluetooth ESPHome (appairage à travers un proxy pas encore testé)
- ❔ Version matérielle et code défaut non transmis en Bluetooth (version « Unknown », capteur Problème toujours à OK)
- 🔔 Bouton Identifier accepté par le radiateur en Bluetooth, mais bip non confirmé (mesures, consignes et changements de mode vérifiés)
- 🐧 Appairage géré par BlueZ (Linux, dont Home Assistant OS) uniquement

## [2.1.1] - 2026-10-31

### Corrigé
- 🌡️ Un arrêt, le planning ou un preset choisi dans les 3 s qui suivent un changement de consigne n'est plus remplacé par cette consigne (mode 8) : le dernier choix l'emporte

## [2.1.0] - 2026-10-30

Aucun attribut n'est retiré : ils restent tous disponibles pour le débogage, et de nouveaux s'y ajoutent.

### ⚠️ Changement de comportement
- 🗓️ Un radiateur qui suit son planning (modes 30, 60, 61, et les forçages 9 et 10) s'affiche en mode HVAC `auto` au lieu de `heat`. Les automatisations qui testent l'état `heat` sont à revoir

### Ajouté
- 🗓️ Mode HVAC `auto` sur le thermostat : il remet le radiateur sur son planning (mode 60, confirmé quel que soit le mode choisi ensuite par le planning)
- 🔁 `climate.turn_on` rallume le radiateur dans son mode d'avant l'arrêt (planning, Manuel Confort, Manuel Éco ou consigne libre) au lieu de toujours passer en Manuel Confort : une automatisation « fenêtre ouverte → arrêt → rallumage » ne fait plus perdre le planning
- 🔍 Attribut `target_mode_value` sur le thermostat : valeur brute du mode, que plusieurs modes partagent en mode HVAC et en preset
- ⏳ Attribut `pending_confirmation` sur le thermostat, le select, les switches et les numbers : valeurs envoyées que le radiateur n'a pas encore confirmées
- 🧩 Attribut `other_fields` sur le capteur Informations appareil : champs envoyés par l'API qu'aucune entité n'exploite encore (nouveau firmware, nouveau modèle...)
- 📡 Diagnostics : état de l'écoute temps réel (connectée ou non, nombre de connexions, dernier événement, dernière erreur)
- 🎨 Icônes dans `icons.json`, avec une icône différente quand un réglage est désactivé (fenêtre, présence, auto-apprentissage, mode manuel) et une icône pour l'action Identifier

### Modifié
- ⚙️ Les switches et les températures de consigne (Number) sont rangés dans la section **Configuration** de l'appareil et n'apparaissent plus dans les tableaux de bord générés automatiquement
- 🎯 L'action `goodhome.identify_device` propose de choisir le radiateur dans la liste des appareils ; l'identifiant GoodHome des anciennes automatisations reste accepté
- 🔤 Les attributs `description` des températures de consigne sont en anglais, comme ceux des switches
- 🧪 100 tests, 94 % du code

## [2.0.0] - 2026-10-30

Publiée avec la 2.1.0.

Les identifiants des entités ne changent pas : historiques, tableaux de bord et automatisations restent valables.

### ⚠️ Changements incompatibles
- ⬆️ Home Assistant **2025.1** minimum : c'est la plus ancienne version testée, avec la dernière
- 🗑️ Configuration YAML supprimée : un bloc `goodhome:` avec `email`/`password` est importé automatiquement dans l'interface (une alerte demande de le retirer). Les configurations par `user_id`/`token` doivent être refaites depuis l'interface
- 🏷️ Les capteurs n'ont plus les attributs génériques répétés sur chacun (version firmware, nom de pièce...) : ils restent sur le capteur Informations appareil et le thermostat
- 🔌 Le capteur Consommation passe à « inconnu » au lieu de 0 W quand la puissance nominale ou la part de chauffe est inconnue
- 📊 Le capteur Cycle de chauffe n'a plus la classe « facteur de puissance », qui ne correspondait pas à la mesure

### Corrigé
- 🕒 Choisir « Auto Confort » ou « Auto Éco » n'affiche plus d'avertissement de non-confirmation : le radiateur passe en automatique et son planning choisit lui-même confort ou éco
- 📨 Une commande n'échoue plus quand la poignée de main Socket.io qui la précède échoue : elle ne fait qu'accélérer l'application par le radiateur
- ⚡ Une réponse inattendue du serveur ou une erreur en traitant un événement n'arrête plus l'écoute temps réel : l'erreur est journalisée et l'écoute continue
- 📝 Identifiants d'entités du README corrigés pour les nouvelles installations (ex. `sensor.xxx_current_temperature`, `switch.xxx_presence_detection`)
- 🖼️ L'icône de l'intégration s'affiche de nouveau (« Icon not available ») : depuis 2026, Home Assistant lit les images d'une intégration personnalisée dans son dossier `brand/`

### Ajouté
- 🌍 Traductions en espagnol, polonais, portugais et roumain (pays où GoodHome est vendu), en plus du français et de l'anglais
- 💬 Textes d'aide sous les champs de connexion ; preset « manual » et attributs du thermostat (`eco_reason`, `temperature_range`...) traduits
- 🔘 Bouton Identifier sur chaque radiateur (fait biper le radiateur, comme le service `goodhome.identify_device`)
- 🩺 Diagnostics téléchargeables, sans email, mot de passe, identifiants ni noms de pièces
- ❌ Une commande refusée par le cloud fait échouer l'action avec un message clair, au lieu d'une simple ligne de journal
- 🧪 Tests automatisés (78 tests, 94 % du code) sur un vrai Home Assistant avec une API simulée, et intégration continue GitHub (hassfest, HACS, tests)

### Modifié
- ⚙️ Client API entièrement asynchrone, sur la session HTTP de Home Assistant (plus de `requests` dans des threads)
- 🔁 Un seul renouvellement du token quand plusieurs requêtes reçoivent un 401 en même temps
- ⏱️ Les actions se terminent dès l'envoi de la commande ; la confirmation du radiateur (45 s à 2 min) est attendue en arrière-plan, sans bloquer les automatisations
- 🧹 Code des plateformes réécrit avec des descriptions d'entités : une base commune gère l'appareil, la disponibilité, l'état optimiste et la confirmation
- 💤 Les températures confort, éco et hors-gel en capteurs (doublons des entités Number) sont désactivées par défaut sur les nouvelles installations
- 📡 Classe IoT `cloud_push` (mises à jour poussées par le cloud)

## [1.1.0] - 2026-10-30

### Corrigé
- 🐛 Le réglage de la température depuis l'entité Climate ne fonctionnait plus (méthode `set_temperature` définie deux fois dans l'API)
- 🐛 Les erreurs de l'API étaient masquées : une panne au démarrage ne créait aucune entité, sans nouvelle tentative
- 🐛 Un échec de connexion au démarrage était ignoré (l'intégration continuait sans token)
- 🐛 Suppression du flux d'options vide, incompatible avec les versions récentes de Home Assistant
- 🐛 La plateforme Select plantait en configuration YAML
- 🐛 Les binary sensors utilisaient des clés de traduction invalides (« Connectivity », « Self Learning Improve »)
- 🐛 Le cache HTTP n'envoie plus d'en-tête `If-None-Match` sans avoir les données correspondantes (évite une erreur sur une réponse 304 après renouvellement du token)
- 🐛 Les logs des switches et des numbers affichaient `None` au lieu du nom de l'entité, et un délai de 30 s au lieu de 40 s
- 🐛 Après une commande, la valeur affichée revenait à l'ancienne au bout de 40 s, alors que le radiateur met de 45 s à 2 min à l'appliquer. L'attente de confirmation passe à 3 min et se termine dès que le radiateur confirme (Socket.io ou relecture), sans relire l'API toutes les 5 s
- 🐛 Le thermostat s'affichait arrêté en mode 0 (par défaut), alors que le radiateur chauffe ; seul le mode 3 (hors-gel) vaut OFF
- 🐛 Les modes éco 2 et 30 apparaissaient en preset `manual` au lieu de `eco`
- 🐛 Les modes inconnus s'affichaient « Par défaut » dans le select ; ils passent en état inconnu
- 🐛 Les options du select n'étaient pas traduites (libellés français codés en dur)

### Ajouté
- 🔐 Réauthentification depuis l'interface quand le mot de passe est refusé
- 🔁 Nouvelle tentative automatique de configuration si le cloud GoodHome est injoignable
- 🔥 Action en cours (`hvac_action`) sur le thermostat : chauffe / inactif / arrêt
- 🔘 Support de `climate.turn_on` / `climate.turn_off`
- 🏷️ Modèle, version firmware et version matérielle affichés sur l'appareil
- ➕ Les radiateurs ajoutés dans l'app GoodHome apparaissent sans redémarrer Home Assistant
- 🗑️ Un radiateur retiré du compte GoodHome peut être supprimé depuis l'interface
- ⚡ Mises à jour en temps réel : l'intégration écoute le Socket.io du cloud GoodHome (événements `setState` et `report`) au lieu d'attendre la relecture suivante. La relecture de l'API toutes les 30 s reste active en secours
- 🎯 Mode 4 (override provisoire) dans le select
- 💤 Preset `sleep` sur le thermostat pour l'absence courte (mode 12), distinct de `away` (absence longue)
- 📖 Documentation de tous les modes : [docs/MODES.md](docs/MODES.md)
- 🛎️ Service `goodhome.identify_device` disponible aussi avec la configuration par l'interface, avec sa description (`services.yaml`)

### Modifié
- ⬆️ Home Assistant **2024.11** minimum
- ⚠️ Les états de `select.xxx_target_mode` deviennent des clés (`manual_comfort`, `auto_eco`…) au lieu des libellés français : les automatisations qui testent ou choisissent une option sont à mettre à jour
- 🔒 Le mode 30 (éco auto sur absence) n'est plus sélectionnable : le radiateur le gère seul
- 📦 Suppression de la dépendance `requests` du manifest (fournie par Home Assistant)
- 🧹 `hacs.json` : suppression de la clé `domains` dépréciée, ajout de la version minimale de Home Assistant
- 🧹 Import de `EntityCategory` depuis `homeassistant.const`
- 🏷️ Le thermostat utilise `has_entity_name` : il porte le nom de l'appareil (nom affiché inchangé)
- 🩺 Les binary sensors Connectivité et Problème passent en catégorie Diagnostic
- 📉 Le sensor Température cible n'enregistre plus de statistiques long terme (valeur de consigne, pas une mesure)
- 🧹 Données d'exécution stockées dans `entry.runtime_data` au lieu de `hass.data`
- 🧹 Logs au format paresseux `%s` au lieu des f-strings
- ⏱️ Relecture de l'API toutes les 30 s au lieu de 60 s
- 🚀 La lecture des radiateurs ne fait plus de poignée de main Socket.io : 1 requête HTTP par cycle au lieu de 3 (testé sur l'API réelle)

## [1.0.0] - 2025-11-11

### Ajouté
- 🎉 Version initiale de l'intégration GoodHome
- ✅ Support complet de la plateforme Climate (thermostat)
- ✅ Support des Sensors (température, humidité, duty cycle, etc.)
- ✅ Support des Binary Sensors (connectivité, problèmes, auto-apprentissage)
- ✅ Support des Switches (fenêtre, présence, auto-apprentissage, mode manuel)
- ✅ Support des Select pour les modes targetMode (12 modes)
- 🔐 Authentification email/password avec refresh token automatique
- 🚀 Optimisation HTTP 304 Not Modified pour le cache
- 🔄 État optimiste avec polling de confirmation (40 secondes max)
- 🌐 Headers conformes à l'application GoodHome officielle
- 🇫🇷 Traductions françaises et anglaises
- ⚙️ Configuration via interface utilisateur (config flow)
- 📱 Regroupement des entités par appareil
- 🎯 Compatible avec les modes ESPHome_GoodHome

### Optimisations
- Cache ETag pour réduire la bande passante (50-70% de gain)
- Polling intelligent avec constantes centralisées (8 × 5s = 40s)
- Invalidation automatique du cache après modification

### Technique
- API Socket.io pour la connexion initiale
- API REST v1 pour les commandes et états
- Headers `access-token` et `if-none-match` conformes
- Paramètres booléens au format JSON (`true/false`)
- Support des modes targetMode 0-70
