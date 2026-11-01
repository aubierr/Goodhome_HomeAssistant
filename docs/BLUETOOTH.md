# 📶 Protocole Bluetooth local des radiateurs GoodHome

Ce document décrit le protocole Bluetooth Low Energy utilisé par l'application **GoodHome Connect** pour piloter un radiateur sans passer par le cloud, et la façon dont l'intégration Home Assistant l'utilise en mode local.

Sources :
- l'application Android GoodHome Connect (React Native, bytecode Hermes), décompilée : modules `com.imh.ble` (transport) et fonctions `buildCommand`, `buildACK`, `computeChecksum`, `formatCommand`, `sendSetAttributeCommand`, `sendGetAttributeCommand` ;
- le projet [ESPHome_GoodHome](https://github.com/Benichou34/ESPHome_GoodHome), qui documente le même format de trames sur la liaison série interne du radiateur (`SerialExchange.cpp`) ;
- des essais sur deux vrais radiateurs (firmware `01206.3 TO100`, dont un modèle `DLRIRFH1000`).

Le code de l'intégration : [ble.py](../custom_components/goodhome/ble.py) (trames et conversions), [ble_client.py](../custom_components/goodhome/ble_client.py) (connexion), [ble_agent.py](../custom_components/goodhome/ble_agent.py) (appairage BlueZ).

## Service GATT

| Élément | UUID | Propriétés | Rôle |
|---------|------|------------|------|
| Service | `000000f0-0000-1000-8000-00805f9b34fb` | | Service GoodHome, annoncé par le radiateur |
| Écriture | `000000f1-0000-1000-8000-00805f9b34fb` | write-without-response | Commandes vers le radiateur |
| Réception | `000000f2-0000-1000-8000-00805f9b34fb` | notify | Réponses et changements envoyés par le radiateur |

Le radiateur s'annonce sous le nom `GOODHOME-XXXX`, avec une adresse aléatoire qui change régulièrement. Une fois appairé, il s'annonce sous son **adresse fixe** (publique), souvent sans son nom.

## Appairage

Le radiateur coupe toute connexion qui ne s'appaire pas **pendant la découverte des services**. L'appairage doit donc être demandé dès la connexion (`pair=True` dans Bleak).

1. Mettre le radiateur en mode appairage, comme dans l'application : sur le radiateur, **Réglages** (engrenage), puis **Connexion**, puis **Ajouter**. Dans le code de l'application, ces étapes correspondent aux icônes `settings`, `connection` et `add_heater`.
2. Se connecter en demandant l'appairage. Le radiateur demande une **confirmation** (BlueZ : « request type 2 », `RequestConfirmation`), sans code à saisir.
3. Sous Linux, BlueZ annule l'appairage s'il n'y a pas d'agent pour répondre (`No agent available for request type 2`, puis `AuthenticationCanceled`). L'intégration enregistre un agent BlueZ le temps de l'appairage : il accepte la confirmation pour ce radiateur seulement et refuse tout autre appareil.
4. Après l'appairage, le radiateur s'annonce sous son adresse fixe. Les connexions suivantes se font sans appairage, à cette adresse.

Un appairage raté laisse côté BlueZ une clé que le radiateur n'a plus : tout nouvel essai échoue alors avec `br-connection-key-missing` (ou une erreur GATT « Unlikely Error »). L'intégration oublie donc tout appairage précédent du radiateur avant d'appairer, et recommence une fois si une clé périmée apparaît pendant l'essai.

Le radiateur garde la liste des appareils appairés (`bluetoothPaired`, voir plus bas). Appairer Home Assistant n'a pas retiré le téléphone déjà appairé lors des essais.

## Format des trames

Toutes les trames commencent par `___` (`5F 5F 5F`).

### Trame de données

```
5F 5F 5F | 00 | compteur (2 o) | longueur (3 o) | JSON | 00 | checksum (2 o)
```

- **Type** `00` : données.
- **Compteur** : sur 2 octets, gros-boutiste. L'application envoie toujours `00 01`.
- **Longueur** : sur 3 octets, gros-boutiste ; elle compte le JSON **et** le `00` final.
- **Checksum** : calculé sur le JSON seul (sans le `00`) :
  - 1er octet : somme pondérée par la position, `Σ octet[i] × (i + 1)`, modulo 256 ;
  - 2e octet : somme simple des octets, modulo 256.

### Accusés de réception

```
5F 5F 5F | 01 | compteur (2 o)     ACK
5F 5F 5F | 02 | compteur (2 o)     NACK
```

Chaque trame de données reçue est acquittée par un ACK qui recopie son compteur. Le radiateur acquitte de même chaque commande.

### Découpage

L'application écrit les trames **par morceaux de 20 octets** (MTU Android par défaut), un par un, en écriture sans réponse. Les notifications du radiateur arrivent aussi en plusieurs morceaux : il faut les recoller avant de décoder (le premier message reçu lors des essais faisait 542 octets).

## Commandes

### Commandes système (module Bluetooth du radiateur)

```json
{"type": "command", "cmdName": "system.get_network_status", "cmdID": "1"}
```

| `cmdName` | Réponse |
|-----------|---------|
| `system.get_network_status` | État du module : `moduleID`, `firmwareVersion`, `wifiConnected`, `bluetoothOpen` (mode appairage), `bluetoothPaired`, `bluetoothConnected`... |
| `system.bluetooth_get_paired_devices` | Appareils appairés : `{"mobile.XXXXXXXXXXXX": "iPhone", ...}` |
| `system.bluetooth_set_mobile_device_name` | Nom de l'appareil appairé (utilisé par l'application, pas par l'intégration) |

La réponse est un message `"type": "return"` avec le même `cmdID`. Elle porte aussi deux identifiants utiles pour la suite :
- `srcID` : `module.<numéro de série>`, le radiateur ;
- `dstID` : l'identifiant que le radiateur attribue à l'appareil connecté (ex. `mobile.000000000000`).

Exemple réel (identifiants remplacés) :

```json
{
  "type": "return", "cmdName": "system.get_network_status", "cmdID": "1",
  "srcID": "module.0000AB000001", "dstID": "mobile.000000000000",
  "params": {
    "moduleID": "module.0000AB000001", "firmwareVersion": "6.3 TO100",
    "wifiConnected": true, "bluetoothOpen": false,
    "bluetoothPaired": ["mobile.000000000001", "mobile.000000000000"],
    "bluetoothConnected": ["mobile.000000000000"]
  }
}
```

### Lire et modifier les attributs du radiateur

Les attributs passent par `system.send_to_host`, adressé à `host.<numéro de série>` :

```json
{
  "type": "command", "cmdName": "system.send_to_host", "cmdID": "3",
  "hostID": "host.0000AB000001",
  "params": {
    "cmdName": "ble_get_attr", "srcID": "mobile.000000000000",
    "request": {"method": "getAttr", "value": ["roomName", "currentTemp", "targetMode", "..."]}
  }
}
```

- **Lecture** (`ble_get_attr` / `getAttr`) : `value` est la **liste des attributs voulus** (une liste vide ne renvoie rien). Le radiateur répond par un `return` vide, puis envoie les valeurs dans **plusieurs messages** `ble_set_attr` :

  ```json
  {"cmdName": "ble_set_attr", "srcID": "host.0000AB000001",
   "request": {"method": "setAttr", "value": {"currentTemp": "190", "humidity": "635", "window": "1"}}}
  ```

- **Modification** (`ble_set_attr` / `setAttr`) : `value` contient les attributs à changer, encodés comme ci-dessous. Le radiateur applique le changement en quelques secondes ; une relecture le confirme en une dizaine de secondes (45 s à 2 min par le cloud).
- **Changements spontanés** : quand un réglage change sur le radiateur, il envoie de lui-même un message `ble_set_attr` à l'appareil connecté.
- `ble_get_prog` / `ble_set_prog` (programmation horaire) et `ble_ota` (mise à jour du firmware) existent aussi ; l'intégration ne les utilise pas.

Liste des attributs demandés par l'application à chaque relecture : `networkId`, `roomID`, `roomName`, `roomType`, `deviceSN`, `model`, `fwVer`, `antifTemp`, `comfTemp`, `ecoTemp`, `holidayTimeout`, `noprog`, `occupancyStatus`, `daylightSaving`, `overrideTemp`, `overrideTime`, `selfLearningCountDay`, `selfLearning`, `selfLearningImprove`, `dutyCycle`, `targetTemp`, `currentTemp`, `targetMode`, `humidity`, `ctnAdjust`, `language`, `window`, `windowTimeOut`, `codeName`, `codeId`, `localTime`, `ssid`.

## Encodage des valeurs

Toutes les valeurs voyagent **en texte**. L'intégration les convertit vers le format de l'API cloud, pour que les entités fonctionnent de la même façon dans les deux modes.

| Attributs | Bluetooth | API cloud | Exemple |
|-----------|-----------|-----------|---------|
| Nom contenant `Temp`, `humidity`, `ctnAdjust` | dixièmes | nombre | `"185"` ↔ `18.5` |
| `window`, `occupancyStatus`, `selfLearning`, `selfLearningImprove`, `noprog`, `daylightSaving` | `"0"` / `"1"` | booléen | `"1"` ↔ `true` |
| `roomName`, `roomID`, `deviceSN`, `fwVer`, `codeName`, `model`, `ssid`, `networkId` | texte | texte | inchangé |
| Autres (`targetMode`, `dutyCycle`, `windowTimeOut`...) | entier en texte | entier | `"60"` ↔ `60` |

Particularités :
- le radiateur renvoie `windowTimeout` pour l'attribut demandé `windowTimeOut` ;
- les modes (`targetMode`) ont les mêmes valeurs qu'en cloud (voir [MODES.md](MODES.md)) ;
- la version matérielle (`HwVer`) et le code défaut (`faultSystem`) de l'API cloud ne font pas partie des attributs lus en Bluetooth.

## Limites connues

- **Portée** : le Bluetooth Low Energy porte à une pièce ou deux. Vers −80 dBm, les annonces du radiateur n'arrivent que de temps en temps et la connexion peut demander plusieurs essais. Un [proxy Bluetooth ESPHome](https://esphome.io/projects/?type=bluetooth) près des radiateurs règle ce problème.
- **Une connexion par radiateur** : chaque radiateur est une entrée séparée. Le radiateur coupe les connexions inactives ; l'intégration se reconnecte à l'opération suivante.
- **Non vérifié sur un vrai radiateur en Bluetooth** : le bouton Identifier (`ping`), et les changements de mode depuis le thermostat ou le select. Ils utilisent le même `setAttr` que les températures, vérifié lui.
- **Programmation horaire et mises à jour du firmware** : non prises en charge.
