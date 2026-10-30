"""Tests du client API GoodHome."""
import aiohttp
import pytest
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMockResponse

from custom_components.goodhome.goodhome_api import GoodHomeAuthError, GoodHomeClient

from .conftest import (
    DEVICE_ID,
    DEVICES_RESPONSE,
    DEVICES_URL,
    LOGIN_URL,
    REFRESH_URL,
    SOCKETIO_URL,
    STATE_URL,
    USER_ID,
)


async def _logged_in_client(hass, aioclient_mock):
    aioclient_mock.post(LOGIN_URL, json={"token": "token-1", "id": USER_ID, "refresh_token": "refresh-1"})
    client = GoodHomeClient(async_get_clientsession(hass), "user@example.com", "secret")
    await client.async_login()
    return client


def _sequence(*responses):
    """Réponses successives d'une même URL : (statut, json, en-têtes)."""
    remaining = list(responses)

    async def side_effect(method, url, data):
        status, json, headers = remaining.pop(0)
        return AiohttpClientMockResponse(method, url, status=status, json=json, headers=headers)

    return side_effect


async def test_rejected_login(hass, aioclient_mock):
    aioclient_mock.post(LOGIN_URL, status=400)
    client = GoodHomeClient(async_get_clientsession(hass), "user@example.com", "wrong")
    with pytest.raises(GoodHomeAuthError):
        await client.async_login()


async def test_devices_are_cached_with_etag(hass, aioclient_mock):
    client = await _logged_in_client(hass, aioclient_mock)
    aioclient_mock.get(
        DEVICES_URL,
        side_effect=_sequence((200, DEVICES_RESPONSE, {"ETag": '"v1"'}), (304, None, {})),
    )

    first = await client.async_get_devices()
    second = await client.async_get_devices()

    assert list(first) == [DEVICE_ID]
    assert first[DEVICE_ID]["state"]["codeName"] == "DLRIRDH1000"
    assert second is first
    # La seconde lecture demande « seulement si modifié »
    assert aioclient_mock.mock_calls[-1][3]["If-None-Match"] == '"v1"'


async def test_expired_token_is_renewed_once(hass, aioclient_mock):
    client = await _logged_in_client(hass, aioclient_mock)
    aioclient_mock.post(REFRESH_URL, json={"token": "token-2"})
    aioclient_mock.get(DEVICES_URL, side_effect=_sequence((401, None, {}), (200, DEVICES_RESPONSE, {})))

    devices = await client.async_get_devices()

    assert list(devices) == [DEVICE_ID]
    assert client.token == "token-2"
    assert aioclient_mock.mock_calls[-1][3]["access-token"] == "token-2"


async def test_token_still_refused_raises(hass, aioclient_mock):
    client = await _logged_in_client(hass, aioclient_mock)
    aioclient_mock.post(REFRESH_URL, json={"token": "token-2"})
    aioclient_mock.get(DEVICES_URL, status=401)
    with pytest.raises(GoodHomeAuthError):
        await client.async_get_devices()


@pytest.mark.parametrize("socketio", [{"status": 503}, {"exc": aiohttp.ClientError()}])
async def test_command_is_sent_when_socketio_handshake_fails(hass, aioclient_mock, socketio):
    """La poignée de main ne fait qu'accélérer la commande : son échec ne l'empêche pas."""
    client = await _logged_in_client(hass, aioclient_mock)
    aioclient_mock.get(SOCKETIO_URL, **socketio)
    aioclient_mock.patch(STATE_URL, json={})

    await client.async_set_state(DEVICE_ID, {"targetMode": 9})

    assert aioclient_mock.mock_calls[-1][0].upper() == "PATCH"
    assert aioclient_mock.mock_calls[-1][2] == {"parameters": {"targetMode": 9}}
