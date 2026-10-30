"""Client asynchrone de l'API cloud GoodHome."""
import asyncio
import logging
import time

import aiohttp

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://shkf02.goodhome.com"
USER_AGENT = "GoodHome/2010301 CFNetwork/3826.600.41 Darwin/24.6.0"
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=15)


class GoodHomeError(Exception):
    """Erreur de l'API GoodHome."""


class GoodHomeAuthError(GoodHomeError):
    """Identifiants refusés."""


class GoodHomeConnectionError(GoodHomeError):
    """API GoodHome injoignable ou réponse inattendue."""


def socketio_t_param():
    """Paramètre anti-cache « t » au format Socket.io."""
    alphabet = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_"
    num, result = int(time.time() * 1000), ""
    for _ in range(7):
        result = alphabet[num % 64] + result
        num //= 64
    return result


def _normalize_device(device):
    """Ne garder que les champs utilisés par l'intégration."""
    return {
        "id": device.get("_id"),
        "name": device.get("name"),
        "type": device.get("type"),
        "connected": device.get("connected", False),
        "state": device.get("state") or {},
    }


class GoodHomeClient:
    """Client de l'API GoodHome pour un compte."""

    def __init__(self, session: aiohttp.ClientSession, email: str, password: str):
        """Initialiser le client (aucune requête avant async_login)."""
        self._session = session
        self._email = email
        self._password = password
        self.user_id = None
        self.token = None
        self._refresh_token = None
        self._auth_lock = asyncio.Lock()
        # Cache HTTP : la liste des radiateurs n'est renvoyée que si elle a changé (304 sinon)
        self._devices = None
        self._etag = None

    async def async_login(self):
        """Se connecter avec email et mot de passe."""
        result = await self._request_json(
            "POST", "/v1/auth/login", json={"email": self._email, "password": self._password}, auth=False
        )
        if "token" not in result:
            raise GoodHomeConnectionError("No token in login response")
        self.token = result["token"]
        self.user_id = result.get("id")
        self._refresh_token = result.get("refresh_token")
        _LOGGER.debug("Logged in to GoodHome")

    async def async_renew_token(self, rejected_token=None):
        """Renouveler le token, ou se reconnecter si le renouvellement échoue.

        Plusieurs requêtes peuvent recevoir un 401 en même temps : seule la
        première renouvelle le token (rejected_token = celui qui a été refusé).
        """
        async with self._auth_lock:
            if rejected_token is not None and self.token != rejected_token:
                return
            if self._refresh_token:
                try:
                    result = await self._request_json(
                        "POST", "/v1/auth/refresh", json={"refresh_token": self._refresh_token}, auth=False
                    )
                    if "token" in result:
                        self.token = result["token"]
                        self._refresh_token = result.get("refresh_token", self._refresh_token)
                        _LOGGER.debug("GoodHome token refreshed")
                        return
                except GoodHomeError as err:
                    _LOGGER.debug("Token refresh failed (%s), logging in again", err)
            await self.async_login()

    async def async_get_devices(self):
        """Lire tous les radiateurs du compte, indexés par identifiant."""
        headers = {}
        # Pas de poignée de main Socket.io : la lecture REST fonctionne sans (testé sur l'API réelle)
        if self._devices is not None and self._etag:
            headers["If-None-Match"] = self._etag
        status, data, response_headers = await self._request(
            "GET", f"/v1/users/{self.user_id}/devices", extra_headers=headers
        )
        if status == 304 and self._devices is not None:
            return self._devices
        if status == 304:
            # 304 sans données en cache : relire sans en-tête de cache
            self._etag = None
            return await self.async_get_devices()

        devices = {}
        for device in (data or {}).get("devices", []):
            normalized = _normalize_device(device)
            if normalized["id"]:
                devices[normalized["id"]] = normalized
        self._devices = devices
        self._etag = response_headers.get("ETag")
        return devices

    async def async_set_state(self, device_id, parameters):
        """Envoyer des paramètres à un radiateur (ex. {"targetMode": 9})."""
        # Sans cette poignée de main, le radiateur applique la commande plus tard
        # (mesuré : 66 s avec, 130 s sans ; le délai restant vient du radiateur)
        await self._async_socketio_handshake()
        await self._request_json("PATCH", f"/v1/devices/{device_id}/state", json={"parameters": parameters})
        _LOGGER.debug("Sent %s to device %s", parameters, device_id)

    async def async_identify(self, device_id):
        """Faire biper un radiateur."""
        await self.async_set_state(device_id, {"ping": 1})

    async def _async_socketio_handshake(self):
        headers = self._socketio_headers()
        base = f"{BASE_URL}/socket.io-v2/?EIO=3&transport=polling&userId={self.user_id}"
        try:
            async with self._session.get(f"{base}&t={socketio_t_param()}", headers=headers, timeout=REQUEST_TIMEOUT) as r:
                body = await r.text()
            if '"sid":"' not in body:
                raise GoodHomeConnectionError("No Socket.io session id")
            sid = body.split('"sid":"', 1)[1].split('"', 1)[0]
            async with self._session.get(
                f"{base}&t={socketio_t_param()}&sid={sid}", headers=headers, timeout=REQUEST_TIMEOUT
            ) as r:
                await r.read()
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise GoodHomeConnectionError(f"Socket.io handshake failed: {err}") from err

    def _socketio_headers(self):
        return {"accept": "*/*", "user-agent": USER_AGENT, "authorization": f"Bearer {self.token}"}

    def _headers(self, auth=True):
        headers = {
            "accept": "application/json",
            "user-agent": USER_AGENT,
            "accept-language": "fr-FR,fr;q=0.9",
        }
        if auth:
            # En-tête utilisé par l'app officielle à la place de Authorization: Bearer
            headers["access-token"] = self.token
        return headers

    async def _request_json(self, method, path, *, json=None, auth=True):
        _, data, _ = await self._request(method, path, json=json, auth=auth)
        return data or {}

    async def _request(self, method, path, *, json=None, auth=True, extra_headers=None, retry=True):
        """Faire une requête, avec un nouvel essai après renouvellement du token sur 401."""
        token = self.token
        headers = {**self._headers(auth), **(extra_headers or {})}
        try:
            async with self._session.request(
                method, f"{BASE_URL}{path}", headers=headers, json=json, timeout=REQUEST_TIMEOUT
            ) as response:
                if response.status == 401 and auth and retry:
                    pass  # traité après la fermeture de la réponse
                elif response.status in (400, 401, 403) and not auth:
                    raise GoodHomeAuthError(f"Login rejected (HTTP {response.status})")
                elif response.status in (401, 403):
                    raise GoodHomeAuthError(f"Access denied (HTTP {response.status})")
                elif response.status == 304:
                    return 304, None, response.headers
                elif response.status >= 400:
                    raise GoodHomeConnectionError(f"HTTP {response.status} on {method} {path}")
                else:
                    # content_type=None : accepter le JSON quel que soit l'en-tête, None si corps vide
                    data = await response.json(content_type=None)
                    return response.status, data, response.headers
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
            raise GoodHomeConnectionError(f"Error on {method} {path}: {err}") from err

        _LOGGER.debug("Received 401 on %s %s, renewing token", method, path)
        await self.async_renew_token(token)
        return await self._request(method, path, json=json, auth=auth, extra_headers=extra_headers, retry=False)
