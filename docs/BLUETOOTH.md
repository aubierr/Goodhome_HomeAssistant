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

Le radiateur ne s'annonce sous son nom `GOODHOME-XXXX` qu'**en mode appairage**, avec une adresse aléatoire. Le reste du temps, il s'annonce sans nom : sous une adresse aléatoire qui change régulièrement, ou sous son **adresse fixe** (publique) une fois appairé à l'appareil qui l'écoute. Un radiateur hors mode appairage ne peut donc pas être reconnu avant d'avoir été appairé.

## Appairage

Le radiateur coupe toute connexion qui ne s'appaire pas **pendant la découverte des services**. L'appairage doit donc être demandé dès la connexion (`pair=True` dans Bleak).

1. Mettre le radiateur en mode appairage, comme dans l'application : sur le radiateur, **Réglage**, puis **Connexion**, **Ajouter un mobile**, **Nouveau mobile** et enfin **Suivant**.
2. Se connecter en demandant l'appairage. Le radiateur demande une **confirmation** (BlueZ : « request type 2 », `RequestConfirmation`), sans code à saisir.
3. Sous Linux, BlueZ annule l'appairage s'il n'y a pas d'agent pour répondre (`No agent available for request type 2`, puis `AuthenticationCanceled`). L'intégration enregistre un agent BlueZ le temps de l'appairage : il accepte la confirmation pour ce radiateur seulement et refuse tout autre appareil.
4. Après l'appairage, le radiateur s'annonce sous son adresse fixe. Les connexions suivantes se font sans appairage, à cette adresse.

Un appairage raté laisse côté BlueZ une clé que le radiateur n'a plus : tout nouvel essai échoue alors avec `br-connection-key-missing` (ou une erreur GATT « Unlikely Error »). L'intégration oublie donc tout appairage précédent du radiateur avant d'appairer, et recommence une fois si une clé périmée apparaît pendant l'essai.

Pièges rencontrés pendant l'appairage, tous gérés par l'intégration :
- **Le nom gardé par BlueZ** : BlueZ attache le nom d'un appareil déjà appairé (`GOODHOME-XXXX`) à toutes ses annonces, y compris celles relayées à Home Assistant sous l'ancienne adresse fixe. Après l'oubli de l'ancien appairage, seules comptent donc les annonces reçues après l'oubli, et jamais à l'adresse oubliée.
- **L'adresse figée par Bleak** : Bleak range chaque appareil BlueZ sous l'adresse vue la première fois et ne la met pas à jour. Juste après l'appairage, c'est l'adresse aléatoire du mode appairage, alors que BlueZ est passé à l'adresse fixe. Home Assistant range alors les annonces sous l'ancienne adresse et répond « no scanner currently has it in its discovered devices » pour l'adresse fixe, jusqu'à son redémarrage. L'intégration reconnaît ces annonces à l'adresse BlueZ jointe à chacune (`platform_data`) et se connecte par l'entrée de Bleak, qui pointe vers le bon chemin BlueZ.
- **Le chemin BlueZ** : le chemin D-Bus d'un appareil appairé (`/org/bluez/hci0/dev_…`) reste celui de l'adresse aléatoire de l'appairage ; seule la propriété `Address` passe à l'adresse fixe.

### À travers un proxy Bluetooth ESPHome

Vérifié sur un vrai radiateur avec ESPHome 2026.10.2 (firmware `esp32-generic` des proxys Bluetooth). L'appairage et la clé sont alors gardés par l'ESP32, pas par BlueZ : le radiateur liste l'ESP32 parmi ses appareils appairés, sous son adresse Bluetooth (ex. `C88541687342`).

- **Réglage de l'ESP32** : `esp32_ble: io_capability: none` (valeur par défaut). Avec `display_yes_no`, le radiateur demande une confirmation que le firmware ESPHome n'envoie jamais : le chiffrement ne se termine pas et le radiateur ne répond à rien.
- **Appairage après la connexion** : `pair=True` n'arrive pas jusqu'au proxy (la connexion reste non chiffrée). L'intégration se connecte sans appairer, puis demande l'appairage (`pair()`).
- **Clé gardée par l'ESP32** : comme BlueZ, l'ESP32 garde la clé d'un essai précédent, que le radiateur n'a plus si l'appareil a été retiré de sa liste. L'intégration l'oublie (`unpair()`) avant d'appairer. L'ESP32 coupe alors la connexion sans que Bleak le voie tout de suite : appairer aussitôt échoue avec l'erreur 102, l'intégration se reconnecte donc d'abord.
- **Chiffrement tardif** : à travers un proxy, le chiffrement se termine plusieurs secondes après la connexion, et le radiateur ignore les messages reçus avant. Après un appairage comme à chaque reconnexion, l'intégration renvoie donc sa première demande (`system.get_network_status`) pendant 30 s, en refaisant l'abonnement aux notifications entre deux envois.
- **Choix du proxy** : Home Assistant passe par le récepteur qui a entendu le radiateur, même faiblement (−94 dBm constaté) quand il est le seul à avoir capté la nouvelle adresse du mode appairage. Pour appairer, débrancher les proxys trop lointains, ou viser −80 dBm ou mieux.
- **Après un redémarrage de Home Assistant** : un radiateur connecté ne s'annonce pas, Home Assistant n'en garde donc aucune trace, et l'adresse notée à l'appairage n'est plus forcément la sienne. « never seen by any scanner » ne veut alors pas dire que le radiateur est absent. L'intégration le reconnaît aussi à son nom `GOODHOME-XXXX`, jamais au service GoodHome, commun à tous les radiateurs. Ce nom n'arrive pas toujours en écoute passive : un proxy en mode `auto` (par défaut) reste passif, et sa première recherche active automatique n'a lieu que 4 minutes après son démarrage. L'intégration demande donc une recherche active chaque fois qu'elle attend le radiateur pour se connecter.
- **Radiateur bloqué** : après plusieurs essais ratés, le radiateur peut continuer à s'annoncer tout en refusant les connexions (`Connection open failed, status=133`). Couper son alimentation 30 s le remet en état.

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

Chaque trame de données reçue est acquittée par un ACK qui recopie son compteur. Le radiateur acquitte de même chaque commande. Si le checksum d'une trame reçue est faux, l'application répond par un NACK (relevé dans `verifyChecksum` et `onReceiveChunckJSON`) ; l'intégration fait de même et ignore le message.

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

### Changer de mode

Un `targetMode` envoyé seul est acquitté mais **pas appliqué** : le cloud complète la commande de lui-même, pas le radiateur. Comme l'application, l'intégration y ajoute `targetTemp` et `overrideTemp`, égales à la température du nouveau mode, et, constaté sur un vrai radiateur, l'état du planning (`noprog`) :

| Mode | Températures envoyées | `noprog` |
|------|----------------------|----------|
| 1 Manuel Confort | `comfTemp` | `1` (planning coupé) |
| 2 Manuel Éco | `ecoTemp` | `1` |
| 3 Manuel Hors-gel | `antifTemp` | `1` |
| 8 Consigne libre | `overrideTemp` | `1` |
| 60 / 61 Retour au planning | `comfTemp` / `ecoTemp` | `0` (planning rallumé) |
| 9 / 10 / 12 Forçages provisoires | `comfTemp` / `ecoTemp` | inchangé |
| 5 Absence longue | `0` | inchangé |
| 4 Consigne provisoire | `overrideTemp` | inchangé |

Sans `noprog`, un radiateur dont le planning est actif passe bien en mode 1, puis repasse en 60 quelques secondes plus tard et l'annonce par un `ble_set_attr` spontané. À l'inverse, remettre `noprog` à `0` suffit pour que le radiateur reprenne son planning de lui-même.

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

## Aides du Bluetooth de Home Assistant

D'après le [guide Bluetooth de Home Assistant](https://contributors.home-assistant.io/core/integrations/bluetooth/), l'intégration s'appuie sur ces fonctions :

- **Aucun adaptateur capable de se connecter** : avant de chercher les radiateurs, `bluetooth.async_scanner_count(hass, connectable=True)` est vérifié. À 0 (pas d'adaptateur, ou seulement des proxys en écoute passive), l'ajout affiche une erreur claire au lieu d'une liste vide ; Valider revérifie.
- **Redécouverte après suppression** : le Bluetooth de Home Assistant ne propose un appareil qu'une fois par adresse. À la suppression d'une entrée locale, `bluetooth.async_rediscover_address` est appelé pour son adresse fixe et pour les adresses où son nom `GOODHOME-XXXX` est visible : la carte « Découvertes » revient sans redémarrage quand le radiateur est remis en mode appairage.
- **Recherche active** : quand aucun radiateur n'est encore visible en mode appairage, et pendant l'attente d'une annonce lors de l'appairage, `bluetooth.async_request_active_scan` est demandé en tâche de fond, pour qu'un radiateur lointain, entendu rarement, apparaisse plus vite. Cette fonction est récente : absente (Home Assistant plus ancien), rien n'est fait.
- **Erreur expliquée** : quand le radiateur n'est pas vu à temps ou que la connexion échoue, l'explication de `bluetooth.async_address_reachability_diagnostics` (intention `CONNECTION` : récepteurs qui l'ont vu, signal, emplacements de connexion occupés) est ajoutée au message d'erreur, visible dans le journal et dans le détail des entrées en échec. Fonction récente elle aussi : absente, le message reste le même. Son texte n'est jamais analysé, il peut changer d'une version à l'autre.

Le Bluetooth de Home Assistant n'est importé qu'à l'intérieur des fonctions de `ble_client.py`, pour ne pas l'imposer au mode cloud. Ces quatre points sont couverts par des tests avec un Bluetooth simulé, pas encore vérifiés sur de vrais radiateurs.

## Limites connues

- **Portée** : le Bluetooth Low Energy porte à une pièce ou deux. Vers −80 dBm, les annonces du radiateur n'arrivent que de temps en temps : la connexion peut demander plusieurs essais, et l'appairage peut échouer faute d'annonce récente en mode appairage (constaté sur un radiateur à −80 dBm). Rapprocher l'adaptateur, ou un [proxy Bluetooth ESPHome](https://esphome.io/projects/?type=bluetooth) près des radiateurs, règle ce problème (voir [À travers un proxy Bluetooth ESPHome](#à-travers-un-proxy-bluetooth-esphome)).
- **Une connexion par radiateur** : chaque radiateur est une entrée séparée. Le radiateur coupe les connexions inactives ; l'intégration se reconnecte à l'opération suivante.
- **Vérifié sur un vrai radiateur** : lecture de tous les attributs, températures de consigne, passage en chauffage manuel et retour au planning (confirmés en une dizaine de secondes), changements faits sur le radiateur reçus aussitôt.
- **Partiellement vérifié** : le bouton Identifier (`ping`) est acquitté par le radiateur, mais son bip n'a pas été confirmé.
- **Programmation horaire et mises à jour du firmware** : non prises en charge.
- **Appairage hors Linux** : l'agent d'appairage passe par BlueZ (D-Bus). Sans BlueZ (Home Assistant sous Windows ou macOS), l'appairage n'est géré qu'à travers un proxy ESPHome.
- **Un proxy par radiateur** : la clé est gardée par l'ESP32 qui a appairé le radiateur. Un autre ESP32, ou l'adaptateur de Home Assistant, ne peut pas s'y connecter sans nouvel appairage.

## Pistes d'amélioration

Relevées dans la documentation de Home Assistant et des bibliothèques Bluetooth, à valider sur de vrais radiateurs :

- **Dépendance `bluetooth_adapters`** dans le manifeste, recommandée par Home Assistant pour les intégrations Bluetooth ([guide Bluetooth](https://contributors.home-assistant.io/core/integrations/bluetooth/)). Elle imposerait le Bluetooth aux utilisateurs du mode cloud : à peser.
- **`ble_device_callback`** de bleak-retry-connector n'est plus appelé dans les versions récentes ([documentation](https://bleak-retry-connector.readthedocs.io/en/latest/usage.html), constaté dans la 4.7.1) : l'intégration ne l'utilise plus et passe directement l'appareil le plus récent.
- **Proxy choisi pour un radiateur appairé** : Home Assistant choisit le récepteur au signal, sans savoir lequel garde la clé. Avec plusieurs proxys à portée d'un même radiateur, une connexion peut passer par un ESP32 non appairé : à surveiller.
- **Nom affiché par le radiateur** : un ESP32 apparaît sous son adresse. L'application nomme le téléphone avec `system.bluetooth_set_mobile_device_name` ; l'intégration envoie désormais « Home Assistant » juste après l'appairage, au mieux (erreur ignorée). Format relevé dans le code de l'application GoodHome Connect 2.1.4 (décompilée), **pas encore vérifié sur un radiateur** : `{"type": "command", "cmdName": "system.bluetooth_set_mobile_device_name", "cmdID": "…", "params": "Home Assistant"}`, `params` étant le nom lui-même (une chaîne), sans identifiant de mobile. Le radiateur nomme l'appareil connecté. L'intégration lit `system.bluetooth_get_paired_devices` avant et après, dans le journal (niveau info), pour le vérifier.
