"""Descubrimiento pasivo LLDP / CDP de switch, puerto y VLAN."""

from __future__ import annotations

import json
import platform
import re
import shutil
import subprocess
from typing import Any

from ethqual.core.metrics import no_window_kwargs


def get_lldp_neighbor(iface: str | None) -> dict[str, Any]:
    """Consulta vecinos LLDP vía lldpctl o networkctl en Linux; degrada seguro en otros SO."""
    if platform.system() != "Linux":
        return {
            "supported": False,
            "reason": f"Consulta LLDP nativa del SO no disponible en {platform.system()} sin daemon lldpd.",
            "neighbors": [],
        }
    if not iface or iface == "lo":
        return {"supported": False, "reason": "Interfaz no válida o loopback.", "neighbors": []}

    lldpctl = shutil.which("lldpctl")
    if lldpctl:
        try:
            proc = subprocess.run(
                [lldpctl, "-f", "json", iface],
                capture_output=True,
                text=True,
                timeout=3.0,
                check=False,
                **no_window_kwargs(),
            )
            if proc.returncode == 0 and proc.stdout.strip():
                data = json.loads(proc.stdout)
                ifaces = data.get("lldp", {}).get("interface", [])
                neighbors: list[dict[str, Any]] = []
                for entry in ifaces if isinstance(ifaces, list) else [ifaces]:
                    if isinstance(entry, dict):
                        for _ifname, info in entry.items():
                            chassis = info.get("chassis", {})
                            port = info.get("port", {})
                            vlan = info.get("vlan", {})
                            neighbors.append({
                                "switch_name": next(iter(chassis.keys()), None) if isinstance(chassis, dict) else None,
                                "port_id": port.get("id", {}).get("value") if isinstance(port, dict) else None,
                                "port_descr": port.get("descr") if isinstance(port, dict) else None,
                                "vlan_id": vlan.get("vlan-id") if isinstance(vlan, dict) else None,
                            })
                return {"supported": True, "source": "lldpctl", "neighbors": neighbors}
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
            pass

    networkctl = shutil.which("networkctl")
    if networkctl:
        try:
            proc = subprocess.run(
                [networkctl, "lldp", iface],
                capture_output=True,
                text=True,
                timeout=3.0,
                check=False,
                **no_window_kwargs(),
            )
            if proc.returncode == 0 and proc.stdout.strip():
                neighbors = []
                for line in proc.stdout.splitlines()[1:]:
                    parts = re.split(r"\s{2,}", line.strip())
                    if len(parts) >= 3:
                        neighbors.append({
                            "switch_name": parts[2] if len(parts) > 2 else None,
                            "port_id": parts[3] if len(parts) > 3 else None,
                            "port_descr": parts[4] if len(parts) > 4 else None,
                            "vlan_id": None,
                        })
                return {"supported": True, "source": "networkctl", "neighbors": neighbors}
        except (OSError, subprocess.SubprocessError):
            pass

    return {
        "supported": False,
        "reason": "No se encontró lldpctl ni networkctl activo en el sistema.",
        "neighbors": [],
    }
