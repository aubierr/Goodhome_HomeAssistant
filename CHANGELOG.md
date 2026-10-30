# Changelog

Toutes les modifications notables de ce projet seront documentées dans ce fichier.

Le format est basé sur [Keep a Changelog](https://keepachangelog.com/fr/1.0.0/),
et ce projet adhère au [Semantic Versioning](https://semver.org/lang/fr/).

## [1.1.0] - 2026-10-30

### Corrigé
- 🐛 Le réglage de la température depuis l'entité Climate ne fonctionnait plus (méthode `set_temperature` définie deux fois dans l'API)
- 🐛 Les erreurs de l'API étaient masquées : une panne au démarrage ne créait aucune entité, sans nouvelle tentative
- 🐛 Un échec de connexion au démarrage était ignoré (l'intégration continuait sans token)
- 🐛 Suppression du flux d'options vide, incompatible avec les versions récentes de Home Assistant
- 🐛 La plateforme Select plantait en configuration YAML
- 🐛 Les binary sensors utilisaient des clés de traduction invalides (« Connectivity », « Self Learning Improve »)
- 🐛 Les logs des switches et des numbers affichaient `None` au lieu du nom de l'entité, et un délai de 30 s au lieu de 40 s

### Ajouté
- 🔐 Réauthentification depuis l'interface quand le mot de passe est refusé
- 🔁 Nouvelle tentative automatique de configuration si le cloud GoodHome est injoignable
- 🔥 Action en cours (`hvac_action`) sur le thermostat : chauffe / inactif / arrêt
- 🔘 Support de `climate.turn_on` / `climate.turn_off`
- 🏷️ Modèle, version firmware et version matérielle affichés sur l'appareil
- 🛎️ Service `goodhome.identify_device` disponible aussi avec la configuration par l'interface, avec sa description (`services.yaml`)

### Modifié
- ⬆️ Home Assistant **2024.11** minimum
- 📦 Suppression de la dépendance `requests` du manifest (fournie par Home Assistant)
- 🧹 `hacs.json` : suppression de la clé `domains` dépréciée, ajout de la version minimale de Home Assistant
- 🧹 Import de `EntityCategory` depuis `homeassistant.const`
- 🏷️ Le thermostat utilise `has_entity_name` : il porte le nom de l'appareil (nom affiché inchangé)
- 🩺 Les binary sensors Connectivité et Problème passent en catégorie Diagnostic
- 📉 Le sensor Température cible n'enregistre plus de statistiques long terme (valeur de consigne, pas une mesure)
- 🧹 Données d'exécution stockées dans `entry.runtime_data` au lieu de `hass.data`
- 🧹 Logs au format paresseux `%s` au lieu des f-strings
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
