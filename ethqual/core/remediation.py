"""Motor de diagnóstico de causas probables y acciones remediales en campo."""

from __future__ import annotations

from typing import Any


def build_remediations(
    connectivity: dict[str, Any],
    throughput_mbps: float,
    ber_results: dict[str, Any],
    client_phy: dict[str, Any],
    server_phy: dict[str, Any],
    thresholds: dict[str, Any],
    reverse_throughput_mbps: float | None = None,
    udp_jitter_results: dict[str, Any] | None = None,
    full_duplex_results: dict[str, Any] | None = None,
    udp_sweep_results: list[dict[str, Any]] | None = None,
    autotest_results: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    """Genera recomendaciones accionables según los fallos o advertencias detectados."""
    remedials: list[dict[str, str]] = []

    if not connectivity.get("reachable"):
        remedials.append({
            "severity": "FALLO",
            "issue": "Equipo servidor inalcanzable vía ICMP",
            "cause": "Cable desconectado, IPs en distinta subred o firewall bloqueando ICMP/TCP.",
            "action": (
                "1) Verificar LEDs de enlace en ambas NICs. 2) Confirmar IP estática en la misma subred "
                "(ej. 192.168.50.10 y 192.168.50.20 /24). 3) Permitir ICMP y puerto TCP 5000 en el firewall."
            ),
        })
    elif float(connectivity.get("packet_loss_pct", 0.0)) > thresholds["max_packet_loss_pct"]:
        remedials.append({
            "severity": "FALLO",
            "issue": f"Pérdida de paquetes ICMP ({connectivity.get('packet_loss_pct')}%)",
            "cause": "Falso contacto en conector RJ45/keystone, cable dañado o interferencia electromagnética.",
            "action": (
                "1) Reemplazar patch cords en ambos extremos. 2) Re-ponchar el jack/plug revisando "
                "el orden T568A/T568B. 3) Alejar el tendido de fuentes eléctricas."
            ),
        })

    for phy in (client_phy, server_phy):
        role = phy.get("role", "equipo")
        link = phy.get("link_info", {})
        speed = link.get("speed_mbps")
        expected = thresholds.get("expected_link_speed_mbps", 1000)

        if link.get("is_up") is False:
            remedials.append({
                "severity": "FALLO",
                "issue": f"Enlace físico caído en {role}",
                "cause": "Interfaz deshabilitada o ausencia total de portadora eléctrica.",
                "action": "Verificar que el cable esté firmemente conectado y la interfaz habilitada en el SO.",
            })
        elif speed is not None and 0 < speed < expected:
            remedials.append({
                "severity": "ADVERTENCIA",
                "issue": f"Degradación de velocidad en {role} ({speed} Mbps vs {expected} Mbps)",
                "cause": "En 1000BASE-T, un corte o falso contacto en pares 4-5 (azul) o 7-8 (marrón) fuerza caída a 100 Mbps.",
                "action": (
                    "1) Inspeccionar y re-ponchar pares 4-5 y 7-8 en ambos extremos. "
                    "2) Verificar que el puerto del switch o adaptador USB-Ethernet soporte Gigabit."
                ),
            })

        if link.get("duplex") == "half":
            remedials.append({
                "severity": "ADVERTENCIA",
                "issue": f"Negociación Half-Duplex en {role}",
                "cause": "Falta de autonegociación en uno de los extremos o puerto de switch mal configurado.",
                "action": "Activar Autonegociación (Auto-Negotiation) en la tarjeta de red y en el switch.",
            })

        if phy.get("total_nic_errors_delta", 0) > thresholds["max_nic_error_delta"] or (phy.get("rx_crc_errors_delta") or 0) > 0:
            remedials.append({
                "severity": "ADVERTENCIA",
                "issue": f"Errores físicos/descartes de trama en NIC de {role}",
                "cause": "Tramas corruptas por cableado marginal, ruido eléctrico (EMI) o congestión de búfer.",
                "action": "Probar con otro patch cord certificado Cat6; si persiste en el enlace permanente, revisar ponchado o ruta del cable.",
            })

    if throughput_mbps < thresholds["min_throughput_mbps"] or (
        reverse_throughput_mbps is not None and reverse_throughput_mbps < thresholds["min_throughput_mbps"]
    ):
        remedials.append({
            "severity": "FALLO",
            "issue": "Rendimiento TCP por debajo del umbral mínimo",
            "cause": "Enlace degradado a 100 Mbps, congestión, adaptador USB limitado a USB 2.0 o 1 solo flujo TCP insuficiente.",
            "action": (
                "1) Confirmar negociación a 1000+ Mbps. 2) Usar adaptador Ethernet USB 3.0/PCIe nativo. "
                "3) Probar aumentando flujos paralelos (--streams 4)."
            ),
        })

    if full_duplex_results is not None:
        fd_rx = float(full_duplex_results.get("server_rx", {}).get("throughput_mbps", 0.0))
        fd_tx = float(full_duplex_results.get("client_rx", {}).get("throughput_mbps", 0.0))
        if min(fd_rx, fd_tx) < thresholds["min_throughput_mbps"]:
            remedials.append({
                "severity": "FALLO",
                "issue": f"Caída de rendimiento en Full-Duplex simultáneo ({fd_rx} / {fd_tx} Mbps)",
                "cause": "Posible diafonía severa (NEXT) entre pares bajo carga bidireccional o cuello de botella CPU/NIC.",
                "action": "Revisar destrenzado excesivo (>13 mm) en conectores RJ45/keystones y repetir prueba con cable corto conocido bueno.",
            })

    if ber_results.get("corrupted_blocks", 0) > 0:
        remedials.append({
            "severity": "FALLO",
            "issue": f"Corrupción de datos en capa de aplicación ({ber_results.get('corrupted_blocks')} bloques)",
            "cause": "Fallo en memoria RAM, bus PCIe/USB, o bug del controlador de red (TCP retransmite errores de cable).",
            "action": "Actualizar driver de la NIC, cambiar de puerto USB/adaptador o validar memoria RAM del equipo.",
        })

    udp_bad = False
    if udp_jitter_results is not None and float(udp_jitter_results.get("loss_pct", 0.0)) > thresholds["max_packet_loss_pct"]:
        udp_bad = True
    if udp_sweep_results:
        for step in udp_sweep_results:
            if float(step.get("server_rx", {}).get("loss_pct", 0.0)) > thresholds["max_packet_loss_pct"]:
                udp_bad = True
                break
    if udp_bad:
        remedials.append({
            "severity": "FALLO",
            "issue": "Pérdida de datagramas UDP en prueba de estrés / barrido",
            "cause": "Micro-cortes físicos, ahorro de energía EEE (Energy Efficient Ethernet) o saturación de cola RX.",
            "action": "Desactivar Energy Efficient Ethernet (EEE/Green Ethernet) en el driver de la NIC y verificar conectores.",
        })

    if autotest_results:
        arp_c = autotest_results.get("arp_conflict", {})
        if arp_c.get("conflict_detected"):
            remedials.append({
                "severity": "FALLO",
                "issue": f"Conflicto de IP detectado en {arp_c.get('target_ip')}",
                "cause": f"Múltiples direcciones MAC ({', '.join(arp_c.get('macs', []))}) responden por la misma IP.",
                "action": "Localizar el equipo duplicado en la red o asignar una IP estática libre.",
            })
        dhcp_s = autotest_results.get("dhcp_scan", {})
        if dhcp_s.get("multiple_dhcp_detected"):
            remedials.append({
                "severity": "ADVERTENCIA",
                "issue": f"Múltiples servidores DHCP detectados ({', '.join(dhcp_s.get('servers', []))})",
                "cause": "Posible router doméstico conectado por error (Rogue DHCP) entregando IPs en la red.",
                "action": "Desconectar el servidor DHCP no autorizado o habilitar DHCP Snooping en el switch.",
            })

    return remedials
