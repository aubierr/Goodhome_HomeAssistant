"""Tests de l'écoute temps réel (Socket.io)."""
import asyncio
from unittest.mock import AsyncMock, MagicMock

from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMockResponse

from custom_components.goodhome.push import GoodHomePushClient, parse_payload

from .conftest import DEVICE_ID, HANDSHAKE, SOCKETIO_URL, USER_ID, entity_id

REPORT = '42["report",{"objectType":"device","objectId":"%s","data":{"currentTemp":21.5}}]' % DEVICE_ID


def test_parse_payload():
    packets = ['0{"sid":"a"}', "40", '42["report",{"data":{"a":1}}]', "3"]
    assert parse_payload("".join(f"{len(p)}:{p}" for p in packets)) == packets


async def test_report_event_updates_measurements(hass, setup_integration):
    coordinator = setup_integration.runtime_data.coordinator
    sensor = entity_id(hass, "sensor", f"goodhome_{DEVICE_ID}_temperature")

    coordinator.async_apply_push_event(
        "report", {"objectType": "device", "objectId": DEVICE_ID, "data": {"currentTemp": 21.5}}
    )
    await hass.async_block_till_done()
    assert hass.states.get(sensor).state == "21.5"


async def test_irrelevant_events_are_ignored(hass, setup_integration):
    coordinator = setup_integration.runtime_data.coordinator
    before = coordinator.data
    coordinator.async_apply_push_event("other", {"objectType": "device", "objectId": DEVICE_ID, "data": {"x": 1}})
    coordinator.async_apply_push_event("report", {"objectType": "device", "objectId": "unknown", "data": {"x": 1}})
    coordinator.async_apply_push_event("report", None)
    assert coordinator.data is before


def _client(token="token-1"):
    client = MagicMock(user_id=USER_ID, token=token)
    client.async_renew_token = AsyncMock()
    return client


async def test_push_client_forwards_events(hass, aioclient_mock):
    """Poignée de main, puis un événement, puis plus rien (requête en attente)."""
    responses = [HANDSHAKE, f"{len(REPORT)}:{REPORT}"]

    async def socketio(method, url, data):
        if method.upper() == "POST" or not responses:
            await asyncio.Event().wait()
        return AiohttpClientMockResponse(method, url, text=responses.pop(0))

    aioclient_mock.get(SOCKETIO_URL, side_effect=socketio)
    received = asyncio.Event()
    events = []

    def on_event(name, payload):
        events.append((name, payload["data"]))
        received.set()

    task = asyncio.create_task(GoodHomePushClient(async_get_clientsession(hass), _client(), on_event).run())
    await asyncio.wait_for(received.wait(), timeout=5)
    task.cancel()

    assert events == [("report", {"currentTemp": 21.5})]
    # Le token est envoyé à la poignée de main
    assert aioclient_mock.mock_calls[0][3]["authorization"] == "Bearer token-1"


async def test_push_client_renews_refused_token(hass, aioclient_mock):
    renewed = asyncio.Event()
    client = _client()
    client.async_renew_token = AsyncMock(side_effect=lambda token: renewed.set())
    aioclient_mock.get(SOCKETIO_URL, status=401)

    task = asyncio.create_task(GoodHomePushClient(async_get_clientsession(hass), client, lambda *a: None).run())
    await asyncio.wait_for(renewed.wait(), timeout=5)
    task.cancel()

    client.async_renew_token.assert_awaited_once_with("token-1")
