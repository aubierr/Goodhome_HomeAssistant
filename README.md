# GoodHome Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
![Version](https://img.shields.io/badge/version-1.1.0-blue.svg)
![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.11+-brightgreen.svg)

Intégration Home Assistant complète pour les radiateurs connectés **GoodHome** (marque Kingfisher - Castorama/Brico Dépôt).

## 📋 Fonctionnalités

### Plateformes supportées
- ✅ **Climate** - Contrôle complet du thermostat avec attribut `eco_reason`
- ✅ **Sensor** - Température, humidité, puissance, consommation, jours d'apprentissage
- ✅ **Binary Sensor** - Connectivité, problèmes, auto-apprentissage
- ✅ **Switch** - Détection fenêtre ouverte, présence, auto-apprentissage, mode manuel
- ✅ **Select** - Sélection des modes targetMode (14 modes)
- ✅ **Number** - Réglage des températures confort, éco et hors-gel

### Caractéristiques principales
- 🔐 Authentification par email/password avec refresh token automatique
- 🚀 Cache HTTP 304 Not Modified pour optimiser les performances
- ⚡ Mises à jour en temps réel via Socket.io (réglages et mesures), relecture de l'API toutes les 30 s en secours
- 🔄 État optimiste : la nouvelle valeur s'affiche tout de suite et reste affichée jusqu'à la confirmation du radiateur (3 min max)
- 🌐 Support complet de l'API GoodHome officielle
- 🎯 100% compatible avec le projet ESPHome_GoodHome
- 🇫🇷🇬🇧 Interface multilingue (français et anglais)
- ⚙️ Configuration via interface utilisateur (config flow)
- 📊 Calcul automatique de la consommation électrique
- 🎓 Suivi de la période d'apprentissage (14 jours)
- 🏠 Détection automatique d'absence avec mode éco

## 📦 Installation

### Pré-requis

⚠️ **Important** : Avant d'installer cette intégration, votre radiateur GoodHome doit être connecté au cloud GoodHome. Cette opération se fait depuis l'application mobile officielle **GoodHome** (disponible sur Android et iOS).

- Home Assistant **2024.11** ou plus récent

### Via HACS (recommandé)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=K0n3k&repository=Goodhome_HomeAssistant&category=integration)

### Installation manuelle

1. Copiez le dossier `custom_components/goodhome` dans votre dossier `custom_components` de Home Assistant
2. Redémarrez Home Assistant

## ⚙️ Configuration

### Via l'interface utilisateur (recommandé)

1. Allez dans **Paramètres** → **Appareils et services**
2. Cliquez sur **Ajouter une intégration**
3. Recherchez **GoodHome**
4. Entrez vos identifiants GoodHome (email et mot de passe)
5. Vos thermostats apparaîtront automatiquement !

### Via YAML (optionnel)

```yaml
goodhome:
  email: !secret goodhome_email
  password: !secret goodhome_password
```

Dans `secrets.yaml` :
```yaml
goodhome_email: "votre@email.com"
goodhome_password: "votre_mot_de_passe"
```

## 📱 Entités créées

Pour chaque thermostat GoodHome, les entités suivantes sont créées :

### Climate
- `climate.xxx` - Contrôle du thermostat
  - Température cible
  - Modes HVAC (Heat, Off), avec les actions `climate.turn_on` / `climate.turn_off`
  - Action en cours (`hvac_action`) : `heating` quand le radiateur chauffe (duty cycle > 0), `idle` sinon
  - Presets (Confort, Éco, Manuel, Absence, Absence courte `sleep`)
  - Attributs étendus :
    - `eco_reason` : `manual` / `absence` / `schedule` / `null`
    - `self_learning_days` : Progression de l'apprentissage (0-14)
    - `temperature_range` : `cold` / `medium` / `hot`
    - `temperature_color` : Code couleur pour l'interface

### Sensors
- `sensor.xxx_temperature` - Température actuelle
- `sensor.xxx_target_temperature` - Température cible
- `sensor.xxx_humidity` - Humidité
- `sensor.xxx_duty_cycle` - Cycle de chauffe (%)
- `sensor.xxx_power_consumption` - Consommation électrique calculée (W)
- `sensor.xxx_comfort_temp` - Température confort
- `sensor.xxx_eco_temp` - Température éco
- `sensor.xxx_antifreeze_temp` - Température hors-gel
- `sensor.xxx_self_learning_days` - Jours d'apprentissage (0-14)
- `sensor.xxx_device_info` - Informations appareil (diagnostic)

### Binary Sensors
- `binary_sensor.xxx_connectivity` - État de connexion
- `binary_sensor.xxx_self_learning_improve` - Amélioration auto-apprentissage
- `binary_sensor.xxx_problem` - Détection de problème

### Switches
- `switch.xxx_open_window_detection` - Détection fenêtre ouverte
- `switch.xxx_presence_sensor` - Détecteur de présence
- `switch.xxx_self_learning` - Mode auto-apprentissage
- `switch.xxx_manual_mode` - Mode manuel (noprog)

### Select
- `select.xxx_target_mode` - Sélection du mode de fonctionnement
  - Par défaut (provisoire)
  - Manuel Confort / Éco / Hors-gel / Manuel
  - Override / Override provisoire
  - Forcé Confort / Éco
  - **Éco auto (absence)** - Mode 30, en lecture seule
  - Auto Confort / Éco
  - Absence courte / longue

### Number
- `number.xxx_comfort_temperature` - Température confort (7-30°C, pas de 0.5°C)
- `number.xxx_eco_temperature` - Température éco (7-30°C, pas de 0.5°C)
- `number.xxx_antifreeze_temperature` - Température hors-gel (7-30°C, pas de 0.5°C)

### Appareil
Chaque thermostat apparaît comme un appareil avec son modèle (`codeName`, ex. `DLRIRFH1800`), sa version de firmware et sa version matérielle.

- **Nouveau radiateur** : un radiateur ajouté dans l'app GoodHome apparaît automatiquement dans Home Assistant à la mise à jour suivante (30 s maximum), sans redémarrage.
- **Radiateur retiré** : ses entités passent en « indisponible ». Pour le supprimer, ouvrez l'appareil dans **Paramètres** → **Appareils et services** → **GoodHome**, puis **⋮** → **Supprimer**. La suppression n'est proposée que pour un radiateur qui n'existe plus dans le compte GoodHome.

### Service `goodhome.identify_device`
Fait biper un thermostat pour le localiser.

```yaml
action: goodhome.identify_device
data:
  device_id: "5f1e2d3c4b5a69788796a5b4"  # attribut device_id du sensor Informations appareil
```

## 🎯 Modes targetMode

L'entité `select.xxx_target_mode` permet de contrôler finement le comportement du radiateur avec 14 modes :

| Mode | Valeur | Description |
|------|--------|-------------|
| Par défaut | 0 | Mode provisoire, retour au défaut |
| Manuel Confort | 1 | Manuel à température confort |
| Manuel Éco | 2 | Manuel à température éco |
| Manuel Hors-gel | 3 | Manuel anti-gel (OFF) |
| Override provisoire | 4 | Provisoire, température override |
| Absence longue | 5 | Absence longue durée (holidayTimeout) |
| Override | 8 | Manuel avec température override |
| Forcé Confort | 9 | Forcé confort avec retour auto |
| Forcé Éco | 10 | Forcé éco avec retour auto |
| Absence courte | 12 | Absence courte (overrideTime) |
| **Éco auto (absence)** | **30** | **Éco automatique après 20+ min sans présence** |
| Auto Confort | 60 | Mode auto période présence |
| Auto Éco | 61 | Mode auto période absence |
| Manuel | 70 | Mode manuel (mise à jour récente) |

Détail de chaque mode, correspondance avec l'entité `climate` et écarts connus : [docs/MODES.md](docs/MODES.md).

### 🆕 Mode 30 - Détection d'absence automatique

Le **mode 30** est un mode spécial qui se déclenche automatiquement :
- 📡 Le radiateur détecte l'absence de présence pendant plus de 20 minutes
- 🌡️ Il passe automatiquement en température éco pour économiser l'énergie
- ↩️ Retour automatique au mode normal dès détection de présence
- 📊 Visible dans l'attribut `eco_reason` du climate : `"absence"`

**Note** : Ce mode est géré par le radiateur lui-même : le select l'affiche mais refuse de le sélectionner.

## 🔌 Compatibilité API

Cette intégration utilise les mêmes endpoints et headers que l'application GoodHome officielle :

- **Socket.io** : `authorization: Bearer {token}`. Une connexion reste ouverte pour recevoir en temps réel les événements `setState` (réglage modifié) et `report` (mesures du radiateur), qui ne contiennent que les champs modifiés. Une poignée de main a aussi lieu avant chaque commande : elle raccourcit le délai avant que le radiateur l'applique.
- **API v1** : `access-token: {token}` + `if-none-match: {etag}`
- **Cache HTTP 304** : Optimisation de la bande passante
- **Paramètres booléens** : Format `true/false` JSON

Référence : Compatible avec [ESPHome_GoodHome](https://github.com/Benichou34/ESPHome_GoodHome)

## 📊 Performances

Grâce au cache HTTP 304 Not Modified :
- **Sans cache** : ~1-2 secondes par requête
- **Avec cache 304** : ~0.3-0.6 secondes par requête
- **Gain** : 50-70% de réduction du temps de réponse

## 🔧 Suivi d'énergie

La consommation électrique est maintenant **calculée automatiquement** par le sensor `sensor.xxx_power_consumption` !

Le calcul utilise :
- Le **duty_cycle** (pourcentage de chauffe actif)
- La **puissance nominale** extraite du modèle (ex: DLRIRFH1800 = 1800W)

Formule : `Consommation (W) = (duty_cycle / 100) × puissance_nominale`

### Intégration dans le tableau de bord énergie

Pour suivre l'énergie consommée, créez un sensor d'intégration dans `configuration.yaml` :

```yaml
sensor:
  - platform: integration
    source: sensor.xxx_power_consumption
    name: "Chauffage XXX Energy"
    unit_prefix: k
    round: 2
    method: left
```

Ce sensor peut ensuite être ajouté au **tableau de bord énergie** de Home Assistant.

## 🐛 Dépannage

### Les entités n'apparaissent pas
1. Vérifiez que l'intégration est bien activée dans **Paramètres** → **Appareils et services**
2. Consultez les logs : **Paramètres** → **Système** → **Journaux**
3. Redémarrez Home Assistant

### Erreur 401 (Unauthorized) ou mot de passe changé
- Le token est automatiquement rafraîchi, attendez 1 minute
- Si le mot de passe est refusé, Home Assistant affiche une notification **Réauthentification requise** dans **Paramètres** → **Appareils et services** : saisissez le nouveau mot de passe, l'intégration se recharge toute seule

### L'intégration indique « Nouvelle tentative de configuration »
- Le cloud GoodHome est injoignable : Home Assistant réessaie automatiquement, aucune action n'est nécessaire

### Les modifications ne sont pas prises en compte
- Le radiateur met de 45 s à 2 min à appliquer une commande (mesuré sur l'API réelle) : ce délai vient du radiateur, pas de l'intégration. Pendant ce temps, Home Assistant affiche la nouvelle valeur ; si le radiateur ne l'a pas confirmée au bout de 3 minutes, la valeur réelle réapparaît et un avertissement est écrit dans les journaux
- Vérifiez la connectivité de vos radiateurs
- Les radiateurs envoient leurs mesures au cloud quand elles changent : une valeur qui ne bouge pas est simplement stable. Il n'existe aucun moyen de forcer une remontée (le ping de `goodhome.identify_device` ne fait que biper)

## 📝 Logs

Pour activer les logs de debug (temporairement) :

```yaml
logger:
  default: info
  logs:
    custom_components.goodhome: debug
```

## 🤝 Contribution

Les contributions sont les bienvenues ! N'hésitez pas à :
- Ouvrir une issue pour signaler un bug
- Proposer une pull request pour une amélioration
- Partager vos retours d'expérience

## 📄 Licence

Ce projet est sous licence MIT.

## 👏 Remerciements

- [ESPHome_GoodHome](https://github.com/Benichou34/ESPHome_GoodHome) pour la documentation de l'API
- La communauté Home Assistant

## 🔗 Liens utiles

- [Documentation Home Assistant](https://www.home-assistant.io/)
- [Forum Home Assistant](https://community.home-assistant.io/)
- [GoodHome (Kingfisher)](https://www.kingfisher.com/en/about-us/goodhome.html)

---

**Développé avec ❤️ pour la communauté Home Assistant**
