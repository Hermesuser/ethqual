"""CLI del servidor pasivo de diagnóstico Ethernet (ethqual)."""

from __future__ import annotations

import argparse
import platform
import socket

from ethqual.core.discovery import ServerBeacon
from ethqual.core.server_engine import handle_client_session


def main() -> None:
    parser = argparse.ArgumentParser(description="Servidor de diagnóstico Ethernet ethqual")
    parser.add_argument("--host", default="0.0.0.0", help="IP de escucha (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=5000, help="Puerto de control TCP (default: 5000)")
    parser.add_argument("--iface", default=None, help="Forzar nombre de interfaz NIC (opcional)")
    args = parser.parse_args()

    beacon = ServerBeacon(tcp_port=args.port)
    beacon.start()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((args.host, args.port))
        srv.listen(4)
        print(f"[ethqual-server] Escuchando en {args.host}:{args.port} (SO: {platform.system()})")
        try:
            while True:
                conn, addr = srv.accept()
                print(f"[ethqual-server] Sesión iniciada desde {addr[0]}:{addr[1]}")
                with conn:
                    handle_client_session(conn, args.iface)
                print(f"[ethqual-server] Sesión finalizada ({addr[0]}:{addr[1]})")
        except KeyboardInterrupt:
            print("\n[ethqual-server] Detenido por el usuario.")
        finally:
            beacon.stop()


if __name__ == "__main__":
    main()
