"""Recolección multiplataforma de telemetría NIC, capa 2 (ARP/ICMP) y análisis PHY."""

from __future__ import annotations

import ipaddress
import platform
import re
import socket
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import psutil


@dataclass(slots=True)
class LinkInfo:
    """Estado de negociación física de una interfaz de red."""

    interface: str | None
    is_up: bool | None
    speed_mbps: int | None
    duplex: str
    mtu: int | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class NicSnapshot:
    """Captura puntual de contadores de interfaz y errores físicos disponibles."""

    interface: str | None
    errin: int | None
    errout: int | None
    dropin: int | None
    dropout: int | None
    bytes_sent: int | None
    bytes_recv: int | None
    packets_sent: int | None
    packets_recv: int | None
    os_physical_errors: dict[str, int | None]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def no_window_kwargs() -> dict[str, Any]:
    """Evita ventanas de consola emergentes en Windows al ejecutar subprocesos desde la GUI."""
    if platform.system() == "Windows" and hasattr(subprocess, "CREATE_NO_WINDOW"):
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


def detect_interface_by_ip(local_ip: str) -> str | None:
    """Identifica el nombre de la interfaz local asociada a `local_ip`."""
    try:
        target = str(ipaddress.ip_address(local_ip))
    except ValueError:
        return None

    for iface, addrs in psutil.net_if_addrs().items():
        for addr in addrs:
            if addr.family == socket.AF_INET and addr.address == target:
                return iface
    return None


def _map_duplex(duplex_val: int) -> str:
    if duplex_val == psutil.NIC_DUPLEX_FULL:
        return "full"
    if duplex_val == psutil.NIC_DUPLEX_HALF:
        return "half"
    return "unknown"


def get_link_info(iface: str | None) -> LinkInfo:
    """Consulta velocidad, dúplex y estado de enlace mediante psutil."""
    if not iface:
        return LinkInfo(None, None, None, "unknown", None)
    stats = psutil.net_if_stats().get(iface)
    if stats is None:
        return LinkInfo(iface, None, None, "unknown", None)
    return LinkInfo(
        interface=iface,
        is_up=bool(stats.isup),
        speed_mbps=int(stats.speed) if stats.speed is not None else None,
        duplex=_map_duplex(stats.duplex),
        mtu=int(stats.mtu) if stats.mtu is not None else None,
    )


def _read_linux_sysfs_errors(iface: str) -> dict[str, int | None]:
    """Lee contadores físicos detallados en Linux sysfs sin lanzar excepciones."""
    fields = (
        "rx_crc_errors",
        "rx_frame_errors",
        "rx_fifo_errors",
        "tx_carrier_errors",
        "tx_aborted_errors",
    )
    results: dict[str, int | None] = {f: None for f in fields}
    if platform.system() != "Linux":
        return results

    base = Path(f"/sys/class/net/{iface}/statistics")
    if not base.is_dir():
        return results

    for field in fields:
        try:
            results[field] = int((base / field).read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            results[field] = None
    return results


def get_nic_snapshot(iface: str | None) -> NicSnapshot:
    """Obtiene los contadores actuales de la interfaz indicada."""
    if not iface:
        return NicSnapshot(None, None, None, None, None, None, None, None, None, {})

    counters = psutil.net_io_counters(pernic=True).get(iface)
    phys_errors = _read_linux_sysfs_errors(iface)
    if counters is None:
        return NicSnapshot(
            iface, None, None, None, None, None, None, None, None, phys_errors
        )

    return NicSnapshot(
        interface=iface,
        errin=int(counters.errin),
        errout=int(counters.errout),
        dropin=int(counters.dropin),
        dropout=int(counters.dropout),
        bytes_sent=int(counters.bytes_sent),
        bytes_recv=int(counters.bytes_recv),
        packets_sent=int(counters.packets_sent),
        packets_recv=int(counters.packets_recv),
        os_physical_errors=phys_errors,
    )


def _safe_delta(before: int | None, after: int | None) -> int | None:
    if before is None or after is None:
        return None
    return max(0, after - before)


def compute_nic_delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Calcula la diferencia entre dos snapshots de NIC (en formato dict)."""
    keys = (
        "errin",
        "errout",
        "dropin",
        "dropout",
        "bytes_sent",
        "bytes_recv",
        "packets_sent",
        "packets_recv",
    )
    delta: dict[str, Any] = {
        "interface": after.get("interface") or before.get("interface"),
        "counters": {k: _safe_delta(before.get(k), after.get(k)) for k in keys},
        "os_physical_errors": {},
    }

    b_phys = before.get("os_physical_errors") or {}
    a_phys = after.get("os_physical_errors") or {}
    for k in sorted(set(b_phys.keys()) | set(a_phys.keys())):
        delta["os_physical_errors"][k] = _safe_delta(b_phys.get(k), a_phys.get(k))
    return delta


def run_ping(target_ip: str, count: int = 4, timeout_ms: int = 1000) -> dict[str, Any]:
    """Ejecuta ping ICMP multiplataforma y extrae pérdida y latencia."""
    system = platform.system()
    if system == "Windows":
        cmd = ["ping", "-n", str(count), "-w", str(timeout_ms), target_ip]
    elif system == "Darwin":
        cmd = ["ping", "-c", str(count), "-W", str(timeout_ms), target_ip]
    else:
        timeout_sec = max(1, timeout_ms // 1000)
        cmd = ["ping", "-c", str(count), "-W", str(timeout_sec), target_ip]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=(count * (timeout_ms / 1000.0)) + 5.0,
            check=False,
            **no_window_kwargs(),
        )
        output = f"{proc.stdout}\n{proc.stderr}"
    except (OSError, subprocess.SubprocessError) as exc:
        return {
            "reachable": False,
            "packet_loss_pct": 100.0,
            "rtt_min_ms": None,
            "rtt_avg_ms": None,
            "rtt_max_ms": None,
            "error": str(exc),
        }

    loss_match = re.search(
        r"(\d+(?:\.\d+)?)\s*%\s*(?:packet\s+loss|loss|perdidos)",
        output,
        re.IGNORECASE,
    )
    loss_pct = (
        float(loss_match.group(1))
        if loss_match
        else (0.0 if proc.returncode == 0 else 100.0)
    )

    rtt_min = rtt_avg = rtt_max = None
    unix_rtt = re.search(
        r"=\s*(\d+(?:\.\d+)?)/(\d+(?:\.\d+)?)/(\d+(?:\.\d+)?)(?:/\d+(?:\.\d+)?)?\s*ms",
        output,
    )
    if unix_rtt:
        rtt_min, rtt_avg, rtt_max = map(float, unix_rtt.groups())
    else:
        win_vals = re.findall(
            r"(?:Minimum|M[íi]nimo|Maximum|M[áa]ximo|Average|Media)\s*=\s*(\d+)\s*ms",
            output,
            re.IGNORECASE,
        )
        if len(win_vals) >= 3:
            rtt_min = float(win_vals[0])
            rtt_max = float(win_vals[1])
            rtt_avg = float(win_vals[2])

    return {
        "reachable": proc.returncode == 0 and loss_pct < 100.0,
        "packet_loss_pct": loss_pct,
        "rtt_min_ms": rtt_min,
        "rtt_avg_ms": rtt_avg,
        "rtt_max_ms": rtt_max,
    }


def get_arp_mac(target_ip: str) -> str | None:
    """Consulta la tabla ARP/Neighbor del SO para obtener la MAC de `target_ip`."""
    system = platform.system()
    commands: list[list[str]]
    if system == "Windows":
        commands = [["arp", "-a", target_ip]]
    elif system == "Darwin":
        commands = [["arp", "-n", target_ip]]
    else:
        commands = [["ip", "neigh", "show", target_ip], ["arp", "-n", target_ip]]

    mac_re = re.compile(r"([0-9a-fA-F]{1,2}(?:[:-][0-9a-fA-F]{1,2}){5})")
    for cmd in commands:
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=3.0,
                check=False,
                **no_window_kwargs(),
            )
        except (OSError, subprocess.SubprocessError):
            continue
        for line in proc.stdout.splitlines():
            if target_ip in line:
                match = mac_re.search(line)
                if match:
                    return match.group(1).lower().replace("-", ":")
    return None


def analyze_link_negotiation(
    link_info: dict[str, Any],
    nic_delta: dict[str, Any],
    expected_speed_mbps: int,
    role: str,
) -> dict[str, Any]:
    """Evalúa degradación PHY por software (ej. caída de 1000 a 100 Mbps) y correlación con errores."""
    speed = link_info.get("speed_mbps")
    duplex = link_info.get("duplex", "unknown")
    is_up = link_info.get("is_up")
    counters = nic_delta.get("counters", {})
    phys = nic_delta.get("os_physical_errors", {})

    total_nic_errors = sum(
        v
        for v in (
            counters.get("errin"),
            counters.get("errout"),
            counters.get("dropin"),
            counters.get("dropout"),
        )
        if isinstance(v, int)
    )
    total_crc_errors = phys.get("rx_crc_errors") or 0

    findings: list[str] = []
    status = "OK"

    if is_up is False:
        status = "FALLO"
        findings.append(f"[{role}] Interfaz reportada como caída (link down).")
    elif speed is not None and speed > 0 and speed < expected_speed_mbps:
        status = "DEGRADADO"
        hint = (
            "Posible fallo en pares 4-5 o 7-8 (en 1000BASE-T obliga a negociar 100BASE-TX) "
            "o puerto de switch limitado a Fast Ethernet."
            if expected_speed_mbps >= 1000 and speed <= 100
            else "Velocidad negociada inferior al umbral esperado."
        )
        findings.append(
            f"[{role}] Velocidad negociada {speed} Mbps < esperada {expected_speed_mbps} Mbps. {hint}"
        )

    if duplex == "half":
        status = "DEGRADADO" if status == "OK" else status
        findings.append(
            f"[{role}] Enlace negociado en Half-Duplex; riesgo alto de colisiones y latencia."
        )

    if total_nic_errors > 0 or total_crc_errors > 0:
        if status == "OK":
            status = "ADVERTENCIA"
        findings.append(
            f"[{role}] Errores/descartes detectados durante la prueba "
            f"(NIC={total_nic_errors}, CRC={total_crc_errors})."
        )

    return {
        "role": role,
        "status": status,
        "link_info": link_info,
        "total_nic_errors_delta": total_nic_errors,
        "rx_crc_errors_delta": phys.get("rx_crc_errors"),
        "findings": findings,
    }
