# 🎯 Modes des radiateurs GoodHome

Ce document liste tous les modes de fonctionnement connus d'un radiateur GoodHome, tels qu'ils apparaissent dans le champ `targetMode` de l'API, et la façon dont l'intégration Home Assistant les lit et les envoie.

Sources :
- le code de l'intégration ([select.py](../custom_components/goodhome/select.py), [climate.py](../custom_components/goodhome/climate.py), [goodhome_api.py](../custom_components/goodhome/goodhome_api.py)) ;
- le projet de référence [ESPHome_GoodHome](https://github.com/Benichou34/ESPHome_GoodHome), qui documente les modes dans `GoodHome.yaml` et les associe aux modes/presets climate dans `components/GoodHome/climate/climate.cpp`.

## Températures de consigne

Chaque mode fait chauffer le radiateur vers l'une de ces températures (champ `targetTemp` de l'API) :

| Champ API | Entité Home Assistant | Rôle |
|-----------|-----------------------|------|
| `comfTemp` | `number.xxx_comfort_temperature` | Confort, périodes de présence |
| `ecoTemp` | `number.xxx_eco_temperature` | Économie, périodes d'absence et absence courte |
| `antifTemp` | `number.xxx_frost_protection_temperature` | Hors-gel, OFF et absence longue |
| `overrideTemp` | consigne de `climate.xxx` | Consigne libre (« override ») |

## Liste des modes `targetMode`

| Valeur | Option du select | Famille | Consigne | Fin du mode |
|:------:|------------------|---------|----------|-------------|
| 0 | `default` — Par défaut | Provisoire | défaut | Retour au mode par défaut à la remise sous tension |
| 1 | `manual_comfort` — Manuel Confort | Manuel | `comfTemp` (ou réglage depuis l'écran) | Aucune |
| 2 | `manual_eco` — Manuel Éco | Manuel | `ecoTemp` | Aucune |
| 3 | `manual_frost` — Manuel Hors-gel (= OFF) | Manuel | `antifTemp` | Aucune |
| 4 | `temporary_override` — Override provisoire | Provisoire | `overrideTemp` | Retour au mode par défaut |
| 5 | `long_absence` — Absence longue | Absence | `antifTemp` | `holidayTimeout` |
| 8 | `override` — Manuel Override | Manuel | `overrideTemp` | Aucune |
| 9 | `forced_comfort` — Forcé Confort | Auto, forçage | `comfTemp` | Prochaine période du planning |
| 10 | `forced_eco` — Forcé Éco | Auto, forçage | `ecoTemp` | Prochaine période du planning |
| 12 | `short_absence` — Absence courte | Absence | `ecoTemp` | `overrideTime` |
| 30 | `eco_auto_absence` — Éco auto (absence), lecture seule | Auto, présence | `ecoTemp` | Retour de présence |
| 60 | `auto_comfort` — Auto Confort | Auto, planning | `comfTemp` | Période suivante |
| 61 | `auto_eco` — Auto Éco | Auto, planning | `ecoTemp` | Période suivante |
| 70 | `manual` — Manuel | Manuel | ? | ? |

Les valeurs 6, 7, 11 et 13 à 29 n'apparaissent dans aucune source. Une valeur inconnue met le select à l'état « inconnu » ; la valeur brute reste lisible dans son attribut `target_mode_value`.

### Détail par famille

**Manuel (1, 2, 3, 8, 70).** Le radiateur garde la même consigne jusqu'au prochain changement. Le 3 (hors-gel) correspond à l'arrêt : c'est ce qu'envoie `climate.turn_off`. Le 8 est envoyé automatiquement dès qu'on change la température du `climate` : l'API reçoit `overrideTemp` + `targetMode: 8`.

**Provisoire (0, 4).** Mode temporaire, abandonné à la remise sous tension. Le 4 est la version provisoire de l'override (8). Il a été observé via l'API cloud sur un radiateur réel (`targetMode` 4, `targetTemp` 7).

**Forçage (9, 10).** Le planning automatique reste actif ; la consigne forcée ne dure que jusqu'au prochain créneau. C'est ce qu'envoient les presets `comfort` et `eco` du `climate`.

**Absence (5, 12).**
- 5, absence longue (vacances) : hors-gel jusqu'à la date `holidayTimeout`. Envoyé par le preset `away`.
- 12, absence courte : éco pendant `overrideTime`. Envoyé par le preset `sleep`.

**Automatique (30, 60, 61).** Le radiateur choisit lui-même la consigne à partir de son planning ou de l'auto-apprentissage :
- envoyer 60 ou 61 passe le radiateur en automatique, mais c'est son planning qui choisit ensuite : « Auto Éco » demandé en période de confort donne 60 (observé sur l'API réelle). L'intégration considère donc ces deux choix confirmés dès que le radiateur est en 30, 60 ou 61 ;
- 60 / 61 : période de présence (confort) ou d'absence (éco) du planning ;
- 30 : passage en éco quand le détecteur ne voit personne pendant environ 20 minutes, retour dès qu'une présence est détectée. Le radiateur le gère seul : le select l'affiche mais refuse de le sélectionner. La référence ESPHome laisse ce mode sans description ; ce comportement vient de l'observation.

**70.** Valeur observée sur des radiateurs récents, absente de la référence ESPHome. Sa consigne et sa fin ne sont pas documentées.

## Réglages qui influencent le mode

Ces interrupteurs ne sont pas des valeurs de `targetMode`, mais ils changent la façon dont le radiateur choisit son mode :

| Champ API | Entité | Effet |
|-----------|--------|-------|
| `noprog` | `switch.xxx_manual_mode` | Activé : mode manuel, pas de planning. Désactivé : planning auto (modes 9/10/60/61). |
| `selfLearning` | `switch.xxx_self_learning` | Auto-apprentissage du planning (exige `occupancyStatus`). `selfLearningImprove` indique la fin de l'apprentissage. |
| `occupancyStatus` | `switch.xxx_presence_detection` | Prise en compte du détecteur de présence (mode 30). |
| `window` | `switch.xxx_open_window_detection` | Coupe la chauffe pendant `windowTimeOut` minutes quand une fenêtre ouverte est détectée. Pas de valeur `targetMode` dédiée. |

## Correspondance avec l'entité `climate`

### Lecture (`targetMode` → Home Assistant)

| `targetMode` | `hvac_mode` | `preset_mode` | attribut `eco_reason` |
|:------------:|:-----------:|:-------------:|:---------------------:|
| 0 | heat | manual | — |
| 1 | heat | manual | — |
| 2 | heat | eco | `manual` |
| 3 | off | manual | — |
| 4 | heat | manual | — |
| 5 | heat | away | — |
| 8 | heat | manual | — |
| 9 | auto | comfort | — |
| 10 | auto | eco | — |
| 12 | heat | sleep | — |
| 30 | auto | eco | `absence` |
| 60 | auto | comfort | — |
| 61 | auto | eco | `schedule` |
| 70 | heat | manual | — |

Une valeur inconnue donne `heat` + `manual`. `auto` couvre les modes où le planning est actif : 30, 60 et 61, et les forçages 9 et 10, qui ne durent que jusqu'au créneau suivant. L'attribut `target_mode_value` du `climate` donne la valeur brute.

### Écriture (Home Assistant → `targetMode`)

| Action | `targetMode` envoyé |
|--------|:-------------------:|
| `climate.turn_off` / `hvac_mode: off` | 3 |
| `hvac_mode: heat` | 1 |
| `hvac_mode: auto` | 60 (confirmé par 30, 60 ou 61 : c'est le planning qui choisit) |
| `climate.turn_on` | le mode d'avant l'arrêt : 60 s'il suivait le planning (30, 60, 61, 9 ou 10), le même mode s'il était en 1, 2 ou 8, sinon 1 ; rien si le radiateur est déjà allumé |
| `climate.set_temperature` | 8 (+ `overrideTemp`) |
| preset `comfort` | 9 |
| preset `eco` | 10 |
| preset `manual` | 1 |
| preset `away` | 5 |
| preset `sleep` | 12 |
| `select.xxx_target_mode` | la valeur choisie (14 options, sauf 30 en lecture seule) |

### Comparaison avec ESPHome_GoodHome

ESPHome expose trois modes (`off`, `heat` = manuel, `auto` = planning) et utilise `sleep` pour l'absence courte. Sa correspondance en écriture :

| Preset | En `heat` (manuel) | En `auto` (planning) |
|--------|:------------------:|:--------------------:|
| aucun | 8 | 0 |
| comfort | 1 | 9 |
| eco | 2 | 10 |
| away | 5 | 5 |
| sleep | 12 | 12 |
| home / activity | 0 | 0 |

En lecture, ESPHome classe 2 (et 10, 61) en `eco`, et 12 en `sleep`. Il affiche `auto` + `home` quand l'auto-apprentissage est actif et `auto` + `activity` quand seul le détecteur de présence l'est.

## Points restant à confirmer

- **Mode 70** : absent de la référence ESPHome ; sa consigne et sa fin restent à vérifier sur un radiateur réel.
- **Mode 30** : la référence ne le décrit pas. Le comportement documenté vient de l'observation, et on ignore si l'API l'accepte en écriture (d'où le refus côté select).
