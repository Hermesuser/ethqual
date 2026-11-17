"""CLI del cliente orquestador de diagnóstico Ethernet (ethqual)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ethqual.core.discovery import discover_servers, run_port_blink
from ethqual.core.engine import (
    PRESET_PROFILES,
    DiagnosticConfig,
    evaluate_verdict,
    run_diagnostic,
    run_soak_test,
    write_markdown_summary,
)
from ethqual.core.reports import write_html_report, write_labels_csv

__all__ = ["DiagnosticConfig", "evaluate_verdict", "run_diagnostic", "write_markdown_summary", "main"]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Cliente orquestador de diagnóstico Ethernet ethqual"
    )
    parser.add_argument("--server", required=False, help="Dirección IP del servidor")
    parser.add_argument("--discover", action="store_true", help="Buscar servidores ethqual activos en la red local")
    parser.add_argument("--blink", type=int, default=0, help="Enviar ráfagas Port Blink durante N segundos para identificar el puerto en el switch")
    parser.add_argument("--port", type=int, default=5000, help="Puerto de control TCP (default: 5000)")
    parser.add_argument("--iface", default=None, help="Forzar interfaz NIC local (opcional)")
    parser.add_argument("--project", default="Proyecto General", help="Nombre del proyecto u obra")
    parser.add_argument("--cable-id", default="TOMA-01", help="Identificador de la toma o enlace")
    parser.add_argument("--technician", default="", help="Nombre del técnico responsable")
    parser.add_argument("--profile", choices=list(PRESET_PROFILES.keys()), default=None, help="Perfil preconfigurado de cualificación")
    parser.add_argument("--duration", type=int, default=10, help="Duración de prueba throughput en s (default: 10)")
    parser.add_argument("--streams", type=int, default=1, help="Flujos TCP paralelos (default: 1)")
    parser.add_argument("--reverse", action="store_true", help="Ejecutar también prueba de throughput reverso (Servidor -> Cliente)")
    parser.add_argument("--full-duplex", action="store_true", help="Ejecutar prueba de carga Full-Duplex simultánea")
    parser.add_argument("--chunk-size", type=int, default=65536, help="Tamaño de chunk TCP en bytes (default: 65536)")
    parser.add_argument("--ber-blocks", type=int, default=500, help="Cantidad de bloques BER (default: 500)")
    parser.add_argument("--ber-block-size", type=int, default=4096, help="Tamaño de bloque BER en bytes (default: 4096)")
    parser.add_argument("--udp-jitter", action="store_true", help="Ejecutar prueba adicional de pérdida y jitter UDP")
    parser.add_argument("--udp-duration", type=int, default=3, help="Duración de prueba UDP en s (default: 3)")
    parser.add_argument("--udp-pps", type=int, default=200, help="Paquetes por segundo UDP (default: 200)")
    parser.add_argument("--udp-sweep", action="store_true", help="Ejecutar barrido UDP por tamaño de trama y tasa PPS (estilo RFC 2544)")
    parser.add_argument("--udp-sweep-sizes", default="36,256,1400", help="Tamaños de payload UDP en bytes separados por coma (default: 36,256,1400)")
    parser.add_argument("--udp-sweep-pps", default="500,2000,5000", help="Tasas PPS del barrido separadas por coma (default: 500,2000,5000)")
    parser.add_argument("--check-dhcp", action="store_true", help="Escanear servidores DHCP en LAN (puede requerir root)")
    parser.add_argument("--soak-rounds", type=int, default=1, help="Número de rondas para Soak Test prolongado (default: 1)")
    parser.add_argument("--soak-interval", type=int, default=60, help="Segundos de espera entre rondas de Soak Test (default: 60)")
    parser.add_argument("--expected-speed", type=int, default=1000, help="Velocidad nominal esperada en Mbps (default: 1000)")
    parser.add_argument("--min-throughput", type=float, default=100.0, help="Umbral mínimo de throughput en Mbps (default: 100.0)")
    parser.add_argument("--max-loss", type=float, default=1.0, help="Umbral máximo de pérdida ICMP %% (default: 1.0)")
    parser.add_argument("--max-error-delta", type=int, default=0, help="Umbral máximo de errores NIC delta (default: 0)")
    parser.add_argument("--output", default="reporte.json", help="Ruta del archivo de salida JSON (default: reporte.json)")
    parser.add_argument("--summary-md", default=None, help="Ruta opcional para exportar resumen legible en Markdown")
    parser.add_argument("--report-html", default=None, help="Ruta opcional para exportar reporte imprimible HTML estilo LinkWare")
    parser.add_argument("--labels-csv", default=None, help="Ruta opcional para exportar etiquetas CSV de patch panel")
    args = parser.parse_args()

    if args.discover:
        servers = discover_servers()
        if not servers:
            print("No se encontraron servidores ethqual en la red local.")
        else:
            for srv in servers:
                print(f"Servidor encontrado: {srv['hostname']} ({srv['os']}) -> {srv['ip']}:{srv['port']}")
        if not args.server:
            return

    if not args.server:
        parser.error("Se requiere --server <IP> (o usa --discover para buscar servidores).")

    if args.blink > 0:
        print(f"Enviando patrón Port Blink hacia {args.server} durante {args.blink} s...")
        run_port_blink(args.server, duration_s=args.blink)
        print("Port Blink finalizado.")
        return

    preset = PRESET_PROFILES.get(args.profile, {}) if args.profile else {}
    cfg = DiagnosticConfig(
        server_ip=args.server,
        port=args.port,
        iface=args.iface,
        project_name=args.project,
        cable_id=args.cable_id,
        technician=args.technician,
        profile_name=args.profile or "Personalizado",
        duration_s=args.duration,
        streams=preset.get("streams", args.streams),
        reverse=preset.get("reverse", args.reverse),
        full_duplex=preset.get("full_duplex", args.full_duplex),
        chunk_size=args.chunk_size,
        ber_blocks=args.ber_blocks,
        ber_block_size=args.ber_block_size,
        udp_jitter=preset.get("udp_jitter", args.udp_jitter),
        udp_duration_s=args.udp_duration,
        udp_pps=args.udp_pps,
        udp_sweep=preset.get("udp_sweep", args.udp_sweep),
        udp_sweep_sizes=tuple(int(x.strip()) for x in args.udp_sweep_sizes.split(",") if x.strip()),
        udp_sweep_pps=tuple(int(x.strip()) for x in args.udp_sweep_pps.split(",") if x.strip()),
        check_dhcp=args.check_dhcp,
        expected_speed_mbps=preset.get("expected_speed_mbps", args.expected_speed),
        min_throughput_mbps=preset.get("min_throughput_mbps", args.min_throughput),
        max_loss_pct=args.max_loss,
        max_error_delta=args.max_error_delta,
    )
    if args.soak_rounds > 1:
        report = run_soak_test(
            cfg,
            rounds=args.soak_rounds,
            interval_s=args.soak_interval,
            on_progress=lambda _pct, msg: print(msg),
        )
    else:
        report = run_diagnostic(cfg, on_progress=lambda _pct, msg: print(msg))

    Path(args.output).write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    if args.summary_md:
        write_markdown_summary(args.summary_md, report)
    if args.report_html:
        write_html_report(args.report_html, [report])
    if args.labels_csv:
        write_labels_csv(args.labels_csv, [report])

    verdict = report["verdict"]
    effective_mbps = report["tests"]["throughput"]["server_rx"].get("throughput_mbps", 0.0)
    loss_pct = report["tests"]["connectivity_layer2"].get("packet_loss_pct", 0.0)
    ber_val = report["tests"]["data_integrity_ber"]["server_rx"].get("application_ber", 0.0)
    print(f"\n=== VEREDICTO GLOBAL: {verdict} ===")
    print(f"Throughput RX: {effective_mbps} Mbps | Pérdida ICMP: {loss_pct}% | BER App: {ber_val}")
    for r in report["verdict_reasons"]:
        print(f"  - {r}")
    print(f"Reporte guardado en: {args.output}")


if __name__ == "__main__":
    main()
