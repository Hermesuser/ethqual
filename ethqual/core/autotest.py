"""AutoTest de servicios de red (Gateway, DNS) y TDR por driver Linux (ethtool)."""

from __future__ import annotations

import platform
import re
import shutil
import socket
import subprocess
import time
from typing import Any

from ethqual.core.lldp import get_lldp_neighbor
from ethqual.core.metrics import no_window_kwargs, run_ping


def get_default_gateway() -> str | None:
    """Detecta la IP del gateway por defecto de forma multiplataforma."""
    system = platform.system()
    try:
        if system == "Linux":
            proc = subprocess.run(
                ["ip", "route", "show", "default"],
                capture_output=True,
                text=True,
                timeout=3.0,
                check=False,
            )
            match = re.search(r"default\s+via\s+(\d+\.\d+\.\d+\.\d+)", proc.stdout)
            return match.group(1) if match else None
        if system == "Darwin":
            proc = subprocess.run(
                ["route", "-n", "get", "default"],
                capture_output=True,
                text=True,
                timeout=3.0,
                check=False,
            )
            match = re.search(r"gateway:\s*(\d+\.\d+\.\d+\.\d+)", proc.stdout)
            return match.group(1) if match else None
        if system == "Windows":
            proc = subprocess.run(
                ["route", "print", "0.0.0.0"],
                capture_output=True,
                text=True,
                timeout=3.0,
                check=False,
                **no_window_kwargs(),
            )
            match = re.search(
                r"0\.0\.0\.0\s+0\.0\.0\.0\s+(\d+\.\d+\.\d+\.\d+)", proc.stdout
            )
            return match.group(1) if match else None
    except (OSError, subprocess.SubprocessError):
        return None
    return None


def check_dns_resolution(hostname: str = "one.one.one.one") -> dict[str, Any]:
    """Mide el tiempo de resolución DNS del sistema sin fallar en redes aisladas."""
    start = time.perf_counter()
    try:
        ip = socket.gethostbyname(hostname)
        elapsed_ms = round((time.perf_counter() - start) * 1000.0, 2)
        return {"ok": True, "target": hostname, "resolved_ip": ip, "elapsed_ms": elapsed_ms}
    except OSError as exc:
        elapsed_ms = round((time.perf_counter() - start) * 1000.0, 2)
        return {
            "ok": False,
            "target": hostname,
            "resolved_ip": None,
            "elapsed_ms": elapsed_ms,
            "error": str(exc),
        }


def run_ethtool_cable_test(iface: str | None) -> dict[str, Any]:
    """Ejecuta `ethtool --cable-test <iface>` en Linux si el hardware/kernel lo soporta."""
    if platform.system() != "Linux":
        return {
            "supported": False,
            "reason": f"No soportado en {platform.system()} (solo Linux kernel 5.6+ con PHY compatible).",
            "pairs": {},
        }
    if not iface or iface == "lo":
        return {"supported": False, "reason": "Interfaz no válida o loopback.", "pairs": {}}

    ethtool_bin = shutil.which("ethtool")
    if not ethtool_bin:
        return {"supported": False, "reason": "Binario `ethtool` no instalado.", "pairs": {}}

    try:
        proc = subprocess.run(
            [ethtool_bin, "--cable-test", iface],
            capture_output=True,
            text=True,
            timeout=6.0,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"supported": False, "reason": str(exc), "pairs": {}}

    output = f"{proc.stdout}\n{proc.stderr}".strip()
    if proc.returncode != 0:
        return {
            "supported": False,
            "reason": output or f"ethtool retornó código {proc.returncode} (requiere root o driver compatible).",
            "pairs": {},
        }

    pairs: dict[str, dict[str, Any]] = {}
    for line in output.splitlines():
        m_pair = re.search(r"Pair\s+([A-D]):\s*([^\n,]+)", line, re.IGNORECASE)
        if m_pair:
            pair_id = m_pair.group(1).upper()
            status_txt = m_pair.group(2).strip()
            m_dist = re.search(r"Fault\s+length:\s*([\d.]+)\s*m", line, re.IGNORECASE)
            pairs[pair_id] = {
                "status": status_txt,
                "fault_length_m": float(m_dist.group(1)) if m_dist else None,
            }

    return {"supported": bool(pairs), "raw_output": output, "pairs": pairs}


def check_ip_conflict_arp(target_ip: str | None) -> dict[str, Any]:
    """Verifica en la tabla ARP/Neighbor si múltiples MACs responden a la misma IP."""
    if not target_ip:
        return {"checked": False, "conflict_detected": False, "macs": []}

    system = platform.system()
    if system == "Windows":
        cmd = ["arp", "-a", target_ip]
    elif system == "Darwin":
        cmd = ["arp", "-n", target_ip]
    else:
        cmd = ["ip", "neigh", "show", target_ip]

    mac_re = re.compile(r"([0-9a-fA-F]{1,2}(?:[:-][0-9a-fA-F]{1,2}){5})")
    macs: set[str] = set()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=3.0, check=False, **no_window_kwargs())
        for line in proc.stdout.splitlines():
            if target_ip in line:
                m = mac_re.search(line)
                if m:
                    macs.add(m.group(1).lower().replace("-", ":"))
    except (OSError, subprocess.SubprocessError):
        return {"checked": False, "conflict_detected": False, "macs": []}

    return {
        "checked": True,
        "target_ip": target_ip,
        "macs": sorted(macs),
        "conflict_detected": len(macs) > 1,
    }


def detect_dhcp_servers(timeout_s: float = 1.5) -> dict[str, Any]:
    """Envía sonda DHCPDISCOVER (si el SO permite puerto 68) para detectar doble DHCP."""
    import os
    import struct

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.bind(("0.0.0.0", 68))
        sock.settimeout(0.4)
    except OSError as exc:
        sock.close()
        return {
            "supported": False,
            "reason": f"Sin privilegios para puerto UDP 68 ({exc}).",
            "servers": [],
            "multiple_dhcp_detected": False,
        }

    xid = os.urandom(4)
    mac_bytes = os.urandom(6)
    # Paquete BOOTP/DHCPDISCOVER mínimo (244 bytes)
    discover = (
        b"\x01\x01\x06\x00"
        + xid
        + b"\x00\x00\x80\x00"
        + b"\x00" * 16
        + mac_bytes
        + b"\x00" * 10
        + b"\x00" * 192
        + b"\x63\x82\x53\x63"
        + b"\x35\x01\x01"
        + b"\xff"
    )
    servers: set[str] = set()
    try:
        sock.sendto(discover, ("255.255.255.255", 67))
        deadline = time.perf_counter() + timeout_s
        while time.perf_counter() < deadline:
            try:
                data, addr = sock.recvfrom(1024)
            except socket.timeout:
                continue
            if len(data) >= 240 and data[4:8] == xid:
                servers.add(addr[0])
    except OSError:
        pass
    finally:
        sock.close()

    return {
        "supported": True,
        "servers": sorted(servers),
        "multiple_dhcp_detected": len(servers) > 1,
    }


def run_network_autotest(
    iface: str | None,
    dns_target: str = "one.one.one.one",
    target_ip: str | None = None,
    check_dhcp: bool = False,
) -> dict[str, Any]:
    """Ejecuta AutoTest de servicios de red (Gateway, DNS, ARP/DHCP) y TDR PHY si está disponible."""
    gw = get_default_gateway()
    gw_ping = run_ping(gw, count=2, timeout_ms=800) if gw else None
    dns_res = check_dns_resolution(dns_target)
    cable_test = run_ethtool_cable_test(iface)
    lldp_res = get_lldp_neighbor(iface)
    arp_conflict = check_ip_conflict_arp(target_ip)
    dhcp_scan = detect_dhcp_servers() if check_dhcp else {
        "supported": False,
        "reason": "Escaneo DHCP no solicitado.",
        "servers": [],
        "multiple_dhcp_detected": False,
    }
    return {
        "gateway_ip": gw,
        "gateway_ping": gw_ping,
        "dns": dns_res,
        "ethtool_cable_test": cable_test,
        "lldp": lldp_res,
        "arp_conflict": arp_conflict,
        "dhcp_scan": dhcp_scan,
    }
