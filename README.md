# GoodHome Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
![Version](https://img.shields.io/badge/version-2.1.1-blue.svg)
![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2025.1+-brightgreen.svg)

Intégration Home Assistant complète pour les radiateurs connectés **GoodHome** (marque Kingfisher - Castorama/Brico Dépôt).

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=aubierr&repository=Goodhome_HomeAssistant&category=integration)
[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=goodhome)

Deux modes de connexion, au choix à l'ajout de l'intégration :
- ☁️ **Compte GoodHome (cloud)** : vos identifiants de l'application, tous les radiateurs du compte d'un coup. Aucun matériel en plus.
- 📶 **Bluetooth local** : sans compte ni cloud, chaque radiateur appairé directement à Home Assistant. Il faut un adaptateur Bluetooth (ou un proxy Bluetooth ESPHome) à portée des radiateurs.

## 📋 Fonctionnalités

### Plateformes supportées
- ✅ **Climate** - Contrôle complet du thermostat avec attribut `eco_reason`
- ✅ **Sensor** - Température, humidité, puissance, consommation, jours d'apprentissage
- ✅ **Binary Sensor** - Connectivité, problèmes, auto-apprentissage
- ✅ **Switch** - Détection fenêtre ouverte, présence, auto-apprentissage, mode manuel
- ✅ **Select** - Sélection des modes targetMode (14 modes)
- ✅ **Number** - Réglage des températures confort, éco et hors-gel
- ✅ **Button** - Identification (fait biper le radiateur)

### Caractéristiques principales
- 📶 Mode Bluetooth local : lecture et pilotage sans cloud, commandes confirmées en une dizaine de secondes, radiateurs détectés automatiquement
- 🔐 Mode cloud : authentification par email/password avec refresh token automatique
- ⚙️ Client entièrement asynchrone (session HTTP de Home Assistant)
- 🩺 Diagnostics téléchargeables, sans identifiants ni noms de pièces
- 🚀 Cache HTTP 304 Not Modified pour optimiser les performances
- ⚡ Mises à jour en temps réel via Socket.io (réglages et mesures), relecture de l'API toutes les 30 s en secours ; en local, les changements faits sur le radiateur arrivent par notification Bluetooth
- 🔄 État optimiste : la nouvelle valeur s'affiche tout de suite et reste affichée jusqu'à la confirmation du radiateur (3 min max)
- 🌐 Support complet de l'API GoodHome officielle
- 🎯 100% compatible avec le projet ESPHome_GoodHome
- 🌍 Interface en français, anglais, espagnol, polonais, portugais et roumain
- ⚙️ Configuration via interface utilisateur (config flow)
- 📊 Calcul automatique de la consommation électrique
- 🎓 Suivi de la période d'apprentissage (14 jours)
- 🏠 Détection automatique d'absence avec mode éco

## 📦 Installation

### Pré-requis

- Home Assistant **2025.1** ou plus récent (testé de la 2025.1 à la dernière version)
- **Mode cloud** : vos radiateurs doivent être connectés au cloud GoodHome, depuis l'application mobile officielle **GoodHome** (Android et iOS).
- **Mode Bluetooth local** : l'intégration **Bluetooth** de Home Assistant doit avoir un adaptateur capable de se connecter, ou un [proxy Bluetooth ESPHome](https://esphome.io/projects/?type=bluetooth) avec les connexions actives (`active: true`), à portée des radiateurs (même pièce ou pièce voisine). Il faut aussi pouvoir mettre le radiateur en mode appairage depuis ses boutons. Ce mode a été testé avec Home Assistant OS ; l'appairage passe par BlueZ (Linux).

### Via HACS (recommandé)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=aubierr&repository=Goodhome_HomeAssistant&category=integration)

1. Cliquez sur le bouton ci-dessus : HACS s'ouvre sur la page de l'intégration GoodHome dans votre Home Assistant (acceptez l'ajout du dépôt personnalisé si HACS le demande)
2. Cliquez sur **Télécharger**, puis redémarrez Home Assistant
3. Ajoutez l'intégration :

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=goodhome)

Sans le bouton : dans HACS, menu **⋮** → **Dépôts personnalisés**, ajoutez `https://github.com/aubierr/Goodhome_HomeAssistant` (type **Intégration**), puis recherchez **GoodHome**.

### Installation manuelle

1. Téléchargez la [dernière version](https://github.com/aubierr/Goodhome_HomeAssistant/releases/latest) et copiez son dossier `custom_components/goodhome` dans le dossier `custom_components` de Home Assistant (à créer s'il n'existe pas, à côté de `configuration.yaml`)
2. Redémarrez Home Assistant

## ⚙️ Configuration

### Via l'interface utilisateur (recommandé)

1. Cliquez sur le bouton **Ajouter l'intégration** en haut de cette page, ou allez dans **Paramètres** → **Appareils et services** → **Ajouter une intégration** et recherchez **GoodHome**
2. Choisissez le mode de connexion :
   - **Compte GoodHome (cloud)** : entrez vos identifiants GoodHome (email et mot de passe). Tous les radiateurs du compte apparaissent automatiquement.
   - **Bluetooth local (adaptateur nécessaire)** : voir ci-dessous.

Les deux modes peuvent cohabiter. Un même radiateur ajouté dans les deux modes apparaît alors deux fois : désactivez l'entrée dont vous ne voulez plus.

### Ajouter un radiateur en Bluetooth local

1. **Mettez d'abord le radiateur en mode appairage**, comme dans l'application GoodHome : sur le radiateur, appuyez sur **Réglages** (engrenage), puis **Connexion**, puis **Ajouter**. Un radiateur n'annonce son nom Bluetooth (`GOODHOME-XXXX`) qu'en mode appairage.
2. Choisissez le radiateur dans la liste, sous son nom. Tant qu'aucun radiateur n'y apparaît, attendez quelques secondes et cliquez sur **Valider** pour relancer la recherche. Un radiateur déjà appairé à Home Assistant apparaît sous son nom suivi de son adresse.
   Un radiateur en mode appairage peut aussi être **détecté automatiquement** : une carte « GOODHOME-XXXX » apparaît dans **Découvertes**, et il suffit de cliquer sur **Ajouter**. Si vous ignorez la carte, elle ne revient pas : passez alors par **Ajouter une intégration**. Après la suppression d'un radiateur, elle revient dès qu'il est remis en mode appairage.
3. Sur l'écran **Appairer GOODHOME-XXXX**, cliquez tout de suite sur **Valider**. L'appairage prend jusqu'à une minute. Si le mode appairage s'est arrêté entre-temps, refaites les 3 étapes sur le radiateur juste avant.
4. Le radiateur est ajouté sous le nom de sa pièce (ex. « GoodHome CUISINE »), avec les mêmes entités qu'en mode cloud.

Chaque radiateur est une entrée séparée : répétez l'opération pour chacun. Le détail du protocole est dans [docs/BLUETOOTH.md](docs/BLUETOOTH.md).

### Ancienne configuration YAML

La configuration par `configuration.yaml` n'est plus prise en charge depuis la version 2.0. Si votre fichier contient encore un bloc `goodhome:` avec `email` et `password`, il est importé automatiquement dans l'interface au démarrage, et une alerte vous invite à retirer le bloc. Les configurations par `user_id`/`token` ne peuvent pas être importées : ajoutez le compte depuis l'interface.

## 📱 Entités créées

Pour chaque thermostat GoodHome, les entités suivantes sont créées, dans les deux modes. Les identifiants indiqués sont ceux d'une nouvelle installation, où `xxx` est le nom du radiateur ; une installation mise à jour depuis la version 1 garde ses identifiants d'origine.

En **Bluetooth local**, le radiateur ne transmet ni sa version matérielle ni son code défaut : la version matérielle s'affiche « Unknown », et `binary_sensor.xxx_problem` reste toujours à « OK ». Vérifié sur un vrai radiateur en Bluetooth : mesures, températures de consigne, passage en chauffage manuel et retour au planning. Le bouton Identifier est accepté par le radiateur, mais son bip n'a pas été confirmé.

En local, un mode manuel permanent (Manuel Confort, Éco, Hors-gel, consigne libre) coupe le planning du radiateur (`switch.xxx_manual_mode` passe à « activé »), et le retour en `auto` le rallume : sans cela, le radiateur reprendrait son planning au bout de quelques secondes. Les forçages provisoires et l'absence ne touchent pas au planning.

### Climate
- `climate.xxx` - Contrôle du thermostat
  - Température cible
  - Modes HVAC :
    - `auto` : le radiateur suit son planning (modes 60, 61 et 30, ainsi que les forçages 9 et 10 qui durent jusqu'au créneau suivant). Choisir `auto` envoie le mode 60, puis le planning choisit confort ou éco
    - `heat` : mode manuel (choisir `heat` envoie Manuel Confort)
    - `off` : hors-gel manuel
  - `climate.turn_off` arrête le radiateur ; `climate.turn_on` le rallume dans son mode d'avant l'arrêt : le planning, ou le même mode manuel (Confort, Éco ou consigne libre). Sans mode connu (radiateur arrêté avant le démarrage de Home Assistant), il repasse en Manuel Confort. Sur un radiateur déjà allumé, `turn_on` ne change rien
  - Action en cours (`hvac_action`) : `heating` quand le radiateur chauffe (duty cycle > 0), `idle` sinon
  - Presets (Confort, Éco, Manuel, Absence, Absence courte `sleep`)
  - Attributs étendus :
    - `eco_reason` : `manual` / `absence` / `schedule` / `null`
    - `self_learning_days` : Progression de l'apprentissage (0-14)
    - `temperature_range` : `cold` / `medium` / `hot`
    - `temperature_color` : Code couleur pour l'interface
    - `target_mode_value` : valeur brute du mode (`targetMode`), utile car plusieurs modes donnent le même mode HVAC et le même preset
    - `pending_confirmation` : valeurs envoyées que le radiateur n'a pas encore confirmées (présent seulement pendant l'attente, aussi sur le select, les switches et les numbers)

### Sensors
- `sensor.xxx_current_temperature` - Température actuelle
- `sensor.xxx_target_temperature` - Température cible
- `sensor.xxx_humidity` - Humidité
- `sensor.xxx_heating_power` - Cycle de chauffe (%)
- `sensor.xxx_power_consumption` - Consommation électrique calculée (W)
- `sensor.xxx_comfort_temperature` / `eco_temperature` / `frost_protection_temperature` - Températures confort, éco et hors-gel (doublons des entités Number, désactivés par défaut sur les nouvelles installations)
- `sensor.xxx_self_learning_days` - Jours d'apprentissage (0-14)
- `sensor.xxx_device_information` - Informations appareil (diagnostic). Son attribut `other_fields` liste les champs envoyés par l'API qu'aucune entité n'exploite encore (nouveau firmware, nouveau modèle...)

### Binary Sensors
- `binary_sensor.xxx_connectivity` - État de connexion
- `binary_sensor.xxx_self_learning_improvement` - Amélioration auto-apprentissage
- `binary_sensor.xxx_problem` - Détection de problème

### Switches
Réglages du radiateur, rangés dans la section **Configuration** de l'appareil.

- `switch.xxx_open_window_detection` - Détection fenêtre ouverte
- `switch.xxx_presence_detection` - Détection de présence
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
Rangés dans la section **Configuration** de l'appareil.

- `number.xxx_comfort_temperature` - Température confort (7-30°C, pas de 0.5°C)
- `number.xxx_eco_temperature` - Température éco (7-30°C, pas de 0.5°C)
- `number.xxx_frost_protection_temperature` - Température hors-gel (7-30°C, pas de 0.5°C)

### Button
- `button.xxx_identify` - Fait biper le radiateur pour le localiser

### Appareil
Chaque thermostat apparaît comme un appareil avec son modèle (`codeName`, ex. `DLRIRFH1800`), sa version de firmware et sa version matérielle.

- **Nouveau radiateur** : en mode cloud, un radiateur ajouté dans l'app GoodHome apparaît automatiquement dans Home Assistant à la mise à jour suivante (30 s maximum), sans redémarrage. En mode local, ajoutez-le comme indiqué plus haut.
- **Radiateur retiré** : ses entités passent en « indisponible ». En mode cloud, pour le supprimer, ouvrez l'appareil dans **Paramètres** → **Appareils et services** → **GoodHome**, puis **⋮** → **Supprimer**. La suppression n'est proposée que pour un radiateur qui n'existe plus dans le compte GoodHome. En mode local, supprimer l'appareil supprime aussi son entrée (elle ne contient que ce radiateur) ; il peut ensuite être ajouté à nouveau, sans redémarrage.

### Service `goodhome.identify_device`
Fait biper un thermostat pour le localiser (le bouton Identifier fait la même chose). Dans l'éditeur d'automatisations, choisissez le radiateur dans la liste des appareils. L'identifiant GoodHome (attribut `device_id` du sensor Informations appareil) des anciennes automatisations reste accepté.

```yaml
action: goodhome.identify_device
data:
  device_id: "5f1e2d3c4b5a69788796a5b4"  # appareil Home Assistant ou identifiant GoodHome
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

### Bluetooth local

Le mode local parle au radiateur en Bluetooth Low Energy, comme l'application GoodHome Connect quand le téléphone est à portée : service `0xF0`, messages JSON dans des trames `___` découpées en morceaux de 20 octets, valeurs en dixièmes et en texte. L'intégration convertit ces valeurs vers le format de l'API cloud, ce qui permet de garder les mêmes entités dans les deux modes. Détails, exemples de messages et limites connues : [docs/BLUETOOTH.md](docs/BLUETOOTH.md).

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
- Mode cloud : le cloud GoodHome est injoignable. Home Assistant réessaie automatiquement, aucune action n'est nécessaire
- Mode local : le radiateur n'a pas répondu en Bluetooth, en général parce qu'il est trop loin de l'adaptateur. Home Assistant réessaie automatiquement. Si cela se répète, rapprochez l'adaptateur (une rallonge USB suffit souvent) ou ajoutez un [proxy Bluetooth ESPHome](https://esphome.io/projects/?type=bluetooth) près du radiateur. Vers −80 dBm, la première connexion peut prendre près d'une minute

### Bluetooth local : le radiateur n'apparaît pas ou l'appairage échoue
- **« Aucun adaptateur Bluetooth ne peut se connecter à un radiateur »** : l'intégration **Bluetooth** de Home Assistant n'a aucun adaptateur, ou seulement des proxys ESPHome en écoute passive. Ajoutez un adaptateur, ou activez les connexions du proxy (`active: true`), puis cliquez sur Valider
- **« Aucun radiateur en mode appairage pour l'instant »** : mettez le radiateur en mode appairage (Réglages → Connexion → Ajouter), attendez quelques secondes, puis cliquez sur Valider. Une recherche Bluetooth active est lancée pour aider un radiateur éloigné à apparaître. Un radiateur déjà ajouté n'est plus proposé
- **Un radiateur éloigné (vers −80 dBm) n'arrive pas à s'appairer** : ses annonces n'arrivent pas assez souvent. Rapprochez l'adaptateur Bluetooth (une rallonge USB suffit souvent) ou ajoutez un proxy Bluetooth ESPHome près du radiateur (l'appairage à travers un proxy n'a pas encore été testé, voir [docs/BLUETOOTH.md](docs/BLUETOOTH.md))
- **« Le radiateur a refusé l'appairage »** : il n'était pas en mode appairage. Refaites les 3 étapes sur le radiateur (Réglages → Connexion → Ajouter), puis cliquez tout de suite sur Valider
- **« Le radiateur n'est plus visible en Bluetooth »** : il est éteint ou trop loin. Sur les versions récentes de Home Assistant, les journaux indiquent pourquoi (récepteurs qui l'ont entendu, signal, connexions occupées)
- **« L'appairage a échoué (…) »** : le détail technique est entre parenthèses. Un ancien appairage raté est oublié automatiquement à chaque essai : refaites simplement les 3 étapes et réessayez
- Un radiateur appairé auparavant à un autre ordinateur (Windows, Linux) peut être retiré de cet ordinateur, pour éviter les conflits

### Les modifications ne sont pas prises en compte
- En mode cloud, le radiateur met de 45 s à 2 min à appliquer une commande (mesuré sur l'API réelle) : ce délai vient du radiateur, pas de l'intégration. En Bluetooth local, la confirmation arrive en une dizaine de secondes. Pendant ce temps, Home Assistant affiche la nouvelle valeur, et l'attribut `pending_confirmation` liste ce qui attend la confirmation ; si le radiateur ne l'a pas confirmée au bout de 3 minutes, la valeur réelle réapparaît et un avertissement est écrit dans les journaux
- Vérifiez la connectivité de vos radiateurs
- Les radiateurs envoient leurs mesures au cloud quand elles changent : une valeur qui ne bouge pas est simplement stable. Il n'existe aucun moyen de forcer une remontée (le ping de `goodhome.identify_device` ne fait que biper)
- Si une commande est refusée par le cloud, l'action Home Assistant échoue avec le message d'erreur, et l'ancienne valeur réapparaît

### Joindre un diagnostic à un rapport de bug
Ouvrez l'intégration dans **Paramètres** → **Appareils et services** → **GoodHome**, puis **⋮** → **Télécharger les diagnostics**. Le fichier contient le mode de connexion (`connection` : `cloud` ou `local`) et les réglages et mesures des radiateurs, sans email, mot de passe, identifiants, noms de pièces, adresse Bluetooth, numéro de série ni nom du Wi-Fi. En mode cloud, il contient aussi l'état de l'écoute temps réel (`push` : connectée ou non, nombre de connexions, date du dernier événement, dernière erreur).

## 📝 Logs

Pour activer les logs de debug (temporairement) :

```yaml
logger:
  default: info
  logs:
    custom_components.goodhome: debug
```

## 🤝 Contribution

### Tests

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv -r requirements_test.txt
.venv/Scripts/python -m pytest --cov=custom_components.goodhome   # Windows ; .venv/bin/python sous Linux
```

Les tests utilisent un vrai Home Assistant avec une API GoodHome simulée. Avec les versions figées de `requirements_test.txt` (Home Assistant 2025.1), ils fonctionnent sous Linux comme sous Windows ; les versions plus récentes de Home Assistant ne s'exécutent plus sous Windows. Sur GitHub Actions, ils tournent avec la 2025.1 et avec la dernière version, en plus des validations hassfest et HACS.

Les contributions sont les bienvenues ! N'hésitez pas à :
- Ouvrir une issue pour signaler un bug
- Proposer une pull request pour une amélioration
- Partager vos retours d'expérience

## 📄 Licence

Ce projet est sous licence MIT.

## 👏 Remerciements

- [K0n3k/Goodhome_HomeAssistant](https://github.com/K0n3k/Goodhome_HomeAssistant), l'intégration d'origine dont cette version est issue
- [ESPHome_GoodHome](https://github.com/Benichou34/ESPHome_GoodHome) pour la documentation de l'API et du format des trames, le même en série et en Bluetooth
- La communauté Home Assistant

## 🔗 Liens utiles

- [Documentation Home Assistant](https://www.home-assistant.io/)
- [Forum Home Assistant](https://community.home-assistant.io/)
- [GoodHome (Kingfisher)](https://www.kingfisher.com/en/about-us/goodhome.html)

---

**Développé avec ❤️ pour la communauté Home Assistant**
