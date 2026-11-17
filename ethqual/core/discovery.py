"""Autodescubrimiento Zero-Config en LAN y Port Blink (localizador visual de puerto)."""

from __future__ import annotations

import json
import platform
import socket
import threading
import time
from collections.abc import Callable
from typing import Any

DISCOVERY_PORT = 5001
DISCOVERY_MAGIC = "ethqual-v1"


class ServerBeacon(threading.Thread):
    """Responde a sondas UDP DISCOVER en LAN para autodescubrimiento sin IP manual."""

    def __init__(self, tcp_port: int, listen_port: int = DISCOVERY_PORT) -> None:
        super().__init__(daemon=True)
        self.tcp_port = tcp_port
        self.listen_port = listen_port
        self._stop_event = threading.Event()
        self._ready_event = threading.Event()

    def wait_ready(self, timeout: float = 2.0) -> bool:
        return self._ready_event.wait(timeout)

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if hasattr(socket, "SO_REUSEPORT"):
                try:
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
                except OSError:
                    pass
            sock.bind(("", self.listen_port))
            sock.settimeout(0.5)
            self._ready_event.set()
        except OSError:
            self._ready_event.set()
            sock.close()
            return

        info_payload = json.dumps({
            "magic": DISCOVERY_MAGIC,
            "hostname": socket.gethostname(),
            "os": platform.system(),
            "port": self.tcp_port,
        }).encode("utf-8")

        try:
            while not self._stop_event.is_set():
                try:
                    data, addr = sock.recvfrom(1024)
                except socket.timeout:
                    continue
                except OSError:
                    break
                if b"DISCOVER" in data:
                    try:
                        sock.sendto(info_payload, addr)
                    except OSError:
                        pass
        finally:
            sock.close()


def discover_servers(timeout_s: float = 1.2, discovery_port: int = DISCOVERY_PORT) -> list[dict[str, Any]]:
    """Envía sonda UDP broadcast/loopback y devuelve los servidores ethqual encontrados."""
    found: dict[tuple[str, int], dict[str, Any]] = {}
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(0.3)
        probe = json.dumps({"magic": DISCOVERY_MAGIC, "cmd": "DISCOVER"}).encode("utf-8")
        for target in ("255.255.255.255", "127.0.0.1"):
            try:
                sock.sendto(probe, (target, discovery_port))
            except OSError:
                pass

        deadline = time.perf_counter() + timeout_s
        while time.perf_counter() < deadline:
            try:
                data, addr = sock.recvfrom(2048)
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                msg = json.loads(data.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if msg.get("magic") == DISCOVERY_MAGIC and "port" in msg:
                key = (addr[0], int(msg["port"]))
                found[key] = {
                    "ip": addr[0],
                    "port": int(msg["port"]),
                    "hostname": msg.get("hostname", addr[0]),
                    "os": msg.get("os", "Unknown"),
                }
    finally:
        sock.close()

    return list(found.values())


def run_port_blink(
    target_ip: str,
    duration_s: int = 10,
    port: int = 9,
    on_pulse: Callable[[bool], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> None:
    """Alterna ráfagas UDP (500ms ON / 500ms OFF) para hacer parpadear el LED del puerto del switch."""
    payload = b"\x55" * 128
    end_time = time.perf_counter() + max(1, duration_s)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        while time.perf_counter() < end_time:
            if cancel_event is not None and cancel_event.is_set():
                break
            if on_pulse is not None:
                on_pulse(True)
            burst_end = time.perf_counter() + 0.5
            while time.perf_counter() < burst_end:
                if cancel_event is not None and cancel_event.is_set():
                    break
                try:
                    sock.sendto(payload, (target_ip, port))
                except OSError:
                    break
                time.sleep(0.005)
            if on_pulse is not None:
                on_pulse(False)
            time.sleep(0.5)
