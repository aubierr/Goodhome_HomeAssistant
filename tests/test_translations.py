"""Tests des traductions : mêmes clés et mêmes variables dans toutes les langues."""
import json
import re
from pathlib import Path

import pytest
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.translation import async_get_translations

from custom_components.goodhome.select import TARGET_MODE_OPTIONS

from .conftest import DEVICE_ID, entity_id

COMPONENT = Path(__file__).parent.parent / "custom_components" / "goodhome"
STRINGS = json.loads((COMPONENT / "strings.json").read_text(encoding="utf-8"))
LANGUAGES = sorted(path.stem for path in (COMPONENT / "translations").glob("*.json"))


def _flatten(data, prefix=""):
    flat = {}
    for key, value in data.items():
        path = f"{prefix}.{key}" if prefix else key
        flat.update(_flatten(value, path) if isinstance(value, dict) else {path: value})
    return flat


def _load(language):
    return json.loads((COMPONENT / "translations" / f"{language}.json").read_text(encoding="utf-8"))


def test_expected_languages():
    assert LANGUAGES == ["en", "es", "fr", "pl", "pt", "ro"]


def test_english_matches_strings():
    assert _load("en") == STRINGS


@pytest.mark.parametrize("language", LANGUAGES)
def test_same_keys_and_placeholders(language):
    reference, translated = _flatten(STRINGS), _flatten(_load(language))
    assert translated.keys() == reference.keys()
    for key, text in reference.items():
        assert set(re.findall(r"{\w+}", translated[key])) == set(re.findall(r"{\w+}", text)), key
        assert translated[key].strip(), key


def test_every_select_option_is_translated():
    assert set(STRINGS["entity"]["select"]["target_mode"]["state"]) == set(TARGET_MODE_OPTIONS)


async def test_translations_are_loaded(hass, setup_integration):
    translations = await async_get_translations(hass, "fr", "entity", ["goodhome"])
    prefix = "component.goodhome.entity.climate.radiator.state_attributes"
    assert translations[f"{prefix}.preset_mode.state.manual"] == "Manuel"
    assert translations[f"{prefix}.eco_reason.state.absence"] == "Absence détectée"

    # Le thermostat utilise bien ces traductions
    climate = entity_id(hass, "climate", f"goodhome_climate_{DEVICE_ID}")
    assert er.async_get(hass).async_get(climate).translation_key == "radiator"
