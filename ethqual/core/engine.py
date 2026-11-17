"""Motor orquestador del cliente de diagnóstico Ethernet (ethqual)."""

from __future__ import annotations

import datetime as dt
import os
import platform
import socket
import struct
import threading
import time
import zlib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ethqual.core.autotest import run_network_autotest
from ethqual.core.metrics import (
    analyze_link_negotiation,
    compute_nic_delta,
    detect_interface_by_ip,
    get_arp_mac,
    get_link_info,
    get_nic_snapshot,
    run_ping,
)
from ethqual.core.protocol import (
    BER_HEADER_FMT,
    UDP_HEADER_FMT,
    UDP_HEADER_SIZE,
    generate_deterministic_block,
    recv_control_msg,
    send_control_msg,
)
from ethqual.core.remediation import build_remediations


PRESET_PROFILES: dict[str, dict[str, Any]] = {
    "1000BASE-T Oficina": {
        "expected_speed_mbps": 1000,
        "min_throughput_mbps": 800.0,
        "streams": 2,
        "reverse": True,
        "full_duplex": False,
        "udp_jitter": False,
        "udp_sweep": False,
    },
    "2.5GBASE-T Enlace": {
        "expected_speed_mbps": 2500,
        "min_throughput_mbps": 2000.0,
        "streams": 4,
        "reverse": True,
        "full_duplex": True,
        "udp_jitter": False,
        "udp_sweep": False,
    },
    "VoIP / Streaming": {
        "expected_speed_mbps": 1000,
        "min_throughput_mbps": 100.0,
        "streams": 1,
        "reverse": False,
        "full_duplex": False,
        "udp_jitter": True,
        "udp_sweep": True,
    },
    "Estrés Full-Duplex": {
        "expected_speed_mbps": 1000,
        "min_throughput_mbps": 750.0,
        "streams": 4,
        "reverse": True,
        "full_duplex": True,
        "udp_jitter": False,
        "udp_sweep": True,
    },
}


@dataclass(slots=True)
class DiagnosticConfig:
    """Parámetros de ejecución para una batería de diagnóstico Ethernet."""

    server_ip: str
    port: int = 5000
    iface: str | None = None
    project_name: str = "Proyecto General"
    cable_id: str = "TOMA-01"
    technician: str = ""
    profile_name: str = "Personalizado"
    duration_s: int = 10
    streams: int = 1
    reverse: bool = False
    full_duplex: bool = False
    chunk_size: int = 65536
    ber_blocks: int = 500
    ber_block_size: int = 4096
    udp_jitter: bool = False
    udp_duration_s: int = 3
    udp_pps: int = 200
    udp_sweep: bool = False
    udp_sweep_sizes: tuple[int, ...] = (36, 256, 1400)
    udp_sweep_pps: tuple[int, ...] = (500, 2000, 5000)
    udp_sweep_duration_s: int = 1
    check_dhcp: bool = False
    expected_speed_mbps: int = 1000
    min_throughput_mbps: float = 100.0
    max_loss_pct: float = 1.0
    max_error_delta: int = 0

    def __post_init__(self) -> None:
        self.duration_s = max(1, min(600, int(self.duration_s)))
        self.streams = max(1, min(32, int(self.streams)))
        self.chunk_size = max(1024, min(4_194_304, int(self.chunk_size)))
        self.ber_blocks = max(1, int(self.ber_blocks))
        self.ber_block_size = max(64, min(16_777_216, int(self.ber_block_size)))


def _run_throughput_sender(
    server_ip: str,
    data_port: int,
    duration_s: int,
    chunk_size: int,
    streams: int = 1,
    cancel_event: threading.Event | None = None,
) -> dict[str, Any]:
    """Envía 1 o N flujos TCP paralelos durante `duration_s` segundos."""
    streams = max(1, streams)
    payload = os.urandom(chunk_size)
    byte_counts = [0] * streams
    errors: list[Exception] = []

    def _worker(idx: int, deadline: float) -> None:
        sent = 0
        try:
            with socket.create_connection((server_ip, data_port), timeout=15.0) as sock:
                sock.settimeout(15.0)
                while time.perf_counter() < deadline:
                    if cancel_event is not None and cancel_event.is_set():
                        break
                    sock.sendall(payload)
                    sent += chunk_size
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)
        byte_counts[idx] = sent

    start = time.perf_counter()
    deadline = start + duration_s
    threads = [
        threading.Thread(target=_worker, args=(i, deadline), daemon=True)
        for i in range(streams)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    if errors:
        raise errors[0]
    elapsed = max(1e-6, time.perf_counter() - start)

    total_bytes = sum(byte_counts)
    mbps = (total_bytes * 8.0) / (elapsed * 1_000_000.0)
    return {
        "streams": streams,
        "bytes_sent": total_bytes,
        "elapsed_s": round(elapsed, 4),
        "throughput_mbps": round(mbps, 2),
    }


def _run_throughput_receiver(
    server_ip: str, data_port: int, chunk_size: int, streams: int = 1
) -> dict[str, Any]:
    """Recibe 1 o N flujos TCP paralelos (Servidor -> Cliente) hasta EOF."""
    streams = max(1, streams)
    byte_counts = [0] * streams
    errors: list[Exception] = []

    def _worker(idx: int) -> None:
        total = 0
        try:
            with socket.create_connection((server_ip, data_port), timeout=15.0) as sock:
                sock.settimeout(30.0)
                while True:
                    data = sock.recv(chunk_size)
                    if not data:
                        break
                    total += len(data)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)
        byte_counts[idx] = total

    start = time.perf_counter()
    threads = [
        threading.Thread(target=_worker, args=(i,), daemon=True)
        for i in range(streams)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    if errors:
        raise errors[0]
    elapsed = max(1e-6, time.perf_counter() - start)

    total_bytes = sum(byte_counts)
    mbps = (total_bytes * 8.0) / (elapsed * 1_000_000.0)
    return {
        "streams": streams,
        "bytes_received": total_bytes,
        "elapsed_s": round(elapsed, 4),
        "throughput_mbps": round(mbps, 2),
    }


def _run_full_duplex_client(
    server_ip: str,
    rx_port: int,
    tx_port: int,
    duration_s: int,
    chunk_size: int,
    streams: int,
) -> dict[str, Any]:
    """Ejecuta transmisión y recepción TCP simultáneas (Full-Duplex real)."""
    out: dict[str, Any] = {}

    def _tx() -> None:
        out["client_tx"] = _run_throughput_sender(
            server_ip, rx_port, duration_s, chunk_size, streams
        )

    def _rx() -> None:
        out["client_rx"] = _run_throughput_receiver(
            server_ip, tx_port, chunk_size, streams
        )

    t_tx = threading.Thread(target=_tx, daemon=True)
    t_rx = threading.Thread(target=_rx, daemon=True)
    t_tx.start()
    t_rx.start()
    t_tx.join()
    t_rx.join()
    return out


def _run_ber_sender(
    server_ip: str, data_port: int, num_blocks: int, block_size: int
) -> dict[str, Any]:
    """Envía bloques deterministas con cabecera CRC32 para verificar integridad."""
    with socket.create_connection((server_ip, data_port), timeout=15.0) as data_sock:
        data_sock.settimeout(15.0)
        for seq_id in range(num_blocks):
            payload = generate_deterministic_block(seq_id, block_size)
            crc = zlib.crc32(payload) & 0xFFFFFFFF
            header = struct.pack(BER_HEADER_FMT, seq_id, block_size, crc)
            data_sock.sendall(header + payload)
    return {"blocks_sent": num_blocks, "block_size_bytes": block_size}


def _run_udp_jitter_sender(
    server_ip: str, data_port: int, duration_s: int, pps: int, packet_size: int = 256
) -> dict[str, Any]:
    """Envía datagramas UDP espaciados para medir pérdida y jitter en el servidor."""
    total_packets = max(1, duration_s * pps)
    interval_s = 1.0 / max(1, pps)
    padding = b"\xaa" * max(0, packet_size - UDP_HEADER_SIZE)

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp_sock:
        next_send = time.perf_counter()
        for seq_id in range(total_packets):
            now = time.perf_counter()
            if now < next_send:
                time.sleep(next_send - now)
            send_ts = time.perf_counter()
            pkt = struct.pack(UDP_HEADER_FMT, seq_id, send_ts) + padding
            udp_sock.sendto(pkt, (server_ip, data_port))
            next_send += interval_s

    return {
        "packets_sent": total_packets,
        "pps_target": pps,
        "packet_size_bytes": len(padding) + UDP_HEADER_SIZE,
    }


def evaluate_verdict(
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
    tcp_control_ok: bool = False,
) -> tuple[str, list[str]]:
    """Determina el veredicto global (APROBADO | ADVERTENCIA | FALLO) con reglas explícitas."""
    reasons: list[str] = []
    severity = 0

    if not connectivity.get("reachable"):
        if tcp_control_ok:
            severity = max(severity, 1)
            reasons.append("ICMP bloqueado/filtrado por firewall, pero el canal de control TCP respondió.")
        else:
            severity = max(severity, 2)
            reasons.append("Host remoto inalcanzable vía ICMP ping.")
    elif connectivity.get("packet_loss_pct", 0.0) > thresholds["max_packet_loss_pct"]:
        severity = max(severity, 2)
        reasons.append(
            f"Pérdida ICMP ({connectivity['packet_loss_pct']}%) supera el umbral "
            f"({thresholds['max_packet_loss_pct']}%)."
        )

    if throughput_mbps < thresholds["min_throughput_mbps"]:
        severity = max(severity, 2)
        reasons.append(
            f"Throughput efectivo ({throughput_mbps} Mbps) inferior al mínimo "
            f"({thresholds['min_throughput_mbps']} Mbps)."
        )

    if (
        reverse_throughput_mbps is not None
        and reverse_throughput_mbps < thresholds["min_throughput_mbps"]
    ):
        severity = max(severity, 2)
        reasons.append(
            f"Throughput reverso ({reverse_throughput_mbps} Mbps) inferior al mínimo "
            f"({thresholds['min_throughput_mbps']} Mbps)."
        )

    if (
        ber_results.get("corrupted_blocks", 0) > 0
        or ber_results.get("application_ber", 0.0) > thresholds["max_ber"]
    ):
        severity = max(severity, 2)
        reasons.append(
            f"Corrupción de datos en aplicación detectada: "
            f"{ber_results.get('corrupted_blocks')} bloques, BER={ber_results.get('application_ber')}."
        )

    if udp_jitter_results is not None:
        udp_loss = float(udp_jitter_results.get("loss_pct", 0.0))
        if udp_loss > thresholds["max_packet_loss_pct"]:
            severity = max(severity, 2)
            reasons.append(
                f"Pérdida UDP ({udp_loss}%) supera el umbral "
                f"({thresholds['max_packet_loss_pct']}%)."
            )

    if full_duplex_results is not None:
        fd_rx = float(full_duplex_results.get("server_rx", {}).get("throughput_mbps", 0.0))
        fd_tx = float(full_duplex_results.get("client_rx", {}).get("throughput_mbps", 0.0))
        if min(fd_rx, fd_tx) < thresholds["min_throughput_mbps"]:
            severity = max(severity, 2)
            reasons.append(
                f"Throughput Full-Duplex ({fd_rx} / {fd_tx} Mbps) inferior al mínimo "
                f"({thresholds['min_throughput_mbps']} Mbps)."
            )

    if udp_sweep_results:
        worst = max(udp_sweep_results, key=lambda x: float(x.get("server_rx", {}).get("loss_pct", 0.0)))
        worst_loss = float(worst.get("server_rx", {}).get("loss_pct", 0.0))
        if worst_loss > thresholds["max_packet_loss_pct"]:
            severity = max(severity, 2)
            reasons.append(
                f"Barrido UDP ({worst['packet_size_bytes']}B @ {worst['pps_target']}pps): "
                f"pérdida {worst_loss}% supera el umbral ({thresholds['max_packet_loss_pct']}%)."
            )

    for phy in (client_phy, server_phy):
        if phy["status"] == "FALLO":
            severity = max(severity, 2)
            reasons.extend(phy["findings"])
        elif phy["status"] == "DEGRADADO":
            severity = max(severity, 1)
            reasons.extend(phy["findings"])
        elif phy["total_nic_errors_delta"] > thresholds["max_nic_error_delta"]:
            severity = max(severity, 1)
            reasons.extend(phy["findings"])

    verdict_map = {0: "APROBADO", 1: "ADVERTENCIA", 2: "FALLO"}
    return verdict_map[severity], reasons


def write_markdown_summary(path: str, report: dict[str, Any]) -> None:
    """Exporta un resumen legible en Markdown a partir del reporte consolidado."""
    meta = report["metadata"]
    tests = report["tests"]
    conn = tests["connectivity_layer2"]
    tp_rx = tests["throughput"]["server_rx"]
    tp_rev = tests["throughput"].get("reverse")
    tp_dup = tests["throughput"].get("full_duplex")
    ber = tests["data_integrity_ber"]["server_rx"]
    udp = tests.get("udp_jitter")
    phy_c = report["phy_link_diagnosis"]["client"]
    phy_s = report["phy_link_diagnosis"]["server"]

    lines = [
        f"# Reporte de Cualificación Ethernet — {report['verdict']}",
        "",
        f"- **Fecha (UTC):** {meta['timestamp_utc']}",
        f"- **Cliente:** {meta['client']['hostname']} (`{meta['client']['ip']}` / `{meta['client']['interface']}`)",
        f"- **Servidor:** {meta['server']['hostname']} (`{meta['server']['ip']}` / `{meta['server']['interface']}`)",
        "",
        "## Resultados",
        "| Prueba | Métrica | Valor |",
        "| :--- | :--- | :--- |",
        f"| Conectividad ICMP | Pérdida / RTT medio | {conn['packet_loss_pct']}% / {conn['rtt_avg_ms']} ms |",
        f"| Capa 2 (ARP) | MAC resuelta | `{conn['arp_mac'] or 'N/A'}` |",
        f"| Throughput TCP (C→S) | Ancho de banda RX ({tp_rx.get('streams', 1)} flujos) | {tp_rx.get('throughput_mbps')} Mbps |",
    ]
    if tp_rev:
        lines.append(
            f"| Throughput TCP (S→C) | Ancho de banda RX ({tp_rev['client_rx'].get('streams', 1)} flujos) | {tp_rev['client_rx'].get('throughput_mbps')} Mbps |"
        )
    if tp_dup:
        lines.append(
            f"| Full-Duplex Simultáneo | C→S RX / S→C RX | {tp_dup['server_rx'].get('throughput_mbps')} / {tp_dup['client_rx'].get('throughput_mbps')} Mbps |"
        )
    lines.append(
        f"| Integridad (BER App) | Bloques corruptos / BER | {ber.get('corrupted_blocks')} / {ber.get('application_ber')} |"
    )
    if udp:
        urx = udp["server_rx"]
        lines.append(
            f"| UDP Jitter | Pérdida / Jitter | {urx.get('loss_pct')}% / {urx.get('jitter_ms')} ms |"
        )
    if tests.get("udp_sweep"):
        worst = max(tests["udp_sweep"], key=lambda x: float(x["server_rx"].get("loss_pct", 0.0)))
        lines.append(
            f"| Barrido UDP (RFC 2544) | Peor pérdida / Jitter | {worst['server_rx'].get('loss_pct')}% ({worst['packet_size_bytes']}B@{worst['pps_target']}pps) / {worst['server_rx'].get('jitter_ms')} ms |"
        )
    lines.extend([
        f"| Enlace PHY Cliente | Velocidad / Dúplex / Estado | {phy_c['link_info'].get('speed_mbps')} Mbps / {phy_c['link_info'].get('duplex')} / {phy_c['status']} |",
        f"| Enlace PHY Servidor | Velocidad / Dúplex / Estado | {phy_s['link_info'].get('speed_mbps')} Mbps / {phy_s['link_info'].get('duplex')} / {phy_s['status']} |",
    ])
    if report["verdict_reasons"]:
        lines.extend(["", "## Motivos del Veredicto"])
        lines.extend(f"- {r}" for r in report["verdict_reasons"])
    if report.get("remediations"):
        lines.extend(["", "## Acciones Correctivas / Remediales"])
        for rem in report["remediations"]:
            lines.append(
                f"- **[{rem['severity']}] {rem['issue']}** — *Causa:* {rem['cause']} → *Acción:* {rem['action']}"
            )

    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_diagnostic(
    cfg: DiagnosticConfig,
    on_progress: Callable[[int, str], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> dict[str, Any]:
    """Ejecuta la batería completa de pruebas y devuelve el diccionario del reporte."""
    execution_log: list[dict[str, Any]] = []

    def check_cancelled() -> None:
        if cancel_event is not None and cancel_event.is_set():
            raise RuntimeError("Diagnóstico cancelado por el usuario.")

    def notify(pct: int, text: str) -> None:
        check_cancelled()
        execution_log.append({
            "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "progress_pct": pct,
            "message": text,
        })
        if on_progress is not None:
            on_progress(pct, text)

    streams = max(1, cfg.streams)
    thresholds = {
        "expected_link_speed_mbps": cfg.expected_speed_mbps,
        "min_throughput_mbps": cfg.min_throughput_mbps,
        "max_packet_loss_pct": cfg.max_loss_pct,
        "max_nic_error_delta": cfg.max_error_delta,
        "max_ber": 0.0,
    }

    notify(10, "[1/5] Ejecutando prueba de conectividad ICMP y resolución ARP...")
    ping_res = run_ping(cfg.server_ip)
    arp_mac = get_arp_mac(cfg.server_ip)

    notify(25, f"[2/5] Conectando al canal de control {cfg.server_ip}:{cfg.port}...")
    with socket.create_connection((cfg.server_ip, cfg.port), timeout=15.0) as ctrl:
        ctrl.settimeout(60.0)
        local_ip = ctrl.getsockname()[0]
        local_iface = cfg.iface or detect_interface_by_ip(local_ip)
        local_link = get_link_info(local_iface).to_dict()

        send_control_msg(ctrl, {"cmd": "HELLO"})
        hello_resp = recv_control_msg(ctrl)

        client_snap_before = get_nic_snapshot(local_iface).to_dict()
        send_control_msg(ctrl, {"cmd": "SNAPSHOT_NIC", "label": "before"})
        server_snap_before = recv_control_msg(ctrl)["snapshot"]

        notify(40, f"[3/5] Throughput TCP ({cfg.duration_s} s, {streams} flujos)...")
        send_control_msg(
            ctrl,
            {
                "cmd": "START_THROUGHPUT",
                "chunk_size": cfg.chunk_size,
                "streams": streams,
            },
        )
        tp_ready = recv_control_msg(ctrl)
        client_tp = _run_throughput_sender(
            cfg.server_ip,
            tp_ready["data_port"],
            cfg.duration_s,
            cfg.chunk_size,
            streams,
            cancel_event=cancel_event,
        )

        client_tp_rev: dict[str, Any] | None = None
        if cfg.reverse:
            notify(55, f"[3b/5] Throughput Reverso ({cfg.duration_s} s, {streams} flujos)...")
            send_control_msg(
                ctrl,
                {
                    "cmd": "START_THROUGHPUT_REVERSE",
                    "duration_s": cfg.duration_s,
                    "chunk_size": cfg.chunk_size,
                    "streams": streams,
                },
            )
            tp_rev_ready = recv_control_msg(ctrl)
            client_tp_rev = _run_throughput_receiver(
                cfg.server_ip, tp_rev_ready["data_port"], cfg.chunk_size, streams
            )

        client_tp_dup: dict[str, Any] | None = None
        if cfg.full_duplex:
            notify(65, f"[3c/5] Full-Duplex simultáneo ({cfg.duration_s} s, {streams} flujos)...")
            send_control_msg(
                ctrl,
                {
                    "cmd": "START_THROUGHPUT_DUPLEX",
                    "duration_s": cfg.duration_s,
                    "chunk_size": cfg.chunk_size,
                    "streams": streams,
                },
            )
            dup_ready = recv_control_msg(ctrl)
            client_tp_dup = _run_full_duplex_client(
                cfg.server_ip,
                dup_ready["rx_port"],
                dup_ready["tx_port"],
                cfg.duration_s,
                cfg.chunk_size,
                streams,
            )

        notify(78, f"[4/5] Integridad / BER ({cfg.ber_blocks} bloques)...")
        send_control_msg(ctrl, {"cmd": "START_BER"})
        ber_ready = recv_control_msg(ctrl)
        client_ber = _run_ber_sender(
            cfg.server_ip, ber_ready["data_port"], cfg.ber_blocks, cfg.ber_block_size
        )

        client_udp: dict[str, Any] | None = None
        if cfg.udp_jitter:
            expected_pkts = max(1, cfg.udp_duration_s * cfg.udp_pps)
            notify(88, f"[4b/5] UDP Jitter ({cfg.udp_duration_s} s @ {cfg.udp_pps} pps)...")
            send_control_msg(
                ctrl,
                {
                    "cmd": "START_UDP_JITTER",
                    "duration_s": cfg.udp_duration_s,
                    "expected_packets": expected_pkts,
                },
            )
            udp_ready = recv_control_msg(ctrl)
            client_udp = _run_udp_jitter_sender(
                cfg.server_ip, udp_ready["data_port"], cfg.udp_duration_s, cfg.udp_pps
            )

        udp_sweep_entries: list[dict[str, Any]] | None = None
        if cfg.udp_sweep:
            udp_sweep_entries = []
            combos = [(sz, pps) for sz in cfg.udp_sweep_sizes for pps in cfg.udp_sweep_pps]
            for idx, (sz, pps) in enumerate(combos, start=1):
                notify(
                    89 + min(5, idx),
                    f"[4c/5] Barrido UDP ({idx}/{len(combos)}): {sz} B @ {pps} pps...",
                )
                expected_pkts = max(1, cfg.udp_sweep_duration_s * pps)
                send_control_msg(
                    ctrl,
                    {
                        "cmd": "START_UDP_JITTER",
                        "duration_s": cfg.udp_sweep_duration_s,
                        "expected_packets": expected_pkts,
                    },
                )
                sw_ready = recv_control_msg(ctrl)
                sw_tx = _run_udp_jitter_sender(
                    cfg.server_ip,
                    sw_ready["data_port"],
                    cfg.udp_sweep_duration_s,
                    pps,
                    packet_size=sz,
                )
                send_control_msg(ctrl, {"cmd": "GET_RESULTS"})
                sw_rx = recv_control_msg(ctrl)["results"].get("udp_jitter", {})
                udp_sweep_entries.append(
                    {
                        "packet_size_bytes": sw_tx["packet_size_bytes"],
                        "pps_target": pps,
                        "client_tx": sw_tx,
                        "server_rx": sw_rx,
                    }
                )

        notify(95, "[5/5] Telemetría final de NICs, AutoTest y consolidación...")
        client_snap_after = get_nic_snapshot(local_iface).to_dict()
        send_control_msg(ctrl, {"cmd": "SNAPSHOT_NIC", "label": "after"})
        server_snap_after = recv_control_msg(ctrl)["snapshot"]

        send_control_msg(ctrl, {"cmd": "GET_RESULTS"})
        server_results = recv_control_msg(ctrl)["results"]
        send_control_msg(ctrl, {"cmd": "BYE"})
        recv_control_msg(ctrl)

    autotest_res = run_network_autotest(
        local_iface,
        target_ip=cfg.server_ip,
        check_dhcp=cfg.check_dhcp,
    )

    client_delta = compute_nic_delta(client_snap_before, client_snap_after)
    server_delta = compute_nic_delta(server_snap_before, server_snap_after)
    client_phy = analyze_link_negotiation(local_link, client_delta, cfg.expected_speed_mbps, "cliente")
    server_phy = analyze_link_negotiation(hello_resp["link_info"], server_delta, cfg.expected_speed_mbps, "servidor")

    effective_mbps = float(server_results.get("throughput", {}).get("throughput_mbps", 0.0))
    reverse_mbps = (
        float(client_tp_rev["throughput_mbps"]) if client_tp_rev is not None else None
    )
    ber_metrics = server_results.get("ber", {})
    udp_rx_metrics = server_results.get("udp_jitter") if client_udp is not None else None
    srv_dup = server_results.get("throughput_duplex")
    fd_combined = (
        {
            "server_rx": srv_dup.get("server_rx", {}),
            "client_rx": client_tp_dup.get("client_rx", {}),
        }
        if client_tp_dup is not None and srv_dup is not None
        else None
    )
    verdict, reasons = evaluate_verdict(
        ping_res,
        effective_mbps,
        ber_metrics,
        client_phy,
        server_phy,
        thresholds,
        reverse_throughput_mbps=reverse_mbps,
        udp_jitter_results=udp_rx_metrics,
        full_duplex_results=fd_combined,
        udp_sweep_results=udp_sweep_entries,
        tcp_control_ok=True,
    )
    remediations = build_remediations(
        ping_res,
        effective_mbps,
        ber_metrics,
        client_phy,
        server_phy,
        thresholds,
        reverse_throughput_mbps=reverse_mbps,
        udp_jitter_results=udp_rx_metrics,
        full_duplex_results=fd_combined,
        udp_sweep_results=udp_sweep_entries,
        autotest_results=autotest_res,
    )

    notify(100, f"Diagnóstico finalizado — Veredicto: {verdict}")
    return {
        "metadata": {
            "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "tool": "ethqual",
            "project_name": cfg.project_name,
            "cable_id": cfg.cable_id,
            "technician": cfg.technician,
            "profile_name": cfg.profile_name,
            "client": {
                "hostname": socket.gethostname(),
                "os": platform.system(),
                "ip": local_ip,
                "interface": local_iface,
            },
            "server": {
                "hostname": hello_resp.get("hostname"),
                "os": hello_resp.get("os"),
                "ip": hello_resp.get("server_ip"),
                "interface": hello_resp.get("interface"),
            },
        },
        "thresholds": thresholds,
        "tests": {
            "connectivity_layer2": {**ping_res, "arp_mac": arp_mac},
            "throughput": {
                "client_tx": client_tp,
                "server_rx": server_results.get("throughput", {}),
                "reverse": (
                    {
                        "server_tx": server_results.get("throughput_reverse", {}),
                        "client_rx": client_tp_rev,
                    }
                    if client_tp_rev is not None
                    else None
                ),
                "full_duplex": (
                    {
                        "server_rx": srv_dup.get("server_rx", {}),
                        "client_rx": client_tp_dup.get("client_rx", {}),
                    }
                    if client_tp_dup is not None and srv_dup is not None
                    else None
                ),
            },
            "data_integrity_ber": {
                "note": "Mide errores en capa de aplicación (memoria/bus/driver); TCP retransmite errores L2.",
                "client_tx": client_ber,
                "server_rx": ber_metrics,
            },
            "udp_jitter": (
                {
                    "client_tx": client_udp,
                    "server_rx": udp_rx_metrics,
                }
                if client_udp is not None
                else None
            ),
            "udp_sweep": udp_sweep_entries,
        },
        "nic_telemetry_delta": {
            "client": client_delta,
            "server": server_delta,
        },
        "phy_link_diagnosis": {
            "tdr_software_supported": bool(autotest_res["ethtool_cable_test"].get("supported")),
            "client": client_phy,
            "server": server_phy,
        },
        "network_autotest": autotest_res,
        "verdict": verdict,
        "verdict_reasons": reasons,
        "remediations": remediations,
        "execution_log": execution_log,
    }


def run_soak_test(
    cfg: DiagnosticConfig,
    rounds: int = 3,
    interval_s: int = 60,
    on_progress: Callable[[int, str], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> dict[str, Any]:
    """Ejecuta múltiples rondas periódicas para detectar degradación térmica o intermitente."""
    rounds = max(1, rounds)
    interval_s = max(0, interval_s)
    round_reports: list[dict[str, Any]] = []

    for idx in range(1, rounds + 1):
        if cancel_event is not None and cancel_event.is_set():
            raise RuntimeError("Soak Test cancelado por el usuario.")
        if on_progress is not None:
            on_progress(
                int(((idx - 1) / rounds) * 100),
                f"[Soak Test] Iniciando ronda {idx}/{rounds}...",
            )
        rep = run_diagnostic(cfg, on_progress=None, cancel_event=cancel_event)
        round_reports.append(rep)
        tp = rep["tests"]["throughput"]["server_rx"].get("throughput_mbps", 0.0)
        if on_progress is not None:
            on_progress(
                int((idx / rounds) * 100),
                f"[Soak Test] Ronda {idx}/{rounds} -> {rep['verdict']} ({tp} Mbps)",
            )
        if idx < rounds and interval_s > 0:
            if cancel_event is not None:
                if cancel_event.wait(interval_s):
                    raise RuntimeError("Soak Test cancelado durante la espera.")
            else:
                time.sleep(interval_s)

    tps = [
        float(r["tests"]["throughput"]["server_rx"].get("throughput_mbps", 0.0))
        for r in round_reports
    ]
    verdicts = [r["verdict"] for r in round_reports]
    overall = "FALLO" if "FALLO" in verdicts else ("ADVERTENCIA" if "ADVERTENCIA" in verdicts else "APROBADO")

    # Devuelve el último reporte enriquecido con el resumen de tendencia del Soak Test
    final_report = dict(round_reports[-1])
    final_report["verdict"] = overall
    final_report["soak_summary"] = {
        "rounds_completed": len(round_reports),
        "interval_s": interval_s,
        "passed_rounds": verdicts.count("APROBADO"),
        "warned_rounds": verdicts.count("ADVERTENCIA"),
        "failed_rounds": verdicts.count("FALLO"),
        "min_throughput_mbps": min(tps) if tps else 0.0,
        "max_throughput_mbps": max(tps) if tps else 0.0,
        "avg_throughput_mbps": round(sum(tps) / len(tps), 2) if tps else 0.0,
    }
    return final_report
