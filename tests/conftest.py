"""Fixtures communes aux tests GoodHome."""
import socket
import sys

import pytest

# Importer notre paquet en premier : sinon Home Assistant trouve celui du dossier
# de test de pytest-homeassistant-custom-component et ne voit pas goodhome
import custom_components  # noqa: F401


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Charger custom_components/goodhome dans chaque test."""
    yield


if sys.platform == "win32":
    # Sous Windows, la boucle asyncio crée une paire de sockets locale pour se
    # réveiller, ce que pytest-socket bloque. On la crée avec la vraie classe
    # socket ; le reste du réseau reste bloqué et les appels HTTP simulés.
    _real_socket = socket.socket

    def _local_socketpair(family=socket.AF_INET, type=socket.SOCK_STREAM, proto=0):
        with _real_socket(family, type, proto) as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            client = _real_socket(family, type, proto)
            client.connect(listener.getsockname())
            fd, _ = listener._accept()  # accept() recréerait le socket avec la classe bloquée
            server = _real_socket(family, type, proto, fileno=fd)
        return server, client

    socket.socketpair = _local_socketpair
