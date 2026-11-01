"""Protocole Bluetooth local des radiateurs GoodHome (retrouvé dans l'appli GoodHome Connect).

Le radiateur expose le service 0xF0 : l'appli écrit sur 0xF1 (par morceaux de 20 octets,
sans réponse) et reçoit sur 0xF2 (notifications). Chaque message est une trame :

    b"___" | type (0 données, 1 ACK, 2 NACK) | compteur (2 o) | longueur (3 o) | JSON + \\0 | checksum (2 o)

Les ACK/NACK s'arrêtent après le compteur (6 octets). La longueur compte le \\0 final ;
le checksum porte sur le JSON seul.

Les valeurs voyagent en texte : températures, humidité et ctnAdjust en dixièmes,
booléens en "0"/"1". Ce module les convertit vers le format de l'API cloud, pour que
les entités fonctionnent de la même façon dans les deux modes.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

SERVICE_UUID = "000000f0-0000-1000-8000-00805f9b34fb"
WRITE_UUID = "000000f1-0000-1000-8000-00805f9b34fb"
NOTIFY_UUID = "000000f2-0000-1000-8000-00805f9b34fb"
LOCAL_NAME_PREFIX = "GOODHOME-"

MARKER = b"___"
TYPE_DATA, TYPE_ACK, TYPE_NACK = 0, 1, 2
CHUNK_SIZE = 20

# Attributs demandés par l'appli à chaque rafraîchissement Bluetooth
GET_ATTRIBUTES = [
    "networkId", "roomID", "roomName", "roomType", "deviceSN", "model", "fwVer", "antifTemp", "comfTemp",
    "ecoTemp", "holidayTimeout", "noprog", "occupancyStatus", "daylightSaving", "overrideTemp", "overrideTime",
    "selfLearningCountDay", "selfLearning", "selfLearningImprove", "dutyCycle", "targetTemp", "currentTemp",
    "targetMode", "humidity", "ctnAdjust", "language", "window", "windowTimeOut", "codeName", "codeId",
    "localTime", "ssid",
]
BOOLEAN_ATTRIBUTES = {"window", "occupancyStatus", "selfLearning", "selfLearningImprove", "noprog", "daylightSaving"}
# Identifiants et textes : jamais convertis en nombre
TEXT_ATTRIBUTES = {"roomID", "roomName", "deviceSN", "model", "fwVer", "codeName", "ssid", "networkId"}
# Le radiateur renvoie « windowTimeout » pour l'attribut demandé « windowTimeOut »
RENAMED_ATTRIBUTES = {"windowTimeout": "windowTimeOut"}


def _in_tenths(key: str) -> bool:
    return "Temp" in key or key in ("humidity", "ctnAdjust")


def from_radiator(values: dict[str, Any]) -> dict[str, Any]:
    """Valeurs Bluetooth -> format de l'API cloud (« 185 » -> 18.5, « 1 » -> True)."""
    state = {}
    for key, value in values.items():
        key = RENAMED_ATTRIBUTES.get(key, key)
        text = str(value)
        if key in TEXT_ATTRIBUTES:
            state[key] = text
        elif key in BOOLEAN_ATTRIBUTES:
            state[key] = text == "1"
        elif _in_tenths(key):
            try:
                state[key] = int(text) / 10
            except ValueError:
                state[key] = text
        else:
            try:
                state[key] = int(text)
            except ValueError:
                state[key] = text
    return state


def to_radiator(parameters: dict[str, Any]) -> dict[str, Any]:
    """Format de l'API cloud -> valeurs Bluetooth, comme formatCommand dans l'appli."""
    values: dict[str, Any] = {}
    for key, value in parameters.items():
        if _in_tenths(key):
            values[key] = str(round(float(value) * 10))
        elif isinstance(value, bool):
            values[key] = "1" if value else "0"
        elif isinstance(value, list):
            values[key] = [str(item) for item in value]
        else:
            values[key] = str(value)
    return values


def checksum(payload: bytes) -> bytes:
    """Somme pondérée par la position, puis somme simple, chacune sur un octet."""
    plain = weighted = 0
    for position, byte in enumerate(payload, start=1):
        plain = (plain + byte) & 0xFF
        weighted = (weighted + byte * position) & 0xFF
    return bytes((weighted, plain))


def build_frame(message: dict[str, Any]) -> bytes:
    """Encoder un message JSON comme l'appli (compteur fixe à 1)."""
    text = json.dumps(message, separators=(",", ":")).encode()
    header = MARKER + bytes((TYPE_DATA, 0, 1)) + (len(text) + 1).to_bytes(3, "big")
    return header + text + b"\x00" + checksum(text)


def build_ack(counter: bytes) -> bytes:
    """Accuser réception d'une trame de données (compteur recopié)."""
    return MARKER + bytes((TYPE_ACK,)) + counter


def split_chunks(frame: bytes, size: int = CHUNK_SIZE) -> list[bytes]:
    """Découper une trame en morceaux écrits un par un."""
    return [frame[i : i + size] for i in range(0, len(frame), size)]


def build_system_command(name: str, cmd_id: str) -> dict[str, Any]:
    """Commande adressée au module Bluetooth lui-même (ex. system.get_network_status)."""
    return {"type": "command", "cmdName": name, "cmdID": cmd_id}


def _host_command(serial: str, src_id: str, cmd_id: str, name: str, request: dict[str, Any]) -> dict[str, Any]:
    # hostID = « host. » + numéro de série ; srcID = identifiant que le radiateur nous a donné (dstID)
    return {
        "type": "command",
        "cmdName": "system.send_to_host",
        "cmdID": cmd_id,
        "hostID": f"host.{serial}",
        "params": {"cmdName": name, "srcID": src_id, "request": request},
    }


def build_get_attr(serial: str, src_id: str, cmd_id: str) -> dict[str, Any]:
    """Demander les attributs du radiateur ; il répond par des messages ble_set_attr."""
    return _host_command(serial, src_id, cmd_id, "ble_get_attr", {"method": "getAttr", "value": GET_ATTRIBUTES})


def build_set_attr(serial: str, src_id: str, cmd_id: str, parameters: dict[str, Any]) -> dict[str, Any]:
    """Modifier des attributs, donnés au format de l'API cloud."""
    return _host_command(
        serial, src_id, cmd_id, "ble_set_attr", {"method": "setAttr", "value": to_radiator(parameters)}
    )


def attributes_in(message: Any) -> dict[str, Any] | None:
    """Attributs portés par un message ble_set_attr du radiateur, None pour un autre message."""
    if not isinstance(message, dict) or message.get("cmdName") != "ble_set_attr":
        return None
    request = message.get("request") or {}
    value = request.get("value")
    return value if request.get("method") == "setAttr" and isinstance(value, dict) else None


@dataclass
class Frame:
    """Trame reçue du radiateur."""

    kind: int
    counter: bytes
    message: Any = None
    checksum_ok: bool = True


@dataclass
class FrameDecoder:
    """Recoller les notifications en trames complètes."""

    buffer: bytes = b""

    def feed(self, data: bytes) -> list[Frame]:
        """Ajouter des octets reçus et rendre les trames terminées."""
        self.buffer += data
        done: list[Frame] = []
        while (start := self.buffer.find(MARKER)) >= 0:
            self.buffer = self.buffer[start:]
            if len(self.buffer) < 6:
                break
            kind, counter = self.buffer[3], self.buffer[4:6]
            if kind in (TYPE_ACK, TYPE_NACK):
                done.append(Frame(kind, counter))
                self.buffer = self.buffer[6:]
                continue
            if len(self.buffer) < 9:
                break
            length = int.from_bytes(self.buffer[6:9], "big")
            total = 9 + length + 2
            if len(self.buffer) < total:
                break
            raw, self.buffer = self.buffer[:total], self.buffer[total:]
            payload = raw[9 : 9 + length].rstrip(b"\x00")
            try:
                message: Any = json.loads(payload)
            except ValueError:
                message = payload.decode(errors="replace")
            done.append(Frame(kind, counter, message, checksum(payload) == raw[-2:]))
        else:
            self.buffer = b""
        return done
