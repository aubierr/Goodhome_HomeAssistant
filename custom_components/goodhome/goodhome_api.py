"""GoodHome API Client."""
import logging
import requests
import time
import random
import string

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://shkf02.goodhome.com"


class GoodHomeError(Exception):
    """Base exception for GoodHome API errors."""


class GoodHomeAuthError(GoodHomeError):
    """Raised when authentication fails (invalid credentials)."""


class GoodHomeConnectionError(GoodHomeError):
    """Raised when the GoodHome API cannot be reached."""


class GoodHomeAPI:
    """Class to communicate with GoodHome API."""
    
    def __init__(self, user_id, token, email=None, password=None):
        """Initialize the API client."""
        self.user_id = user_id
        self.token = token
        self.refresh_token = None
        self.email = email
        self.password = password
        self.sid = None
        self.token_expiry = None
        # Cache pour ETag/Last-Modified (gestion du 304)
        self._cache = {}
        self._etags = {}
        self._last_modified = {}
    
    def _is_token_expired(self):
        """Check if token is expired or about to expire."""
        if self.token_expiry is None:
            return False
        # Rafraîchir 1 heure avant l'expiration
        return time.time() > (self.token_expiry - 3600)
    
    def login(self):
        """Login with email and password to get a new token."""
        if not self.email or not self.password:
            _LOGGER.error("Email or password not provided for login")
            return False
        
        try:
            url = f"{BASE_URL}/v1/auth/login"
            headers = {
                "accept": "application/json",
                "content-type": "application/json",
                "user-agent": "GoodHome/2010301 CFNetwork/3826.600.41 Darwin/24.6.0",
                "accept-language": "fr-FR,fr;q=0.9",
                "accept-encoding": "gzip, deflate, br"
            }
            
            data = {
                "email": self.email,
                "password": self.password
            }
            
            response = requests.post(url, headers=headers, json=data, timeout=10)
            response.raise_for_status()
            result = response.json()
            
            if "token" in result:
                self.token = result["token"]
                self.user_id = result.get("id")
                self.refresh_token = result.get("refresh_token")
                # Le token expire dans 24h
                self.token_expiry = time.time() + 86400
                _LOGGER.info("Successfully logged in and obtained new token")
                return True
            
            _LOGGER.error("No token in login response")
            return False

        except requests.HTTPError as e:
            # 4xx = identifiants refusés, le reste = problème côté serveur
            if e.response is not None and e.response.status_code in (400, 401, 403):
                _LOGGER.error("Login rejected: %s", e)
                return False
            raise GoodHomeConnectionError(f"Error during login: {e}") from e
        except requests.RequestException as e:
            raise GoodHomeConnectionError(f"Error during login: {e}") from e
    
    def refresh_access_token(self):
        """Refresh the access token using refresh_token."""
        if not self.refresh_token:
            _LOGGER.warning("No refresh token available, attempting full login")
            return self.login()
        
        try:
            url = f"{BASE_URL}/v1/auth/refresh"
            headers = {
                "accept": "application/json",
                "content-type": "application/json",
                "user-agent": "GoodHome/2010301 CFNetwork/3826.600.41 Darwin/24.6.0",
                "accept-language": "fr-FR,fr;q=0.9",
                "accept-encoding": "gzip, deflate, br"
            }
            
            data = {
                "refresh_token": self.refresh_token
            }
            
            response = requests.post(url, headers=headers, json=data, timeout=10)
            response.raise_for_status()
            result = response.json()
            
            if "token" in result:
                self.token = result["token"]
                self.refresh_token = result.get("refresh_token", self.refresh_token)
                self.token_expiry = time.time() + 86400
                _LOGGER.info("Successfully refreshed token")
                return True
            
            _LOGGER.error("No token in refresh response, attempting full login")
            return self.login()
            
        except Exception as e:
            _LOGGER.error("Error refreshing token: %s, attempting full login", e)
            return self.login()
        
    def _generate_t_param(self):
        """Generate a t parameter similar to Socket.io."""
        alphabet = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_"
        timestamp = int(time.time() * 1000)
        result = ""
        num = timestamp
        
        for _ in range(7):
            idx = num % 64
            result = alphabet[idx] + result
            num = num // 64
        
        return result
    
    def _connect_socket(self):
        """Establish Socket.io connection and get SID."""
        try:
            t_param = self._generate_t_param()
            url = f"{BASE_URL}/socket.io-v2/?EIO=3&transport=polling&userId={self.user_id}&t={t_param}"
            
            headers = {
                "accept": "*/*",
                "accept-encoding": "gzip, deflate, br",
                "user-agent": "GoodHome/2010301 CFNetwork/3826.600.41 Darwin/24.6.0",
                "accept-language": "fr-FR,fr;q=0.9",
                "authorization": f"Bearer {self.token}"
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            
            # Extract SID from response
            response_text = response.text
            if '"sid":"' in response_text:
                sid_start = response_text.find('"sid":"') + 7
                sid_end = response_text.find('"', sid_start)
                self.sid = response_text[sid_start:sid_end]
                
                # Maintain connection
                t_param2 = self._generate_t_param()
                url2 = f"{BASE_URL}/socket.io-v2/?EIO=3&transport=polling&userId={self.user_id}&t={t_param2}&sid={self.sid}"
                requests.get(url2, headers=headers, timeout=10)
                
                return True
            
            _LOGGER.error("Failed to get SID from response")
            return False
            
        except Exception as e:
            _LOGGER.error("Error connecting to Socket.io: %s", e)
            return False
    
    def _get_headers(self):
        """Get headers for API v1 requests (with access-token like official app)."""
        return {
            "accept": "application/json",
            "user-agent": "GoodHome/2010301 CFNetwork/3826.600.41 Darwin/24.6.0",
            "accept-language": "fr-FR,fr;q=0.9",
            "accept-encoding": "gzip, deflate, br",
            "access-token": self.token  # Utilisé par l'app officielle au lieu de Authorization: Bearer
        }
    
    def get_devices(self):
        """Get all devices with 304 Not Modified support."""
        try:
            # Establish Socket.io connection first
            if not self._connect_socket():
                raise GoodHomeConnectionError("Failed to establish Socket.io connection")

            url = f"{BASE_URL}/v1/users/{self.user_id}/devices"
            headers = self._get_headers()
            
            # Ajouter les headers de cache si disponibles
            cache_key = f"devices_{self.user_id}"
            if cache_key in self._etags:
                headers["If-None-Match"] = self._etags[cache_key]
            if cache_key in self._last_modified:
                headers["If-Modified-Since"] = self._last_modified[cache_key]
            
            response = requests.get(url, headers=headers, timeout=10)
            
            # Gérer le 304 Not Modified
            if response.status_code == 304:
                if cache_key in self._cache:
                    return self._cache[cache_key]
                else:
                    # Cache vide mais 304 reçu, forcer le rechargement
                    _LOGGER.warning("Received 304 but no cache available, forcing reload")
                    headers.pop("If-None-Match", None)
                    headers.pop("If-Modified-Since", None)
                    response = requests.get(url, headers=headers, timeout=10)
            
            # Si 401, rafraîchir le token et réessayer
            if response.status_code == 401:
                _LOGGER.warning("Received 401, refreshing token...")
                if self.refresh_access_token():
                    # Réessayer avec le nouveau token
                    if not self._connect_socket():
                        raise GoodHomeConnectionError("Failed to establish Socket.io connection")
                    headers = self._get_headers()
                    # Ré-ajouter les headers de cache
                    if cache_key in self._etags:
                        headers["If-None-Match"] = self._etags[cache_key]
                    if cache_key in self._last_modified:
                        headers["If-Modified-Since"] = self._last_modified[cache_key]
                    response = requests.get(url, headers=headers, timeout=10)
                    
                    # Gérer à nouveau le 304 après refresh du token
                    if response.status_code == 304:
                        _LOGGER.debug("Received 304 after token refresh, using cached data")
                        if cache_key in self._cache:
                            return self._cache[cache_key]
                else:
                    raise GoodHomeAuthError("Failed to refresh token after 401")
            
            response.raise_for_status()
            
            # Stocker les headers de cache pour les prochaines requêtes
            if "ETag" in response.headers:
                self._etags[cache_key] = response.headers["ETag"]
            if "Last-Modified" in response.headers:
                self._last_modified[cache_key] = response.headers["Last-Modified"]
            
            data = response.json()
            
            devices = []
            if "devices" in data:
                for device in data["devices"]:
                    devices.append({
                        "id": device.get("_id"),
                        "name": device.get("name"),
                        "type": device.get("type"),
                        "connected": device.get("connected", False),
                        "state": device.get("state", {})
                    })
            
            # Mettre à jour le cache
            self._cache[cache_key] = devices
            
            return devices

        except GoodHomeError:
            raise
        except Exception as e:
            raise GoodHomeConnectionError(f"Error getting devices: {e}") from e
    
    def get_device(self, device_id):
        """Get a specific device with 304 Not Modified support."""
        try:
            if not self._connect_socket():
                return None
            
            url = f"{BASE_URL}/v1/devices/{device_id}/"
            headers = self._get_headers()
            
            # Ajouter les headers de cache si disponibles
            cache_key = f"device_{device_id}"
            if cache_key in self._etags:
                headers["If-None-Match"] = self._etags[cache_key]
            if cache_key in self._last_modified:
                headers["If-Modified-Since"] = self._last_modified[cache_key]
            
            response = requests.get(url, headers=headers, timeout=10)
            
            # Gérer le 304 Not Modified
            if response.status_code == 304:
                if cache_key in self._cache:
                    return self._cache[cache_key]
            
            response.raise_for_status()
            
            # Stocker les headers de cache
            if "ETag" in response.headers:
                self._etags[cache_key] = response.headers["ETag"]
            if "Last-Modified" in response.headers:
                self._last_modified[cache_key] = response.headers["Last-Modified"]
            
            device = response.json()
            result = {
                "id": device.get("_id"),
                "name": device.get("name"),
                "type": device.get("type"),
                "connected": device.get("connected", False),
                "state": device.get("state", {})
            }
            
            # Mettre à jour le cache
            self._cache[cache_key] = result
            
            return result
            
        except Exception as e:
            _LOGGER.error("Error getting device: %s", e)
            return None
    
    def _invalidate_cache(self, device_id=None):
        """Invalidate cache for a device or all devices."""
        if device_id:
            # Invalider le cache pour un appareil spécifique
            cache_key = f"device_{device_id}"
            if cache_key in self._cache:
                del self._cache[cache_key]
            if cache_key in self._etags:
                del self._etags[cache_key]
            if cache_key in self._last_modified:
                del self._last_modified[cache_key]
        else:
            # Invalider tout le cache
            self._cache.clear()
            self._etags.clear()
            self._last_modified.clear()
    
    def set_override_temperature(self, device_id, temperature):
        """Set target temperature for a device."""
        try:
            if not self._connect_socket():
                return False
            
            url = f"{BASE_URL}/v1/devices/{device_id}/state"
            headers = self._get_headers()
            headers["content-type"] = "application/json"
            
            # Utiliser le format parameters avec overrideTemp et targetMode
            data = {
                "parameters": {
                    "overrideTemp": temperature,
                    "targetMode": 8  # Mode confort par défaut lors du changement de température
                }
            }
            
            response = requests.patch(url, headers=headers, json=data, timeout=10)
            
            # Invalider le cache après modification
            self._invalidate_cache(device_id)
            
            # Si 401, rafraîchir le token et réessayer
            if response.status_code == 401:
                _LOGGER.warning("Received 401, refreshing token...")
                if self.refresh_access_token():
                    if not self._connect_socket():
                        return False
                    headers = self._get_headers()
                    headers["content-type"] = "application/json"
                    response = requests.patch(url, headers=headers, json=data, timeout=10)
                else:
                    return False
            
            response.raise_for_status()
            
            _LOGGER.info("Set temperature %s for device %s", temperature, device_id)
            return True
            
        except Exception as e:
            _LOGGER.error("Error setting temperature: %s", e)
            return False
    
    def set_mode(self, device_id, mode):
        """Set mode for a device."""
        try:
            if not self._connect_socket():
                return False
            
            url = f"{BASE_URL}/v1/devices/{device_id}/state"
            headers = self._get_headers()
            headers["content-type"] = "application/json"
            
            # Utiliser le format parameters
            data = {
                "parameters": {
                    "targetMode": mode
                }
            }
            
            response = requests.patch(url, headers=headers, json=data, timeout=10)
            
            # Invalider le cache après modification
            self._invalidate_cache(device_id)
            
            # Si 401, rafraîchir le token et réessayer
            if response.status_code == 401:
                _LOGGER.warning("Received 401, refreshing token...")
                if self.refresh_access_token():
                    if not self._connect_socket():
                        return False
                    headers = self._get_headers()
                    headers["content-type"] = "application/json"
                    response = requests.patch(url, headers=headers, json=data, timeout=10)
                else:
                    return False
            
            response.raise_for_status()
            
            _LOGGER.info("Set mode %s for device %s", mode, device_id)
            return True
            
        except Exception as e:
            _LOGGER.error("Error setting mode: %s", e)
            return False
    
    def identify_device(self, device_id):
        """Make the device beep for identification."""
        try:
            if not self._connect_socket():
                return False
            
            url = f"{BASE_URL}/v1/devices/{device_id}/state"
            headers = self._get_headers()
            headers["content-type"] = "application/json"
            
            # Envoyer la commande ping
            data = {
                "parameters": {
                    "ping": 1
                }
            }
            
            response = requests.patch(url, headers=headers, json=data, timeout=10)
            
            # Si 401, rafraîchir le token et réessayer
            if response.status_code == 401:
                _LOGGER.warning("Received 401, refreshing token...")
                if self.refresh_access_token():
                    if not self._connect_socket():
                        return False
                    headers = self._get_headers()
                    headers["content-type"] = "application/json"
                    response = requests.patch(url, headers=headers, json=data, timeout=10)
                else:
                    return False
            
            response.raise_for_status()
            
            _LOGGER.info("Identified device %s (ping)", device_id)
            return True
            
        except Exception as e:
            _LOGGER.error("Error identifying device: %s", e)
            return False
    
    def set_parameter(self, device_id, parameter_name, value):
        """Set a generic parameter for a device (for switches)."""
        try:
            if not self._connect_socket():
                return False
            
            url = f"{BASE_URL}/v1/devices/{device_id}/state"
            headers = self._get_headers()
            headers["content-type"] = "application/json"
            
            # L'API GoodHome attend des booléens JSON (true/false) pour les switches
            # et des nombres pour les autres paramètres
            data = {
                "parameters": {
                    parameter_name: value  # Envoyer directement: bool reste bool, int reste int
                }
            }
            
            response = requests.patch(url, headers=headers, json=data, timeout=10)
            
            # Invalider le cache après modification
            self._invalidate_cache(device_id)
            
            # Si 401, rafraîchir le token et réessayer
            if response.status_code == 401:
                _LOGGER.warning("Received 401, refreshing token...")
                if self.refresh_access_token():
                    if not self._connect_socket():
                        return False
                    headers = self._get_headers()
                    headers["content-type"] = "application/json"
                    response = requests.patch(url, headers=headers, json=data, timeout=10)
                else:
                    return False
            
            response.raise_for_status()
            
            _LOGGER.info("Set parameter %s=%s for device %s", parameter_name, value, device_id)
            return True
            
        except Exception as e:
            _LOGGER.error("Error setting parameter %s: %s", parameter_name, e)
            return False
    
    def set_temperature(self, device_id, temp_type, temperature):
        """Set a temperature setpoint (comfTemp, ecoTemp, antifTemp)."""
        try:
            if not self._connect_socket():
                return False
            
            url = f"{BASE_URL}/v1/devices/{device_id}/state"
            headers = self._get_headers()
            headers["content-type"] = "application/json"
            
            # L'API attend des températures en float avec 1 décimale
            data = {
                "parameters": {
                    temp_type: round(float(temperature), 1)
                }
            }
            
            response = requests.patch(url, headers=headers, json=data, timeout=10)
            
            # Invalider le cache après modification
            self._invalidate_cache(device_id)
            
            # Si 401, rafraîchir le token et réessayer
            if response.status_code == 401:
                _LOGGER.warning("Received 401, refreshing token...")
                if self.refresh_access_token():
                    if not self._connect_socket():
                        return False
                    headers = self._get_headers()
                    headers["content-type"] = "application/json"
                    response = requests.patch(url, headers=headers, json=data, timeout=10)
                else:
                    return False
            
            response.raise_for_status()
            
            _LOGGER.info("Set temperature %s=%s°C for device %s", temp_type, temperature, device_id)
            return True
            
        except Exception as e:
            _LOGGER.error("Error setting temperature %s: %s", temp_type, e)
            return False
