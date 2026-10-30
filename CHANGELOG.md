# Changelog

Toutes les modifications notables de ce projet seront documentées dans ce fichier.

Le format est basé sur [Keep a Changelog](https://keepachangelog.com/fr/1.0.0/),
et ce projet adhère au [Semantic Versioning](https://semver.org/lang/fr/).

## [2.0.0] - Non publiée

Les identifiants des entités ne changent pas : historiques, tableaux de bord et automatisations restent valables.

### ⚠️ Changements incompatibles
- 🗑️ Configuration YAML supprimée : un bloc `goodhome:` avec `email`/`password` est importé automatiquement dans l'interface (une alerte demande de le retirer). Les configurations par `user_id`/`token` doivent être refaites depuis l'interface
- 🏷️ Les capteurs n'ont plus les attributs génériques répétés sur chacun (version firmware, nom de pièce...) : ils restent sur le capteur Informations appareil et le thermostat
- 🔌 Le capteur Consommation passe à « inconnu » au lieu de 0 W quand la puissance nominale ou la part de chauffe est inconnue
- 📊 Le capteur Cycle de chauffe n'a plus la classe « facteur de puissance », qui ne correspondait pas à la mesure

### Ajouté
- 🔘 Bouton Identifier sur chaque radiateur (fait biper le radiateur, comme le service `goodhome.identify_device`)
- 🩺 Diagnostics téléchargeables, sans email, mot de passe, identifiants ni noms de pièces
- ❌ Une commande refusée par le cloud fait échouer l'action avec un message clair, au lieu d'une simple ligne de journal
- 🧪 Tests automatisés (63 tests, 93 % du code) sur un vrai Home Assistant avec une API simulée, et intégration continue GitHub (hassfest, HACS, tests)

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
