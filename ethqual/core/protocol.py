"""Protocolo binario/JSON de control y utilidades de integridad para ethqual."""

from __future__ import annotations

import hashlib
import json
import socket
import struct
from typing import Any

# Cabecera de control: longitud del payload JSON en 4 bytes unsigned int (big-endian)
CONTROL_HEADER_FMT = "!I"
CONTROL_HEADER_SIZE = struct.calcsize(CONTROL_HEADER_FMT)
MAX_CONTROL_PAYLOAD_BYTES = 1_048_576  # 1 MiB

# Cabecera de bloque BER: seq_id (uint64), payload_len (uint32), crc32 (uint32)
BER_HEADER_FMT = "!QII"
BER_HEADER_SIZE = struct.calcsize(BER_HEADER_FMT)

# Cabecera de datagrama UDP Jitter: seq_id (uint64), send_ts_s (float64)
UDP_HEADER_FMT = "!Qd"
UDP_HEADER_SIZE = struct.calcsize(UDP_HEADER_FMT)


class ProtocolError(Exception):
    """Error de framing o deserialización en el protocolo de control."""


def recv_exact(sock: socket.socket, num_bytes: int) -> bytes:
    """Lee exactamente `num_bytes` del socket o lanza EOFError si se cierra antes."""
    chunks: list[bytes] = []
    remaining = num_bytes
    while remaining > 0:
        chunk = sock.recv(remaining)
        if not chunk:
            raise EOFError(
                f"Conexión cerrada prematuramente; faltaban {remaining} bytes."
            )
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def send_control_msg(sock: socket.socket, payload: dict[str, Any]) -> None:
    """Serializa un diccionario a JSON y lo envía precedido por su longitud."""
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    if len(raw) > MAX_CONTROL_PAYLOAD_BYTES:
        raise ProtocolError("Mensaje de control excede el tamaño máximo permitido.")
    header = struct.pack(CONTROL_HEADER_FMT, len(raw))
    sock.sendall(header + raw)


def recv_control_msg(sock: socket.socket) -> dict[str, Any]:
    """Lee un mensaje de control con cabecera de longitud fija y lo decodifica."""
    header = recv_exact(sock, CONTROL_HEADER_SIZE)
    (length,) = struct.unpack(CONTROL_HEADER_FMT, header)
    if length == 0 or length > MAX_CONTROL_PAYLOAD_BYTES:
        raise ProtocolError(f"Longitud de mensaje de control inválida: {length}")
    raw = recv_exact(sock, length)
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProtocolError(f"Payload JSON inválido: {exc}") from exc
    if not isinstance(data, dict):
        raise ProtocolError("El mensaje de control debe ser un objeto JSON.")
    return data


def generate_deterministic_block(seq_id: int, size: int) -> bytes:
    """Genera un bloque determinista de `size` bytes a partir del `seq_id`."""
    digest = hashlib.sha256(seq_id.to_bytes(8, "big")).digest()
    repeats = (size // len(digest)) + 1
    return (digest * repeats)[:size]


def count_bit_differences(expected: bytes, actual: bytes) -> int:
    """Cuenta los bits distintos entre dos buffers usando XOR y bit_count()."""
    min_len = min(len(expected), len(actual))
    diff_bits = (
        int.from_bytes(expected[:min_len], "big")
        ^ int.from_bytes(actual[:min_len], "big")
    ).bit_count()
    diff_bits += abs(len(expected) - len(actual)) * 8
    return diff_bits
