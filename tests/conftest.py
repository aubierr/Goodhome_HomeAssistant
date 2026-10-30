"""Fixtures communes aux tests GoodHome."""
import copy
import socket
import sys
from unittest.mock import AsyncMock, patch

import pytest

# Importer notre paquet en premier : sinon Home Assistant trouve celui du dossier
# de test de pytest-homeassistant-custom-component et ne voit pas goodhome
import custom_components  # noqa: F401
from custom_components.goodhome.const import DOMAIN
from custom_components.goodhome.goodhome_api import BASE_URL
from pytest_homeassistant_custom_component.common import MockConfigEntry

EMAIL = "user@example.com"
PASSWORD = "secret"
USER_ID = "user-1"
DEVICE_ID = "device-1"

LOGIN_URL = f"{BASE_URL}/v1/auth/login"
REFRESH_URL = f"{BASE_URL}/v1/auth/refresh"
DEVICES_URL = f"{BASE_URL}/v1/users/{USER_ID}/devices"
STATE_URL = f"{BASE_URL}/v1/devices/{DEVICE_ID}/state"
SOCKETIO_URL = f"{BASE_URL}/socket.io-v2/"
_OPEN = '0{"sid":"sid-1","upgrades":[],"pingInterval":25000,"pingTimeout":60000}'
HANDSHAKE = f"{len(_OPEN)}:{_OPEN}2:40"

# État réel d'un radiateur (identifiants remplacés)
DEVICE_STATE = {
    "HwVer": "0001",
    "antifTemp": 7,
    "codeName": "DLRIRDH1000",
    "comfTemp": 19,
    "currentTemp": 19.6,
    "dutyCycle": 40,
    "ecoTemp": 16,
    "faultSystem": 0,
    "fwVer": "01206.3 TO100",
    "humidity": 58.2,
    "noprog": False,
    "occupancyStatus": True,
    "overrideTemp": 18.5,
    "roomName": "CUISINE",
    "selfLearning": False,
    "selfLearningCountDay": 0,
    "selfLearningImprove": False,
    "targetMode": 60,
    "targetTemp": 19,
    "userHash": "home-1",
    "window": True,
    "windowTimeOut": 15,
}
DEVICES_RESPONSE = {
    "devices": [
        {"_id": DEVICE_ID, "name": "CUISINE", "type": "thermostat", "connected": True, "state": DEVICE_STATE}
    ]
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Charger custom_components/goodhome dans chaque test."""
    yield


@pytest.fixture(autouse=True)
def no_push():
    """Pas d'écoute temps réel par défaut (les événements sont testés à part)."""
    # Seulement la classe utilisée par __init__.py : push.py reste testable tel quel
    with patch("custom_components.goodhome.GoodHomePushClient") as push_client:
        push_client.return_value.run = AsyncMock()
        yield push_client


@pytest.fixture
def config_entry():
    """Compte GoodHome configuré."""
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id=EMAIL,
        title=f"GoodHome ({EMAIL})",
        data={"email": EMAIL, "password": PASSWORD},
    )


def register_api(aioclient_mock, connected=True, command_status=200, **state_changes):
    """Simuler l'API GoodHome : connexion, liste des radiateurs et commandes."""
    devices = copy.deepcopy(DEVICES_RESPONSE)
    devices["devices"][0]["connected"] = connected
    devices["devices"][0]["state"].update(state_changes)
    aioclient_mock.post(LOGIN_URL, json={"token": "token-1", "id": USER_ID, "refresh_token": "refresh-1"})
    aioclient_mock.get(DEVICES_URL, json=devices)
    aioclient_mock.get(SOCKETIO_URL, text=HANDSHAKE)
    aioclient_mock.patch(STATE_URL, status=command_status, json={})
    return aioclient_mock


async def async_setup_entry_with(hass, config_entry, aioclient_mock, connected=True, command_status=200, **state_changes):
    """Charger l'intégration avec un radiateur dans l'état voulu."""
    register_api(aioclient_mock, connected, command_status, **state_changes)
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()


@pytest.fixture
def mock_api(aioclient_mock):
    """API GoodHome simulée avec l'état réel du radiateur."""
    return register_api(aioclient_mock)


@pytest.fixture
async def setup_integration(hass, config_entry, mock_api):
    """Intégration chargée avec un radiateur."""
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry


def entity_id(hass, platform, unique_id):
    """Identifiant d'entité à partir de son unique_id (inchangé depuis la v1)."""
    from homeassistant.helpers import entity_registry as er

    found = er.async_get(hass).async_get_entity_id(platform, DOMAIN, unique_id)
    assert found, f"{platform} {unique_id} absent"
    return found


def sent_parameters(aioclient_mock):
    """Paramètres de toutes les commandes PATCH envoyées."""
    return [call[2]["parameters"] for call in aioclient_mock.mock_calls if call[0].upper() == "PATCH"]


if sys.platform == "win32":
    # Sous Windows, la boucle asyncio crée une paire de sockets locale pour se
    # réveiller, ce que pytest-socket bloque. On la crée avec la vraie classe
    # socket ; le reste du réseau reste bloqué et les appels HTTP simulés.
    _real_socket = socket.socket

    def _local_socketpair(family=socket.AF_INET, type=socket.SOCK_STREAM, proto=0):
        with _real_socket(family, type, proto) as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            client = _real_socket(family, type, proto)
            client.connect(listener.getsockname())
            fd, _ = listener._accept()  # accept() recréerait le socket avec la classe bloquée
            server = _real_socket(family, type, proto, fileno=fd)
        return server, client

    socket.socketpair = _local_socketpair

    # aiodns (résolveur DNS d'aiohttp) exige une boucle Selector sous Windows
    import asyncio

    from homeassistant import runner

    runner.HassEventLoopPolicy._loop_factory = asyncio.SelectorEventLoop
