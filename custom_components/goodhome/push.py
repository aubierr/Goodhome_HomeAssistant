"""Écoute temps réel du cloud GoodHome (Socket.io v2 / Engine.IO v3 en long-polling).

Le serveur pousse, avec uniquement les champs modifiés (testé sur l'API réelle) :
- « setState » quand le radiateur a appliqué un réglage (depuis l'app ou Home Assistant) ;
- « report » quand ses mesures changent (température ambiante, humidité...).
La relecture REST du coordinator reste active en secours.
"""
import asyncio
import json
import logging
import time

import aiohttp

from .goodhome_api import BASE_URL, USER_AGENT, GoodHomeError, socketio_t_param

_LOGGER = logging.getLogger(__name__)

RECONNECT_MIN_DELAY = 5  # Délai avant reconnexion (secondes), doublé à chaque échec
RECONNECT_MAX_DELAY = 300


class GoodHomePushSessionLost(Exception):
    """La session Socket.io a été fermée par le serveur."""


class GoodHomePushAuthError(Exception):
    """Le serveur refuse le token."""


def parse_payload(payload):
    """Découper une réponse Engine.IO v3 en paquets : '<longueur>:<paquet>...'."""
    packets, i = [], 0
    while i < len(payload):
        sep = payload.find(":", i)
        if sep == -1 or not payload[i:sep].isdigit():
            packets.append(payload[i:])
            break
        length = int(payload[i:sep])
        packets.append(payload[sep + 1:sep + 1 + length])
        i = sep + 1 + length
    return packets


class GoodHomePushClient:
    """Client Socket.io qui transmet les événements du serveur à `on_event(nom, données)`."""

    def __init__(self, session: aiohttp.ClientSession, client, on_event):
        """Initialiser le client ; client est le GoodHomeClient du compte (token à jour)."""
        self._session = session
        self._client = client
        self._on_event = on_event
        self._token = None  # Token de la session en cours, pour ne renouveler que celui refusé

    async def run(self):
        """Écouter indéfiniment, avec reconnexion automatique (s'arrête à l'annulation)."""
        delay = RECONNECT_MIN_DELAY
        while True:
            started = time.monotonic()
            try:
                await self._listen()
            except asyncio.CancelledError:
                raise
            except GoodHomePushAuthError as err:
                _LOGGER.debug("GoodHome push: token refused, renewing it")
                try:
                    await self._client.async_renew_token(err.args[0] if err.args else None)
                except GoodHomeError as renew_err:
                    _LOGGER.debug("GoodHome push: token renewal failed (%s)", renew_err)
            except (aiohttp.ClientError, asyncio.TimeoutError, GoodHomePushSessionLost, ValueError) as err:
                _LOGGER.debug("GoodHome push: connection lost (%s), reconnecting in %ss", err, delay)

            # Une session qui a tenu longtemps remet le délai de reconnexion à zéro
            if time.monotonic() - started > RECONNECT_MAX_DELAY:
                delay = RECONNECT_MIN_DELAY
            await asyncio.sleep(delay)
            delay = min(delay * 2, RECONNECT_MAX_DELAY)

    async def _request(self, method, url, headers, data=None, timeout=15):
        async with self._session.request(
            method, url, headers=headers, data=data, timeout=aiohttp.ClientTimeout(total=timeout)
        ) as response:
            if response.status in (401, 403):
                raise GoodHomePushAuthError(self._token)
            if response.status != 200:
                # 400 = session inconnue (expirée ou fermée côté serveur)
                raise GoodHomePushSessionLost(f"HTTP {response.status}")
            return await response.text()

    async def _listen(self):
        user_id, token = self._client.user_id, self._client.token
        if not user_id or not token:
            raise GoodHomePushAuthError(None)
        self._token = token

        headers = {"accept": "*/*", "user-agent": USER_AGENT, "authorization": f"Bearer {token}"}
        base = f"{BASE_URL}/socket.io-v2/?EIO=3&transport=polling&userId={user_id}"

        packets = parse_payload(await self._request("GET", f"{base}&t={socketio_t_param()}", headers))
        if not packets or not packets[0].startswith("0"):
            raise GoodHomePushSessionLost("unexpected handshake")
        opened = json.loads(packets[0][1:])
        url = f"{base}&sid={opened['sid']}"
        ping_interval = opened.get("pingInterval", 25000) / 1000
        _LOGGER.debug("GoodHome push: connected (ping every %ss)", ping_interval)
        self._handle_packets(packets[1:])

        ping_task = asyncio.create_task(self._ping_loop(url, headers, ping_interval))
        try:
            while True:
                if ping_task.done():
                    # Fait remonter l'erreur du ping (session perdue)
                    ping_task.result()
                payload = await self._request("GET", f"{url}&t={socketio_t_param()}", headers, timeout=ping_interval + 20)
                self._handle_packets(parse_payload(payload))
        finally:
            ping_task.cancel()

    async def _ping_loop(self, url, headers, interval):
        """Envoyer le ping Engine.IO, sans lequel le serveur ferme la session."""
        post_headers = {**headers, "content-type": "text/plain;charset=UTF-8"}
        while True:
            await asyncio.sleep(interval)
            await self._request("POST", f"{url}&t={socketio_t_param()}", post_headers, data="1:2")

    def _handle_packets(self, packets):
        for packet in packets:
            if packet == "1":
                raise GoodHomePushSessionLost("closed by server")
            if not packet.startswith("42"):
                continue  # pong, noop, connexion au namespace
            try:
                event = json.loads(packet[2:])
            except ValueError:
                _LOGGER.debug("GoodHome push: invalid event %s", packet)
                continue
            if isinstance(event, list) and event and isinstance(event[0], str):
                self._on_event(event[0], event[1] if len(event) > 1 else None)
