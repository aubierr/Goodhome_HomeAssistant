"""Constantes de l'intégration GoodHome."""

DOMAIN = "goodhome"

UPDATE_INTERVAL = 30  # Intervalle de relecture de l'API, en secours de l'écoute temps réel (secondes)
DEBOUNCE_DELAY = 3  # Délai avant d'envoyer la commande de température (secondes)
# Le radiateur applique une commande en 45 s à 2 min (mesuré sur l'API réelle)
CONFIRMATION_TIMEOUT = 180  # Attente maximale de la confirmation d'une commande (secondes)
