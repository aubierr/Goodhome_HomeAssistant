# Changelog

Toutes les modifications notables de ce projet seront documentées dans ce fichier.

Le format est basé sur [Keep a Changelog](https://keepachangelog.com/fr/1.0.0/),
et ce projet adhère au [Semantic Versioning](https://semver.org/lang/fr/).

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
