"""TCP front end that exposes a Device over a line-based ASCII protocol.

Real sensors of this kind usually talk RS-422 or Ethernet. The test station
connects through pyserial's ``socket://`` URL handler, so the same driver code
would work against a physical serial port (``COM3``) without changes.
"""

from __future__ import annotations

import socketserver
import threading

from .device import Device


class _Handler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        device: Device = self.server.device  # type: ignore[attr-defined]
        for raw in self.rfile:
            line = raw.decode("ascii", errors="replace").strip()
            if not line:
                continue
            response = device.handle(line)
            if response is None:
                continue
            self.wfile.write((response + "\n").encode("ascii"))


class _Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


class SimulatorServer:
    def __init__(self, device: Device, host: str = "127.0.0.1", port: int = 5025) -> None:
        self.device = device
        self._server = _Server((host, port), _Handler)
        self._server.device = device  # type: ignore[attr-defined]
        self._thread: threading.Thread | None = None

    @property
    def address(self) -> tuple[str, int]:
        host, port = self._server.server_address[:2]
        return str(host), int(port)

    @property
    def url(self) -> str:
        host, port = self.address
        return f"socket://{host}:{port}"

    def start(self) -> "SimulatorServer":
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def serve_forever(self) -> None:
        self._server.serve_forever()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
