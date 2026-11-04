"""Tests du client Bluetooth local, face à un radiateur simulé."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.goodhome.ble import FrameDecoder, build_frame, split_chunks
from custom_components.goodhome.ble_client import GoodHomeBleClient, GoodHomeBleError
from custom_components.goodhome.const import (
    CONF_ADDRESS,
    CONF_BLE_NAME,
    CONF_CONNECTION,
    CONF_SERIAL,
    CONNECTION_LOCAL,
    DOMAIN,
)

from .conftest import entity_id
from .test_ble import RADIATOR_VALUES

SERIAL = "0000AB000001"
ADDRESS = "00:00:AB:00:00:02"
SRC_ID = "mobile.000000000000"


class FakeRadiator:
    """Client Bleak simulé qui répond comme un vrai radiateur."""

    def __init__(self, values=None, answer=True):
        self.values = dict(values or RADIATOR_VALUES)
        self.answer = answer
        self.is_connected = True
        self.received = []
        self._notify = None
        self._decoder = FrameDecoder()

    async def start_notify(self, _uuid, callback):
        self._notify = callback

    async def disconnect(self):
        self.is_connected = False

    async def write_gatt_char(self, _uuid, data, response):
        assert response is False
        assert len(data) <= 20
        for frame in self._decoder.feed(bytes(data)):
            if frame.kind == 0:
                self.received.append(frame.message)
                if self.answer:
                    asyncio.get_running_loop().call_soon(self._respond, frame.message)

    def _send(self, message):
        for chunk in split_chunks(build_frame(message)):
            self._notify(None, bytearray(chunk))

    def push(self, values):
        """Changement envoyé de lui-même par le radiateur (ex. réglage sur le radiateur)."""
        self.values.update(values)
        self._send({"cmdName": "ble_set_attr", "srcID": f"host.{SERIAL}", "request": {"method": "setAttr", "value": values}})

    def _respond(self, message):
        reply = {"type": "return", "cmdName": message["cmdName"], "cmdID": message["cmdID"],
                 "srcID": f"module.{SERIAL}", "dstID": SRC_ID}
        self._send(reply)
        params = message.get("params") or {}
        if params.get("cmdName") == "ble_get_attr":
            # Comme le vrai radiateur : les attributs en deux messages
            items = list(self.values.items())
            for part in (dict(items[: len(items) // 2]), dict(items[len(items) // 2 :])):
                self._send({"cmdName": "ble_set_attr", "srcID": f"host.{SERIAL}",
                            "request": {"method": "setAttr", "value": part}})
        elif params.get("cmdName") == "ble_set_attr":
            self.values.update(params["request"]["value"])


@pytest.fixture(autouse=True)
def fast_timeouts():
    with (
        patch("custom_components.goodhome.ble_client.ATTRIBUTES_QUIET", 0.05),
        patch("custom_components.goodhome.ble_client.CHUNK_DELAY", 0),
        patch("custom_components.goodhome.ble_client.COMMAND_TIMEOUT", 0.5),
        patch("custom_components.goodhome.ble_client.ATTRIBUTES_TIMEOUT", 0.5),
    ):
        yield


@pytest.fixture
def radiator():
    """Radiateur simulé ; la connexion Bluetooth de Home Assistant est remplacée par lui."""
    fake = FakeRadiator()

    async def _connect(self):
        if self._client is None or not self._client.is_connected:
            fake.is_connected = True
            await self._async_start(fake)

    with patch.object(GoodHomeBleClient, "_async_ensure_connected", _connect):
        yield fake


async def test_read_attributes_in_cloud_format(hass, radiator):
    client = GoodHomeBleClient(hass, ADDRESS, SERIAL)
    devices = await client.async_get_devices()

    device = devices[SERIAL]
    assert device["name"] == "COULOIR"
    assert device["connected"] is True
    assert device["state"]["currentTemp"] == 19.0
    assert device["state"]["humidity"] == 63.5
    assert device["state"]["windowTimeOut"] == 15
    # Identifiants appris du radiateur, puis getAttr adressé à « host.<série> »
    assert radiator.received[0]["cmdName"] == "system.get_network_status"
    assert radiator.received[1]["hostID"] == f"host.{SERIAL}"
    assert radiator.received[1]["params"]["srcID"] == SRC_ID


async def test_serial_learned_when_unknown(hass, radiator):
    client = GoodHomeBleClient(hass, ADDRESS)
    devices = await client.async_get_devices()
    assert client.serial == SERIAL
    assert SERIAL in devices


async def test_set_state_converts_and_refreshes(hass, radiator):
    client = GoodHomeBleClient(hass, ADDRESS, SERIAL)
    updates = []
    client.on_update = updates.append
    await client.async_get_devices()

    await client.async_set_state(SERIAL, {"comfTemp": 20.5, "window": False})
    await hass.async_block_till_done(wait_background_tasks=True)

    sent = radiator.received[-2]  # setAttr, puis la relecture getAttr
    assert sent["params"]["cmdName"] == "ble_set_attr"
    assert sent["params"]["request"]["value"] == {"comfTemp": "205", "window": "0"}
    assert updates[-1][SERIAL]["state"]["comfTemp"] == 20.5
    assert updates[-1][SERIAL]["state"]["window"] is False


async def test_unsolicited_change_is_pushed(hass, radiator):
    client = GoodHomeBleClient(hass, ADDRESS, SERIAL)
    updates = []
    client.on_update = updates.append
    await client.async_get_devices()

    radiator.push({"currentTemp": "205"})
    assert updates[-1][SERIAL]["state"]["currentTemp"] == 20.5


async def test_no_answer_raises(hass, radiator):
    radiator.answer = False
    client = GoodHomeBleClient(hass, ADDRESS, SERIAL)
    with pytest.raises(GoodHomeBleError):
        await client.async_get_devices()


async def test_silent_radiator_gets_a_fresh_connection(hass, radiator):
    # Liaison restée ouverte mais radiateur muet : ne pas réutiliser une connexion sans poignée de main
    radiator.answer = False
    client = GoodHomeBleClient(hass, ADDRESS, SERIAL)
    with pytest.raises(GoodHomeBleError):
        await client.async_get_devices()
    assert radiator.is_connected is False

    radiator.answer = True
    radiator.received.clear()
    devices = await client.async_get_devices()
    assert devices[SERIAL]["connected"] is True
    assert radiator.received[0]["cmdName"] == "system.get_network_status"


async def test_failed_command_drops_the_connection(hass, radiator):
    client = GoodHomeBleClient(hass, ADDRESS, SERIAL)
    await client.async_get_devices()
    radiator.answer = False
    with pytest.raises(GoodHomeBleError):
        await client.async_set_state(SERIAL, {"comfTemp": 20.5})
    assert radiator.is_connected is False


async def test_late_disconnect_of_previous_connection_is_ignored(hass, radiator):
    client = GoodHomeBleClient(hass, ADDRESS, SERIAL)
    await client.async_get_devices()
    client._on_disconnect(FakeRadiator())
    assert client._client is radiator
    client._on_disconnect(radiator)
    assert client._client is None


async def test_local_entry_creates_entities(hass, radiator):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=SERIAL,
        title="GoodHome COULOIR",
        data={CONF_CONNECTION: CONNECTION_LOCAL, CONF_ADDRESS: ADDRESS, CONF_SERIAL: SERIAL,
              CONF_BLE_NAME: "GOODHOME-0001"},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data.push is None

    climate = hass.states.get(entity_id(hass, "climate", f"goodhome_climate_{SERIAL}"))
    assert climate.attributes["current_temperature"] == 19.0

    # Changement fait sur le radiateur : visible sans attendre la relecture
    radiator.push({"currentTemp": "212"})
    await hass.async_block_till_done()
    climate = hass.states.get(entity_id(hass, "climate", f"goodhome_climate_{SERIAL}"))
    assert climate.attributes["current_temperature"] == 21.2

    assert await hass.config_entries.async_unload(entry.entry_id)
    assert radiator.is_connected is False


async def test_local_entry_not_ready_when_out_of_range(hass, radiator):
    radiator.answer = False
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=SERIAL,
        data={CONF_CONNECTION: CONNECTION_LOCAL, CONF_ADDRESS: ADDRESS, CONF_SERIAL: SERIAL},
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY


def test_fake_radiator_is_json_serializable():
    # Garde-fou : les messages simulés sont du JSON valide, comme sur le vrai radiateur
    json.dumps(RADIATOR_VALUES)


async def test_local_diagnostics_hide_identifiers(hass, radiator):
    from custom_components.goodhome.diagnostics import async_get_config_entry_diagnostics

    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=SERIAL,
        data={CONF_CONNECTION: CONNECTION_LOCAL, CONF_ADDRESS: ADDRESS, CONF_SERIAL: SERIAL},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    assert diagnostics["connection"] == "local"
    assert diagnostics["push"] is None
    assert diagnostics["devices"][0]["state"]["currentTemp"] == 19.0
    text = str(diagnostics)
    for secret in (SERIAL, ADDRESS, "COULOIR"):
        assert secret not in text


async def test_pairing_retries_after_stale_key(hass):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from custom_components.goodhome import ble_client

    device = SimpleNamespace(address="11:22:33:44:55:66", name="GOODHOME-0001")
    paired = (ADDRESS, SERIAL, {"roomName": "COULOIR"})
    remove = AsyncMock(return_value=["4C:11:AE:00:00:01"])
    with (
        patch.object(ble_client, "_async_wait_device", AsyncMock(return_value=device)),
        patch.object(
            ble_client,
            "_async_pair_once",
            AsyncMock(side_effect=[GoodHomeBleError("[org.bluez.Error.Failed] br-connection-key-missing"), paired]),
        ) as pair_once,
        # dbus-fast n'existe que sous Linux : agent BlueZ simulé
        patch.dict("sys.modules", {"custom_components.goodhome.ble_agent": SimpleNamespace(async_remove_bonds=remove)}),
    ):
        assert await ble_client.async_pair_radiator(hass, device.address, device.name) == paired
    assert pair_once.await_count == 2
    # Oubli de l'ancien appairage avant le premier essai, puis de la clé périmée
    assert remove.await_count >= 2


async def test_pairing_rejected_is_not_retried(hass):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from custom_components.goodhome import ble_client

    device = SimpleNamespace(address="11:22:33:44:55:66", name="GOODHOME-0001")
    with (
        # Sous Linux, le vrai agent BlueZ passerait par D-Bus : oubli simulé
        patch.object(ble_client, "_async_forget", AsyncMock()),
        patch.object(ble_client, "_async_wait_device", AsyncMock(return_value=device)),
        patch.object(ble_client, "_async_pair_once", AsyncMock(side_effect=ble_client.GoodHomeBlePairingRejected("x"))) as pair_once,
        pytest.raises(ble_client.GoodHomeBlePairingRejected),
    ):
        await ble_client.async_pair_radiator(hass, device.address, device.name)
    assert pair_once.await_count == 1


async def test_wait_device_uses_the_advertised_name(hass):
    import time
    from types import SimpleNamespace

    from custom_components.goodhome import ble_client

    def info(address, advertised_name, age, device, bluez_name=None):
        return SimpleNamespace(
            address=address, name=bluez_name or advertised_name or address, time=time.monotonic() - age,
            advertisement=SimpleNamespace(local_name=advertised_name), device=device,
        )

    # Ancienne adresse fixe : BlueZ y garde le nom, mais l'annonce n'en contient pas (et elle est récente)
    identity = info("4C:11:AE:00:00:06", None, 2, "identity", bluez_name="GOODHOME-0006")
    # Mode appairage : nouvelle adresse aléatoire, nom dans l'annonce
    pairing = info("5D:60:48:00:00:99", "GOODHOME-0006", 1, "pairing")
    old_pairing = info("6E:00:00:00:00:01", "GOODHOME-0006", 43, "old")
    bluetooth = SimpleNamespace(async_discovered_service_info=lambda _hass, connectable: [identity, old_pairing, pairing])
    with patch.dict("sys.modules", {"homeassistant.components.bluetooth": bluetooth}), patch(
        "homeassistant.components.bluetooth", bluetooth, create=True
    ):
        # Appairage : le nom de l'annonce, jamais celui gardé par BlueZ
        assert await ble_client._async_wait_device(hass, identity.address, "GOODHOME-0006") == "pairing"
        # Radiateur appairé : son adresse fixe
        assert await ble_client._async_wait_device(hass, identity.address, None) == "identity"
        # Annonce trop ancienne : introuvable
        with pytest.raises(ble_client.GoodHomeBleNotFound):
            await ble_client._async_wait_device(hass, old_pairing.address, None, timeout=0)


async def test_paired_radiator_found_by_name_after_its_address_changed(hass):
    import time

    from custom_components.goodhome import ble_client

    # À travers un proxy ESPHome : adresse de l'appairage périmée, seule l'adresse actuelle s'annonce
    current = SimpleNamespace(
        address="55:AD:8C:00:00:2A", time=time.monotonic() - 1,
        advertisement=SimpleNamespace(local_name="GOODHOME-1FE9"), device="current",
    )
    other = SimpleNamespace(
        address="41:98:21:00:00:99", time=time.monotonic() - 1,
        advertisement=SimpleNamespace(local_name="GOODHOME-DFE5"), device="other",
    )
    bluetooth = SimpleNamespace(async_discovered_service_info=lambda _hass, connectable: [other, current])
    with patch.dict("sys.modules", {"homeassistant.components.bluetooth": bluetooth}), patch(
        "homeassistant.components.bluetooth", bluetooth, create=True
    ):
        found = await ble_client._async_wait_device(hass, "77:47:49:00:00:B0", None, also_named="GOODHOME-1FE9")
        assert found == "current"
        with pytest.raises(ble_client.GoodHomeBleNotFound):
            await ble_client._async_wait_device(hass, "77:47:49:00:00:B0", None, timeout=0)


async def test_mode_change_sent_with_temperatures(hass, radiator):
    client = GoodHomeBleClient(hass, ADDRESS, SERIAL)
    await client.async_get_devices()
    await client.async_set_state(SERIAL, {"targetMode": 1})
    await hass.async_block_till_done(wait_background_tasks=True)

    sent = next(m for m in radiator.received if m.get("params", {}).get("cmdName") == "ble_set_attr")
    # Confort à 18 °C dans RADIATOR_VALUES
    assert sent["params"]["request"]["value"] == {
        "targetMode": "1", "targetTemp": "180", "overrideTemp": "180", "noprog": "1",
    }


async def test_connects_through_bleak_entry_after_pairing(hass):
    import time
    from types import SimpleNamespace

    from custom_components.goodhome import ble_client

    fixed = "4C:11:AE:00:00:E6"
    now = time.monotonic()
    # Juste après l'appairage, Home Assistant range les annonces sous l'adresse aléatoire de
    # l'appairage ; l'adresse fixe n'apparaît que dans les propriétés BlueZ jointes à l'annonce
    stale = SimpleNamespace(
        address="76:0E:D1:00:00:9C", time=now - 1, device="stale-entry",
        advertisement=SimpleNamespace(
            local_name="GOODHOME-0006", platform_data=("/org/bluez/hci0/dev_76_0E_D1_00_00_9C", {"Address": fixed})
        ),
    )
    old_fixed = SimpleNamespace(address=fixed, time=now - 300, device="old", advertisement=SimpleNamespace(local_name=None))
    bluetooth = SimpleNamespace(async_discovered_service_info=lambda _hass, connectable: [old_fixed, stale])
    with patch.dict("sys.modules", {"homeassistant.components.bluetooth": bluetooth}), patch(
        "homeassistant.components.bluetooth", bluetooth, create=True
    ):
        assert await ble_client._async_wait_device(hass, fixed, None, timeout=0) == "stale-entry"
        # Après un redémarrage : annonces rangées sous l'adresse fixe
        fresh_fixed = SimpleNamespace(
            address=fixed, time=now, device="fixed", advertisement=SimpleNamespace(local_name=None, platform_data=None)
        )
        bluetooth.async_discovered_service_info = lambda _hass, connectable: [fresh_fixed]
        assert await ble_client._async_wait_device(hass, fixed, None, timeout=0) == "fixed"


async def test_deleting_local_device_removes_its_entry(hass, radiator):
    from homeassistant.helpers import device_registry as dr

    from custom_components.goodhome import async_remove_config_entry_device

    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=SERIAL,
        data={CONF_CONNECTION: CONNECTION_LOCAL, CONF_ADDRESS: ADDRESS, CONF_SERIAL: SERIAL},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    # async_get_device est déprécié dans les versions récentes de Home Assistant
    (device,) = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)

    assert await async_remove_config_entry_device(hass, entry, device)
    await hass.async_block_till_done()
    assert hass.config_entries.async_get_entry(entry.entry_id) is None
    assert radiator.is_connected is False


async def test_pairing_ignores_the_forgotten_address(hass):
    import time
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from custom_components.goodhome import ble_client

    fixed = "4C:11:AE:00:00:E6"
    now = time.monotonic()
    # BlueZ joint le nom gardé en mémoire à la dernière annonce de l'ancienne adresse fixe
    old = SimpleNamespace(address=fixed, time=now - 1, device="old", advertisement=SimpleNamespace(local_name="GOODHOME-0006"))
    pairing = SimpleNamespace(address="76:0E:D1:00:00:9C", time=now + 5, device="pairing",
                              advertisement=SimpleNamespace(local_name="GOODHOME-0006"))
    bluetooth = SimpleNamespace(async_discovered_service_info=lambda _hass, connectable: [old, pairing])
    paired = (fixed, SERIAL, {})
    with (
        patch.dict("sys.modules", {"homeassistant.components.bluetooth": bluetooth}),
        patch("homeassistant.components.bluetooth", bluetooth, create=True),
        patch.object(ble_client, "_async_forget", AsyncMock(return_value=frozenset({fixed}))),
        patch.object(ble_client, "_async_pair_once", AsyncMock(return_value=paired)) as pair_once,
    ):
        assert await ble_client.async_pair_radiator(hass, fixed, "GOODHOME-0006") == paired
    assert pair_once.await_args.args[1] == "pairing"


async def test_pairing_through_esphome_proxy_keeps_the_current_address(hass):
    import time
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from custom_components.goodhome import ble_client

    # Proxy ESPHome seul : BlueZ n'a aucun appairage à oublier, et le radiateur en mode
    # appairage s'annonce toujours à l'adresse passée par l'ajout
    address = "76:0E:D1:00:00:9C"
    pairing = SimpleNamespace(address=address, time=time.monotonic() + 5, device="pairing",
                              advertisement=SimpleNamespace(local_name="GOODHOME-0006"))
    bluetooth = SimpleNamespace(async_discovered_service_info=lambda _hass, connectable: [pairing])
    paired = (address, SERIAL, {})
    with (
        patch.dict("sys.modules", {"homeassistant.components.bluetooth": bluetooth}),
        patch("homeassistant.components.bluetooth", bluetooth, create=True),
        patch.object(ble_client, "_async_forget", AsyncMock(return_value=frozenset())),
        patch.object(ble_client, "_async_pair_once", AsyncMock(return_value=paired)) as pair_once,
    ):
        assert await ble_client.async_pair_radiator(hass, address, "GOODHOME-0006") == paired
    assert pair_once.await_args.args[1] == "pairing"


async def test_pairing_through_esphome_proxy_pairs_after_connecting(hass):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from custom_components.goodhome import ble_client

    device = SimpleNamespace(address="5E:B1:1E:23:C4:5D", details={"source": "C8:85:41:68:73:42"})
    bleak_client = SimpleNamespace(
        address=device.address, is_connected=True, unpair=AsyncMock(), pair=AsyncMock(), disconnect=AsyncMock()
    )
    connect = AsyncMock(return_value=bleak_client)
    retry_connector = SimpleNamespace(BleakClientWithServiceCache=object, establish_connection=connect)
    with (
        # bleak_retry_connector importe dbus-fast, absent hors Linux : module simulé
        patch.dict("sys.modules", {"bleak_retry_connector": retry_connector}),
        patch.object(GoodHomeBleClient, "async_adopt", AsyncMock(side_effect=GoodHomeBleError("stop"))),
        patch.object(ble_client, "_async_wait_device", AsyncMock(side_effect=ble_client.GoodHomeBleNotFound("x"))),
        pytest.raises(ble_client.GoodHomeBleNotFound),
    ):
        await ble_client._async_pair_once(hass, device, "GOODHOME-1FE9")
    # Pas d'appairage pendant la connexion (perdu par le proxy), mais juste après,
    # une fois oubliée la clé d'un essai précédent gardée par l'ESP32
    assert connect.await_args.kwargs["pair"] is False
    bleak_client.unpair.assert_awaited_once()
    bleak_client.pair.assert_awaited_once()


async def test_first_request_sent_again_while_pairing_finishes(hass):
    # Via un proxy ESPHome, le radiateur ignore les messages d'avant la fin de l'appairage
    fake = FakeRadiator(answer=False)
    loop = asyncio.get_running_loop()
    loop.call_later(0.3, setattr, fake, "answer", True)  # Réponses attendues 0,5 s dans les tests
    client = GoodHomeBleClient(hass, ADDRESS)
    await client.async_adopt(fake, attempts=3)
    assert client.serial == SERIAL
    assert [m["cmdName"] for m in fake.received].count("system.get_network_status") == 2


def test_pairing_agent_only_for_bluez_devices():
    import contextlib
    from types import SimpleNamespace

    from custom_components.goodhome import ble_client

    # Appareil relayé par un proxy ESPHome : pas de chemin D-Bus, pas d'agent BlueZ
    proxied = SimpleNamespace(address="76:0E:D1:00:00:9C", details={"source": "C8:85:41:68:73:42"})
    assert isinstance(ble_client._pairing_agent(proxied), contextlib.nullcontext)
    bluez = SimpleNamespace(details={"path": "/org/bluez/hci0/dev_76_0E_D1_00_00_9C", "props": {}})
    assert ble_client._uses_bluez(bluez)


async def test_remove_local_entry_allows_rediscovery(hass):
    from unittest.mock import MagicMock

    from custom_components.goodhome import async_remove_entry

    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=SERIAL,
        data={CONF_CONNECTION: CONNECTION_LOCAL, CONF_ADDRESS: ADDRESS, CONF_SERIAL: SERIAL, CONF_BLE_NAME: "GOODHOME-0001"},
    )
    rediscover = MagicMock()
    bluetooth = SimpleNamespace(
        async_rediscover_address=rediscover,
        # Le radiateur, remis en mode appairage, s'annonce sous une autre adresse
        async_discovered_service_info=lambda _hass, connectable: [
            SimpleNamespace(address="11:22:33:44:55:66", name="GOODHOME-0001", service_uuids=[]),
            SimpleNamespace(address="11:22:33:44:55:77", name="GOODHOME-0002", service_uuids=[]),
        ],
    )
    with patch.dict("sys.modules", {"homeassistant.components.bluetooth": bluetooth}), patch(
        "homeassistant.components.bluetooth", bluetooth, create=True
    ):
        await async_remove_entry(hass, entry)
        assert [call.args for call in rediscover.call_args_list] == [(hass, ADDRESS), (hass, "11:22:33:44:55:66")]

        # Compte cloud : rien à redécouvrir
        rediscover.reset_mock()
        await async_remove_entry(hass, MockConfigEntry(domain=DOMAIN, data={"email": "a@b.c"}))
        rediscover.assert_not_called()


async def test_connection_wait_requests_active_scan(hass):
    from unittest.mock import AsyncMock

    from custom_components.goodhome import ble_client

    wait = AsyncMock(side_effect=ble_client.GoodHomeBleNotFound("x"))
    client = GoodHomeBleClient(hass, ADDRESS, SERIAL, "GOODHOME-0001")
    with (
        # bleak_retry_connector importe dbus-fast, absent hors Linux : module simulé
        patch.dict("sys.modules", {"bleak_retry_connector": SimpleNamespace(
            BleakClientWithServiceCache=object, establish_connection=AsyncMock()
        )}),
        patch.object(ble_client, "_async_wait_device", wait),
        pytest.raises(ble_client.GoodHomeBleNotFound),
    ):
        await client._async_ensure_connected()
    assert wait.await_args.kwargs["active_scan"] is True


async def test_pairing_wait_requests_active_scan_and_explains(hass):
    from unittest.mock import AsyncMock

    from custom_components.goodhome import ble_client

    scan = AsyncMock()
    bluetooth = SimpleNamespace(
        async_discovered_service_info=lambda _hass, connectable: [],
        async_request_active_scan=scan,
        async_address_reachability_diagnostics=lambda _hass, address, intent: f"{address} not seen by any scanner ({intent})",
        BluetoothReachabilityIntent=SimpleNamespace(CONNECTION="connection"),
    )
    with patch.dict("sys.modules", {"homeassistant.components.bluetooth": bluetooth}), patch(
        "homeassistant.components.bluetooth", bluetooth, create=True
    ):
        with pytest.raises(ble_client.GoodHomeBleNotFound, match=r"not seen by any scanner \(connection\)"):
            await ble_client._async_wait_device(hass, ADDRESS, "GOODHOME-0001", timeout=1.5, active_scan=True)
        await hass.async_block_till_done()
        scan.assert_awaited_once_with(hass)

        # Hors appairage, pas de recherche active
        scan.reset_mock()
        with pytest.raises(ble_client.GoodHomeBleNotFound):
            await ble_client._async_wait_device(hass, ADDRESS, None, timeout=0)
        scan.assert_not_called()


async def test_older_home_assistant_without_recent_bluetooth_functions(hass):
    from custom_components.goodhome import ble_client

    bluetooth = SimpleNamespace(async_scanner_count=lambda _hass, connectable: 0)
    with patch.dict("sys.modules", {"homeassistant.components.bluetooth": bluetooth}), patch(
        "homeassistant.components.bluetooth", bluetooth, create=True
    ):
        ble_client.async_request_active_scan(hass)
        assert ble_client.async_reachability(hass, ADDRESS) is None
        assert ble_client.async_connectable_scanner_count(hass) == 0


async def test_failed_active_scan_and_diagnostics_are_ignored(hass):
    from unittest.mock import AsyncMock

    from custom_components.goodhome import ble_client

    def diagnose(_hass, _address, _intent):
        raise RuntimeError("boom")

    bluetooth = SimpleNamespace(
        async_request_active_scan=AsyncMock(side_effect=RuntimeError("busy")),
        async_address_reachability_diagnostics=diagnose,
        BluetoothReachabilityIntent=SimpleNamespace(CONNECTION="connection"),
    )
    with patch.dict("sys.modules", {"homeassistant.components.bluetooth": bluetooth}), patch(
        "homeassistant.components.bluetooth", bluetooth, create=True
    ):
        ble_client.async_request_active_scan(hass)
        await hass.async_block_till_done()
        assert ble_client.async_reachability(hass, ADDRESS) is None


async def test_bluetooth_not_loaded_does_not_break_flow_or_removal(hass):
    from custom_components.goodhome import async_remove_entry, ble_client

    def not_loaded(*_args, **_kwargs):
        raise RuntimeError("Bluetooth manager not set up")

    bluetooth = SimpleNamespace(
        async_scanner_count=not_loaded, async_rediscover_address=not_loaded, async_discovered_service_info=not_loaded
    )
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_CONNECTION: CONNECTION_LOCAL, CONF_ADDRESS: ADDRESS, CONF_BLE_NAME: "GOODHOME-0001"})
    with patch.dict("sys.modules", {"homeassistant.components.bluetooth": bluetooth}), patch(
        "homeassistant.components.bluetooth", bluetooth, create=True
    ):
        assert ble_client.async_connectable_scanner_count(hass) == 0
        await async_remove_entry(hass, entry)
