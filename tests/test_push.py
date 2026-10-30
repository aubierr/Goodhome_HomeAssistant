"""Tests de l'écoute temps réel (Socket.io)."""
import asyncio
from unittest.mock import AsyncMock, MagicMock

from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMockResponse

from custom_components.goodhome import push
from custom_components.goodhome.push import GoodHomePushClient, parse_payload

from .conftest import DEVICE_ID, HANDSHAKE, SOCKETIO_URL, USER_ID, entity_id

REPORT = '42["report",{"objectType":"device","objectId":"%s","data":{"currentTemp":21.5}}]' % DEVICE_ID


def _packets(*packets):
    """Réponse Engine.IO contenant ces paquets."""
    return "".join(f"{len(packet)}:{packet}" for packet in packets)


def _socketio(aioclient_mock, *responses):
    """Réponses successives du serveur, puis plus rien (requête en attente)."""
    remaining = list(responses)

    async def side_effect(method, url, data):
        if method.upper() == "POST" or not remaining:
            await asyncio.Event().wait()
        return AiohttpClientMockResponse(method, url, text=remaining.pop(0))

    aioclient_mock.get(SOCKETIO_URL, side_effect=side_effect)


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

    push_client = GoodHomePushClient(async_get_clientsession(hass), _client(), on_event)
    task = asyncio.create_task(push_client.run())
    await asyncio.wait_for(received.wait(), timeout=5)

    # État de l'écoute pour les diagnostics
    assert push_client.connected
    assert push_client.connections == 1
    assert push_client.last_event is not None
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


async def test_push_client_reconnects_after_unexpected_error(hass, aioclient_mock, monkeypatch, caplog):
    """Une réponse inattendue (ici sans sid) n'arrête pas l'écoute : elle se reconnecte."""
    monkeypatch.setattr(push, "RECONNECT_MIN_DELAY", 0)
    _socketio(aioclient_mock, _packets('0{"pingInterval":25000}'), HANDSHAKE, _packets(REPORT))
    received = asyncio.Event()

    push_client = GoodHomePushClient(async_get_clientsession(hass), _client(), lambda *a: received.set())
    task = asyncio.create_task(push_client.run())
    await asyncio.wait_for(received.wait(), timeout=5)
    task.cancel()

    assert "unexpected error" in caplog.text
    # La première session n'a pas abouti ; sa cause reste visible dans les diagnostics
    assert push_client.connections == 1
    assert "KeyError" in push_client.last_error


async def test_event_handler_error_keeps_session(hass, aioclient_mock, caplog):
    """Une erreur en traitant un événement ne coupe pas la session : les suivants arrivent."""
    second = REPORT.replace("21.5", "22")
    _socketio(aioclient_mock, HANDSHAKE, _packets(REPORT, second))
    received = asyncio.Event()
    temperatures = []

    def on_event(name, payload):
        if payload["data"]["currentTemp"] == 21.5:
            raise RuntimeError("entity error")
        temperatures.append(payload["data"]["currentTemp"])
        received.set()

    task = asyncio.create_task(GoodHomePushClient(async_get_clientsession(hass), _client(), on_event).run())
    await asyncio.wait_for(received.wait(), timeout=5)
    await asyncio.sleep(0)
    task.cancel()

    assert temperatures == [22]
    # Une seule poignée de main : la session n'a pas été refaite
    assert sum("sid=" not in str(call[1]) for call in aioclient_mock.mock_calls) == 1
    assert "entity error" in caplog.text
