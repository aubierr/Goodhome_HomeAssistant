"""Tests du protocole Bluetooth local (trames et conversions)."""
from custom_components.goodhome.ble import (
    GET_ATTRIBUTES,
    TYPE_ACK,
    TYPE_DATA,
    FrameDecoder,
    attributes_in,
    build_ack,
    build_frame,
    build_get_attr,
    build_set_attr,
    checksum,
    from_radiator,
    split_chunks,
    to_radiator,
)

# Attributs réellement renvoyés par un radiateur (identifiants remplacés)
RADIATOR_VALUES = {
    "roomName": "COULOIR", "fwVer": "01206.3 TO100", "codeName": "DLRIRFH1000", "deviceSN": "0000AB000001",
    "roomID": "1000000001", "antifTemp": "70", "ecoTemp": "155", "comfTemp": "180", "targetTemp": "180",
    "overrideTemp": "185", "currentTemp": "190", "humidity": "635", "ctnAdjust": "0", "targetMode": "60",
    "dutyCycle": "0", "window": "1", "occupancyStatus": "1", "selfLearning": "0", "noprog": "0",
    "windowTimeout": "15", "selfLearningCountDay": "0",
}


def test_checksum_weighted_then_plain():
    # "ab" : pondérée 0x61*1 + 0x62*2 = 0x125 -> 0x25 ; simple 0x61 + 0x62 = 0xC3
    assert checksum(b"ab") == bytes((0x25, 0xC3))


def test_frame_layout_matches_app():
    frame = build_frame({"a": 1})
    text = b'{"a":1}'
    assert frame[:9] == b"___" + bytes((0, 0, 1)) + (len(text) + 1).to_bytes(3, "big")
    assert frame[9:-2] == text + b"\x00"
    assert frame[-2:] == checksum(text)


def test_ack():
    assert build_ack(b"\x00\x07") == b"___\x01\x00\x07"


def test_decoder_reassembles_chunks():
    frame = build_frame({"cmdName": "system.get_network_status", "cmdID": "1"})
    decoder = FrameDecoder()
    done = []
    for chunk in split_chunks(b"noise" + frame + build_ack(b"\x00\x02")):
        done += decoder.feed(chunk)
    assert [f.kind for f in done] == [TYPE_DATA, TYPE_ACK]
    assert done[0].message == {"cmdName": "system.get_network_status", "cmdID": "1"}
    assert done[0].checksum_ok
    assert done[1].counter == b"\x00\x02"


def test_decoder_flags_bad_checksum():
    frame = bytearray(build_frame({"a": 1}))
    frame[-1] ^= 0xFF
    (decoded,) = FrameDecoder().feed(bytes(frame))
    assert decoded.message == {"a": 1}
    assert not decoded.checksum_ok


def test_from_radiator_matches_cloud_format():
    state = from_radiator(RADIATOR_VALUES)
    assert state["currentTemp"] == 19.0
    assert state["humidity"] == 63.5
    assert state["overrideTemp"] == 18.5
    assert state["antifTemp"] == 7.0
    assert state["targetMode"] == 60
    assert state["window"] is True
    assert state["selfLearning"] is False
    # Renommé comme dans l'API cloud
    assert state["windowTimeOut"] == 15
    assert "windowTimeout" not in state
    # Textes et identifiants jamais convertis
    assert state["roomID"] == "1000000001"
    assert state["deviceSN"] == "0000AB000001"
    assert state["fwVer"] == "01206.3 TO100"


def test_to_radiator_like_app():
    assert to_radiator({"comfTemp": 19.3, "window": False, "targetMode": 9, "selfLearning": True}) == {
        "comfTemp": "193",
        "window": "0",
        "targetMode": "9",
        "selfLearning": "1",
    }


def test_round_trip():
    parameters = {"ecoTemp": 16.5, "noprog": True, "windowTimeOut": 30}
    assert from_radiator(to_radiator(parameters)) == parameters


def test_get_and_set_attr_commands():
    get = build_get_attr("SERIAL1", "mobile.000000000000", "3")
    assert get["cmdName"] == "system.send_to_host"
    assert get["hostID"] == "host.SERIAL1"
    assert get["params"] == {
        "cmdName": "ble_get_attr",
        "srcID": "mobile.000000000000",
        "request": {"method": "getAttr", "value": GET_ATTRIBUTES},
    }
    set_ = build_set_attr("SERIAL1", "mobile.000000000000", "4", {"overrideTemp": 20.5})
    assert set_["cmdID"] == "4"
    assert set_["params"]["request"] == {"method": "setAttr", "value": {"overrideTemp": "205"}}


def test_attributes_in():
    message = {"cmdName": "ble_set_attr", "srcID": "host.SERIAL1", "request": {"method": "setAttr", "value": {"a": "1"}}}
    assert attributes_in(message) == {"a": "1"}
    assert attributes_in({"type": "return", "cmdName": "system.send_to_host"}) is None
    assert attributes_in("text") is None
