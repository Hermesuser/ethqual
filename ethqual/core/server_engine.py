"""Motor de servidor concurrente para pruebas de flujo paralelo, Full-Duplex, BER y UDP."""

from __future__ import annotations

import os
import platform
import socket
import struct
import threading
import time
import zlib
from typing import Any

from ethqual.core.metrics import detect_interface_by_ip, get_link_info, get_nic_snapshot
from ethqual.core.protocol import (
    BER_HEADER_FMT,
    BER_HEADER_SIZE,
    ProtocolError,
    UDP_HEADER_FMT,
    UDP_HEADER_SIZE,
    count_bit_differences,
    generate_deterministic_block,
    recv_control_msg,
    recv_exact,
    send_control_msg,
)


MAX_STREAMS = 32
MIN_CHUNK_SIZE = 1024
MAX_CHUNK_SIZE = 4_194_304
MAX_BER_PAYLOAD = 16_777_216


def _clamp_streams(val: Any) -> int:
    return max(1, min(MAX_STREAMS, int(val)))


def _clamp_chunk_size(val: Any) -> int:
    return max(MIN_CHUNK_SIZE, min(MAX_CHUNK_SIZE, int(val)))


def _open_ephemeral_data_socket(bind_ip: str, backlog: int = 8) -> tuple[socket.socket, int]:
    """Abre un socket TCP efímero en puerto 0 listo para aceptar N flujos paralelos."""
    data_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    data_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    data_sock.bind((bind_ip, 0))
    data_sock.listen(max(4, backlog))
    data_sock.settimeout(15.0)
    _, port = data_sock.getsockname()
    return data_sock, int(port)


def _open_ephemeral_udp_socket(bind_ip: str) -> tuple[socket.socket, int]:
    """Abre un socket UDP efímero en puerto 0 para pruebas de jitter y pérdida."""
    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_sock.bind((bind_ip, 0))
    udp_sock.settimeout(5.0)
    _, port = udp_sock.getsockname()
    return udp_sock, int(port)


def _run_throughput_receiver(
    data_sock: socket.socket, chunk_size: int, streams: int = 1
) -> dict[str, Any]:
    """Recibe 1 o N flujos TCP paralelos hasta EOF y calcula el throughput agregado."""
    streams = _clamp_streams(streams)
    chunk_size = _clamp_chunk_size(chunk_size)
    conns: list[socket.socket] = []
    byte_counts: list[int] = [0] * streams
    workers_started = False

    def _worker(idx: int, conn: socket.socket) -> None:
        total = 0
        with conn:
            conn.settimeout(30.0)
            while True:
                data = conn.recv(chunk_size)
                if not data:
                    break
                total += len(data)
        byte_counts[idx] = total

    try:
        for _ in range(streams):
            conn, _ = data_sock.accept()
            conns.append(conn)
        start = time.perf_counter()
        threads = [
            threading.Thread(target=_worker, args=(i, c), daemon=True)
            for i, c in enumerate(conns)
        ]
        workers_started = True
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        elapsed = max(1e-6, time.perf_counter() - start)
    finally:
        if not workers_started:
            for c in conns:
                c.close()
        data_sock.close()

    total_bytes = sum(byte_counts)
    mbps = (total_bytes * 8.0) / (elapsed * 1_000_000.0)
    return {
        "streams": streams,
        "bytes_received": total_bytes,
        "elapsed_s": round(elapsed, 4),
        "throughput_mbps": round(mbps, 2),
    }


def _run_throughput_sender(
    data_sock: socket.socket, duration_s: int, chunk_size: int, streams: int = 1
) -> dict[str, Any]:
    """Envía 1 o N flujos TCP paralelos hacia el cliente durante `duration_s` segundos."""
    streams = _clamp_streams(streams)
    chunk_size = _clamp_chunk_size(chunk_size)
    payload = os.urandom(chunk_size)
    conns: list[socket.socket] = []
    byte_counts: list[int] = [0] * streams
    workers_started = False

    def _worker(idx: int, conn: socket.socket, deadline: float) -> None:
        sent = 0
        with conn:
            conn.settimeout(30.0)
            while time.perf_counter() < deadline:
                conn.sendall(payload)
                sent += chunk_size
        byte_counts[idx] = sent

    try:
        for _ in range(streams):
            conn, _ = data_sock.accept()
            conns.append(conn)
        start = time.perf_counter()
        deadline = start + duration_s
        threads = [
            threading.Thread(target=_worker, args=(i, c, deadline), daemon=True)
            for i, c in enumerate(conns)
        ]
        workers_started = True
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        elapsed = max(1e-6, time.perf_counter() - start)
    finally:
        if not workers_started:
            for c in conns:
                c.close()
        data_sock.close()

    total_bytes = sum(byte_counts)
    mbps = (total_bytes * 8.0) / (elapsed * 1_000_000.0)
    return {
        "streams": streams,
        "bytes_sent": total_bytes,
        "elapsed_s": round(elapsed, 4),
        "throughput_mbps": round(mbps, 2),
    }


def _run_full_duplex_server(
    rx_sock: socket.socket,
    tx_sock: socket.socket,
    duration_s: int,
    chunk_size: int,
    streams: int,
) -> dict[str, Any]:
    """Ejecuta recepción y transmisión TCP simultáneas (Full-Duplex real)."""
    results: dict[str, Any] = {}

    def _rx() -> None:
        results["server_rx"] = _run_throughput_receiver(rx_sock, chunk_size, streams)

    def _tx() -> None:
        results["server_tx"] = _run_throughput_sender(tx_sock, duration_s, chunk_size, streams)

    t_rx = threading.Thread(target=_rx, daemon=True)
    t_tx = threading.Thread(target=_tx, daemon=True)
    t_rx.start()
    t_tx.start()
    t_rx.join()
    t_tx.join()
    return results


def _run_ber_receiver(data_sock: socket.socket) -> dict[str, Any]:
    """Recibe bloques con cabecera fija, valida CRC32 y cuantifica errores de bit."""
    blocks_received = 0
    corrupted_blocks = 0
    total_bits = 0
    bit_errors = 0

    try:
        conn, _ = data_sock.accept()
        with conn:
            conn.settimeout(30.0)
            while True:
                try:
                    header = recv_exact(conn, BER_HEADER_SIZE)
                except EOFError:
                    break
                seq_id, payload_len, expected_crc = struct.unpack(BER_HEADER_FMT, header)
                if payload_len > MAX_BER_PAYLOAD:
                    raise ProtocolError(f"Bloque BER excede límite máximo: {payload_len}")
                payload = recv_exact(conn, payload_len)
                blocks_received += 1
                total_bits += payload_len * 8

                actual_crc = zlib.crc32(payload) & 0xFFFFFFFF
                if actual_crc != expected_crc:
                    corrupted_blocks += 1
                    expected_payload = generate_deterministic_block(seq_id, payload_len)
                    bit_errors += count_bit_differences(expected_payload, payload)
    finally:
        data_sock.close()

    ber = (bit_errors / total_bits) if total_bits > 0 else 0.0
    return {
        "blocks_received": blocks_received,
        "corrupted_blocks": corrupted_blocks,
        "total_bits": total_bits,
        "bit_errors": bit_errors,
        "application_ber": ber,
    }


def _run_udp_jitter_receiver(
    udp_sock: socket.socket, duration_s: int, expected_packets: int
) -> dict[str, Any]:
    """Recibe datagramas UDP y calcula pérdida, desorden y jitter RFC 3550 (ms)."""
    received = 0
    out_of_order = 0
    last_seq = -1
    prev_send_ts: float | None = None
    prev_recv_ts: float | None = None
    jitter_s = 0.0
    deadline = time.perf_counter() + duration_s + 2.0

    try:
        while time.perf_counter() < deadline:
            try:
                data, _ = udp_sock.recvfrom(4096)
            except socket.timeout:
                if received > 0:
                    break
                continue
            recv_ts = time.perf_counter()
            if len(data) < UDP_HEADER_SIZE:
                continue
            seq_id, send_ts = struct.unpack(UDP_HEADER_FMT, data[:UDP_HEADER_SIZE])
            received += 1
            if received == 1:
                udp_sock.settimeout(0.8)
            if seq_id <= last_seq:
                out_of_order += 1
            else:
                last_seq = seq_id

            if prev_send_ts is not None and prev_recv_ts is not None:
                transit_diff = abs((recv_ts - prev_recv_ts) - (send_ts - prev_send_ts))
                jitter_s += (transit_diff - jitter_s) / 16.0
            prev_send_ts = send_ts
            prev_recv_ts = recv_ts
    finally:
        udp_sock.close()

    total_expected = max(expected_packets, last_seq + 1 if last_seq >= 0 else 0)
    lost = max(0, total_expected - received)
    loss_pct = round((lost / total_expected) * 100.0, 3) if total_expected > 0 else 0.0
    return {
        "expected_packets": total_expected,
        "packets_received": received,
        "lost_packets": lost,
        "loss_pct": loss_pct,
        "out_of_order": out_of_order,
        "jitter_ms": round(jitter_s * 1000.0, 4),
    }


def _run_wiggle_echo(udp_sock: socket.socket, max_duration_s: int = 120) -> dict[str, Any]:
    """Eco UDP de baja latencia para Wiggle Test en vivo hasta inactividad de 2.5s."""
    echoed = 0
    udp_sock.settimeout(2.5)
    deadline = time.perf_counter() + max(5, min(300, max_duration_s))
    try:
        while time.perf_counter() < deadline:
            try:
                data, addr = udp_sock.recvfrom(2048)
            except socket.timeout:
                if echoed > 0:
                    break
                continue
            if data == b"WIGGLE_STOP":
                break
            try:
                udp_sock.sendto(data, addr)
                echoed += 1
            except OSError:
                break
    finally:
        udp_sock.close()
    return {"echoed_packets": echoed}


def handle_client_session(ctrl_conn: socket.socket, forced_iface: str | None) -> None:
    """Atiende la secuencia de comandos de control de una sesión de diagnóstico."""
    local_ip = ctrl_conn.getsockname()[0]
    iface = forced_iface or detect_interface_by_ip(local_ip)
    session_metrics: dict[str, Any] = {}

    ctrl_conn.settimeout(60.0)
    while True:
        try:
            msg = recv_control_msg(ctrl_conn)
        except (EOFError, ProtocolError, socket.timeout):
            break

        cmd = msg.get("cmd")
        if cmd == "HELLO":
            send_control_msg(
                ctrl_conn,
                {
                    "status": "OK",
                    "os": platform.system(),
                    "hostname": socket.gethostname(),
                    "server_ip": local_ip,
                    "interface": iface,
                    "link_info": get_link_info(iface).to_dict(),
                },
            )
        elif cmd == "SNAPSHOT_NIC":
            label = str(msg.get("label", "unknown"))
            snap = get_nic_snapshot(iface).to_dict()
            session_metrics[f"nic_{label}"] = snap
            send_control_msg(ctrl_conn, {"status": "OK", "snapshot": snap})
        elif cmd == "START_THROUGHPUT":
            chunk_size = _clamp_chunk_size(msg.get("chunk_size", 65536))
            streams = _clamp_streams(msg.get("streams", 1))
            data_sock, data_port = _open_ephemeral_data_socket(local_ip, backlog=streams)
            send_control_msg(ctrl_conn, {"status": "READY", "data_port": data_port})
            session_metrics["throughput"] = _run_throughput_receiver(
                data_sock, chunk_size, streams
            )
        elif cmd == "START_THROUGHPUT_REVERSE":
            duration_s = max(1, min(600, int(msg.get("duration_s", 10))))
            chunk_size = _clamp_chunk_size(msg.get("chunk_size", 65536))
            streams = _clamp_streams(msg.get("streams", 1))
            data_sock, data_port = _open_ephemeral_data_socket(local_ip, backlog=streams)
            send_control_msg(ctrl_conn, {"status": "READY", "data_port": data_port})
            session_metrics["throughput_reverse"] = _run_throughput_sender(
                data_sock, duration_s, chunk_size, streams
            )
        elif cmd == "START_THROUGHPUT_DUPLEX":
            duration_s = max(1, min(600, int(msg.get("duration_s", 10))))
            chunk_size = _clamp_chunk_size(msg.get("chunk_size", 65536))
            streams = _clamp_streams(msg.get("streams", 1))
            rx_sock, rx_port = _open_ephemeral_data_socket(local_ip, backlog=streams)
            tx_sock, tx_port = _open_ephemeral_data_socket(local_ip, backlog=streams)
            send_control_msg(
                ctrl_conn,
                {"status": "READY", "rx_port": rx_port, "tx_port": tx_port},
            )
            session_metrics["throughput_duplex"] = _run_full_duplex_server(
                rx_sock, tx_sock, duration_s, chunk_size, streams
            )
        elif cmd == "START_BER":
            data_sock, data_port = _open_ephemeral_data_socket(local_ip)
            send_control_msg(ctrl_conn, {"status": "READY", "data_port": data_port})
            session_metrics["ber"] = _run_ber_receiver(data_sock)
        elif cmd == "START_UDP_JITTER":
            duration_s = int(msg.get("duration_s", 3))
            expected_packets = int(msg.get("expected_packets", 600))
            udp_sock, udp_port = _open_ephemeral_udp_socket(local_ip)
            send_control_msg(ctrl_conn, {"status": "READY", "data_port": udp_port})
            session_metrics["udp_jitter"] = _run_udp_jitter_receiver(
                udp_sock, duration_s, expected_packets
            )
        elif cmd == "START_WIGGLE":
            max_dur = int(msg.get("max_duration_s", 120))
            udp_sock, udp_port = _open_ephemeral_udp_socket(local_ip)
            send_control_msg(ctrl_conn, {"status": "READY", "data_port": udp_port})
            session_metrics["wiggle"] = _run_wiggle_echo(udp_sock, max_dur)
        elif cmd == "GET_RESULTS":
            send_control_msg(ctrl_conn, {"status": "OK", "results": session_metrics})
        elif cmd == "BYE":
            send_control_msg(ctrl_conn, {"status": "OK"})
            break
        else:
            send_control_msg(
                ctrl_conn, {"status": "ERROR", "error": f"Comando desconocido: {cmd}"}
            )
