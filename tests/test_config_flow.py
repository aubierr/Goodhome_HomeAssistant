"""Tests de la configuration depuis l'interface."""
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType

from custom_components.goodhome.const import DOMAIN

from .conftest import EMAIL, LOGIN_URL, PASSWORD, USER_ID


async def _cloud_form(hass):
    """Ouvrir l'ajout et choisir le compte cloud dans le menu."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.MENU
    assert result["menu_options"] == ["cloud", "local"]
    return await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "cloud"})


@pytest.fixture
def mock_setup_entry():
    """Ne pas charger le compte créé : seul le flow est testé ici."""
    with patch("custom_components.goodhome.async_setup_entry", new=AsyncMock(return_value=True)) as setup:
        yield setup


async def test_user_flow_creates_entry(hass, aioclient_mock, mock_setup_entry):
    aioclient_mock.post(LOGIN_URL, json={"token": "t", "id": USER_ID})
    result = await _cloud_form(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "cloud"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"email": EMAIL, "password": PASSWORD}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {"email": EMAIL, "password": PASSWORD}
    assert result["result"].unique_id == EMAIL


async def test_user_flow_invalid_auth(hass, aioclient_mock):
    aioclient_mock.post(LOGIN_URL, status=401)
    result = await _cloud_form(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"email": EMAIL, "password": "wrong"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_user_flow_cannot_connect(hass, aioclient_mock):
    aioclient_mock.post(LOGIN_URL, status=500)
    result = await _cloud_form(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"email": EMAIL, "password": PASSWORD}
    )
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_flow_already_configured(hass, config_entry, aioclient_mock):
    config_entry.add_to_hass(hass)
    result = await _cloud_form(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"email": EMAIL, "password": PASSWORD}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    # Aucune connexion tentée pour un compte déjà configuré
    assert aioclient_mock.call_count == 0


async def test_reauth_updates_password(hass, setup_integration, aioclient_mock):
    result = await setup_integration.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"password": "new"})
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert setup_integration.data["password"] == "new"


async def test_import_from_yaml(hass, aioclient_mock, mock_setup_entry):
    aioclient_mock.post(LOGIN_URL, json={"token": "t", "id": USER_ID})
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_IMPORT}, data={"email": EMAIL, "password": PASSWORD}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == EMAIL


# --- Bluetooth local ---

BLE_ADDRESS = "11:22:33:44:55:66"  # Adresse aléatoire avant appairage
FIXED_ADDRESS = "00:00:AB:00:00:02"
SERIAL = "0000AB000001"
PAIRED_STATE = {"roomName": "COULOIR", "currentTemp": 19.0}


@pytest.fixture(autouse=True)
def bluetooth_scanners():
    """Un adaptateur capable de se connecter ; recherche active simulée."""
    with (
        patch("custom_components.goodhome.ble_client.async_connectable_scanner_count", return_value=1) as count,
        patch("custom_components.goodhome.ble_client.async_request_active_scan") as active_scan,
    ):
        yield count, active_scan


@pytest.fixture
def discovered():
    radiators = {BLE_ADDRESS: "GOODHOME-0001"}
    with patch("custom_components.goodhome.ble_client.async_discovered_radiators", return_value=radiators):
        yield radiators


@pytest.fixture
def mock_pair():
    with patch(
        "custom_components.goodhome.ble_client.async_pair_radiator",
        new=AsyncMock(return_value=(FIXED_ADDRESS, SERIAL, PAIRED_STATE)),
    ) as pair:
        yield pair


async def _local_form(hass):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    return await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "local"})


async def test_local_flow_pairs_and_creates_entry(hass, discovered, mock_pair, mock_setup_entry):
    result = await _local_form(hass)
    assert result["step_id"] == "local"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"address": BLE_ADDRESS})
    assert result["step_id"] == "pair"
    assert result["description_placeholders"] == {"name": "GOODHOME-0001", "error": ""}

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "GoodHome COULOIR"
    assert result["data"] == {
        "connection": "local",
        "address": FIXED_ADDRESS,
        "serial": SERIAL,
        "ble_name": "GOODHOME-0001",
    }
    assert result["result"].unique_id == SERIAL
    mock_pair.assert_awaited_once_with(hass, BLE_ADDRESS, "GOODHOME-0001")


async def test_local_flow_pair_failure_can_retry(hass, discovered, mock_pair, mock_setup_entry):
    from custom_components.goodhome.ble_client import GoodHomeBleError

    result = await _local_form(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"address": BLE_ADDRESS})
    mock_pair.side_effect = GoodHomeBleError("AuthenticationCanceled")
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["step_id"] == "pair"
    assert result["errors"] == {"base": "pair_failed"}

    mock_pair.side_effect = None
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_local_flow_without_connectable_adapter(hass, bluetooth_scanners, discovered):
    count, _active_scan = bluetooth_scanners
    count.return_value = 0
    result = await _local_form(hass)
    assert result["step_id"] == "local"
    assert result["errors"] == {"base": "no_connectable_adapter"}
    assert "address" not in result["data_schema"].schema

    # Adaptateur ajouté entre-temps : Valider affiche la liste
    count.return_value = 1
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["errors"] is None
    assert result["data_schema"].schema["address"].container == {BLE_ADDRESS: "GOODHOME-0001"}


async def test_local_flow_waits_for_a_radiator_in_pairing_mode(hass, bluetooth_scanners, mock_pair, mock_setup_entry):
    _count, active_scan = bluetooth_scanners
    # Seuls des radiateurs sans nom (pas en mode appairage) sont visibles : ils ne sont pas proposés
    announced = {"56:82:18:00:00:94": "56:82:18:00:00:94"}
    # Un radiateur sans nom fait lire les noms de BlueZ : agent simulé (sous Linux, le vrai ouvre le
    # bus D-Bus système, ce que pytest-socket signale ; dbus-fast n'existe d'ailleurs que sous Linux)
    from types import SimpleNamespace

    agent = SimpleNamespace(async_known_names=AsyncMock(return_value={}))
    with (
        patch("custom_components.goodhome.ble_client.async_discovered_radiators", return_value=announced),
        patch.dict("sys.modules", {"custom_components.goodhome.ble_agent": agent}),
    ):
        result = await _local_form(hass)
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "local"
        assert result["errors"] == {"base": "no_radiator_in_pairing_mode"}
        # Recherche active pour un radiateur lointain
        active_scan.assert_called_once_with(hass)

        # Le radiateur passe en mode appairage : Valider relance la recherche
        announced[BLE_ADDRESS] = "GOODHOME-0001"
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        assert result["step_id"] == "local"
        assert result["errors"] is None
        assert result["data_schema"].schema["address"].container == {BLE_ADDRESS: "GOODHOME-0001"}

        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"address": BLE_ADDRESS})
    assert result["step_id"] == "pair"


async def test_local_flow_hides_configured_radiators(hass, discovered):
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    MockConfigEntry(domain=DOMAIN, unique_id=SERIAL, data={"connection": "local", "ble_name": "GOODHOME-0001"}).add_to_hass(hass)
    result = await _local_form(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "no_radiator_in_pairing_mode"}


async def test_bluetooth_discovery_goes_to_pairing(hass, discovered, mock_pair, mock_setup_entry):
    from types import SimpleNamespace

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_BLUETOOTH},
        data=SimpleNamespace(address=BLE_ADDRESS, name="GOODHOME-0001"),
    )
    assert result["step_id"] == "pair"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == SERIAL


async def test_pairing_existing_radiator_updates_address(hass, discovered, mock_pair):
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    entry = MockConfigEntry(domain=DOMAIN, unique_id=SERIAL, data={"connection": "local", "address": "old"})
    entry.add_to_hass(hass)
    result = await _local_form(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"address": BLE_ADDRESS})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data["address"] == FIXED_ADDRESS


@pytest.mark.parametrize(
    ("error", "reason"),
    [("GoodHomeBleNotFound", "not_found"), ("GoodHomeBlePairingRejected", "pair_rejected"), ("GoodHomeBleError", "pair_failed")],
)
async def test_local_flow_explains_pairing_errors(hass, discovered, mock_pair, error, reason):
    from custom_components.goodhome import ble_client

    result = await _local_form(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"address": BLE_ADDRESS})
    mock_pair.side_effect = getattr(ble_client, error)("detail")
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["errors"] == {"base": reason}
    assert result["description_placeholders"]["error"] == ("detail" if reason == "pair_failed" else "")


async def test_local_flow_names_paired_radiators_and_hides_added_ones(hass):
    from types import SimpleNamespace

    from pytest_homeassistant_custom_component.common import MockConfigEntry

    # Radiateurs déjà appairés : annoncés sous leur adresse fixe, sans nom
    announced = {"4C:11:AE:00:00:06": "4C:11:AE:00:00:06", FIXED_ADDRESS: FIXED_ADDRESS}
    known = {"4C:11:AE:00:00:06": "GOODHOME-0006", FIXED_ADDRESS: "GOODHOME-0001"}
    MockConfigEntry(
        domain=DOMAIN, unique_id=SERIAL, data={"connection": "local", "address": FIXED_ADDRESS, "ble_name": "GOODHOME-0001"}
    ).add_to_hass(hass)
    agent = SimpleNamespace(async_known_names=AsyncMock(return_value=known))
    with (
        patch("custom_components.goodhome.ble_client.async_discovered_radiators", return_value=announced),
        # dbus-fast n'existe que sous Linux : agent BlueZ simulé
        patch.dict("sys.modules", {"custom_components.goodhome.ble_agent": agent}),
    ):
        result = await _local_form(hass)
        options = result["data_schema"].schema["address"].container
        assert options == {"4C:11:AE:00:00:06": "GOODHOME-0006 (4C:11:AE:00:00:06)"}

        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"address": "4C:11:AE:00:00:06"})
    assert result["step_id"] == "pair"
    assert result["description_placeholders"]["name"] == "GOODHOME-0006"
