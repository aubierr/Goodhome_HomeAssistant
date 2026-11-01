"""Constantes de l'intégration GoodHome."""

DOMAIN = "goodhome"

# Mode de connexion d'une entrée : compte cloud (par défaut, entrées d'avant la v2.2) ou Bluetooth local
CONF_CONNECTION = "connection"
CONNECTION_CLOUD = "cloud"
CONNECTION_LOCAL = "local"
# Entrée locale : un radiateur appairé
CONF_ADDRESS = "address"  # Adresse Bluetooth fixe, connue après l'appairage
CONF_SERIAL = "serial"  # Numéro de série (identifiant du radiateur)
CONF_BLE_NAME = "ble_name"  # Nom Bluetooth avant appairage (GOODHOME-XXXX)

UPDATE_INTERVAL = 30  # Intervalle de relecture de l'API, en secours de l'écoute temps réel (secondes)
DEBOUNCE_DELAY = 3  # Délai avant d'envoyer la commande de température (secondes)
# Le radiateur applique une commande en 45 s à 2 min (mesuré sur l'API réelle)
CONFIRMATION_TIMEOUT = 180  # Attente maximale de la confirmation d'une commande (secondes)

# Modes automatiques : envoyer 60 ou 61 passe le radiateur en automatique, puis c'est son
# planning qui choisit confort (60) ou éco (61), ou 30 s'il ne détecte personne (observé sur l'API réelle)
AUTO_MODES = {30, 60, 61}
