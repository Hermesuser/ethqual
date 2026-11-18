"""Pruebas unitarias y de integración local para ethqual."""

from __future__ import annotations

import socket
import struct
import sys
import unittest
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ethqual.core.discovery import ServerBeacon, discover_servers, run_port_blink
from ethqual.core.engine import DiagnosticConfig, evaluate_verdict
from ethqual.core.metrics import analyze_link_negotiation, compute_nic_delta
from ethqual.core.protocol import (
    BER_HEADER_FMT,
    ProtocolError,
    count_bit_differences,
    generate_deterministic_block,
    recv_control_msg,
    send_control_msg,
)
from ethqual.core.remediation import build_remediations
from ethqual.core.reports import write_html_report, write_labels_csv, write_labels_html


class TestProtocol(unittest.TestCase):
    def test_control_message_roundtrip(self) -> None:
        s1, s2 = socket.socketpair()
        with s1, s2:
            payload = {"cmd": "HELLO", "seq": 1, "tags": ["a", "b"]}
            send_control_msg(s1, payload)
            received = recv_control_msg(s2)
            self.assertEqual(received, payload)

    def test_invalid_control_length_raises(self) -> None:
        s1, s2 = socket.socketpair()
        with s1, s2:
            s1.sendall(struct.pack("!I", 0))
            with self.assertRaises(ProtocolError):
                recv_control_msg(s2)

    def test_deterministic_block_and_bit_diff(self) -> None:
        b1 = generate_deterministic_block(42, 128)
        b2 = generate_deterministic_block(42, 128)
        self.assertEqual(b1, b2)
        self.assertEqual(len(b1), 128)

        corrupted = bytes([b1[0] ^ 0b00000101]) + b1[1:]
        self.assertEqual(count_bit_differences(b1, corrupted), 2)
        self.assertNotEqual(zlib.crc32(b1), zlib.crc32(corrupted))
        self.assertEqual(struct.calcsize(BER_HEADER_FMT), 16)


class TestMetricsAndVerdict(unittest.TestCase):
    def test_nic_delta_handles_reset(self) -> None:
        before = {
            "interface": "eth0",
            "errin": 10,
            "errout": 0,
            "dropin": 2,
            "dropout": 0,
            "bytes_sent": 1000,
            "bytes_recv": 2000,
            "packets_sent": 10,
            "packets_recv": 20,
            "os_physical_errors": {"rx_crc_errors": 1},
        }
        after = {
            "interface": "eth0",
            "errin": 4,  # menor que before (simula reset)
            "errout": 1,
            "dropin": 5,
            "dropout": 0,
            "bytes_sent": 2500,
            "bytes_recv": 2000,
            "packets_sent": 25,
            "packets_recv": 20,
            "os_physical_errors": {"rx_crc_errors": 3},
        }
        delta = compute_nic_delta(before, after)
        self.assertEqual(delta["counters"]["errin"], 0)
        self.assertEqual(delta["counters"]["errout"], 1)
        self.assertEqual(delta["counters"]["dropin"], 3)
        self.assertEqual(delta["os_physical_errors"]["rx_crc_errors"], 2)

    def test_link_degradation_1000_to_100(self) -> None:
        link = {"interface": "eth0", "is_up": True, "speed_mbps": 100, "duplex": "full", "mtu": 1500}
        delta = {"counters": {"errin": 0, "errout": 0, "dropin": 0, "dropout": 0}, "os_physical_errors": {}}
        res = analyze_link_negotiation(link, delta, expected_speed_mbps=1000, role="cliente")
        self.assertEqual(res["status"], "DEGRADADO")
        self.assertTrue(any("4-5 o 7-8" in f for f in res["findings"]))

    def test_evaluate_verdict_states(self) -> None:
        thresholds = {
            "expected_link_speed_mbps": 1000,
            "min_throughput_mbps": 500.0,
            "max_packet_loss_pct": 1.0,
            "max_nic_error_delta": 0,
            "max_ber": 0.0,
        }
        ok_phy = {"status": "OK", "total_nic_errors_delta": 0, "findings": []}
        deg_phy = {"status": "DEGRADADO", "total_nic_errors_delta": 0, "findings": ["100 Mbps"]}
        ok_conn = {"reachable": True, "packet_loss_pct": 0.0}
        ok_ber = {"corrupted_blocks": 0, "application_ber": 0.0}

        verdict, _ = evaluate_verdict(ok_conn, 920.0, ok_ber, ok_phy, ok_phy, thresholds)
        self.assertEqual(verdict, "APROBADO")

        verdict, _ = evaluate_verdict(ok_conn, 920.0, ok_ber, deg_phy, ok_phy, thresholds)
        self.assertEqual(verdict, "ADVERTENCIA")

        bad_ber = {"corrupted_blocks": 1, "application_ber": 1e-5}
        verdict, _ = evaluate_verdict(ok_conn, 920.0, bad_ber, ok_phy, ok_phy, thresholds)
        self.assertEqual(verdict, "FALLO")

        verdict, reasons = evaluate_verdict(
            ok_conn, 920.0, ok_ber, ok_phy, ok_phy, thresholds, reverse_throughput_mbps=95.0
        )
        self.assertEqual(verdict, "FALLO")
        self.assertTrue(any("Throughput reverso" in r for r in reasons))

        verdict, reasons = evaluate_verdict(
            ok_conn,
            920.0,
            ok_ber,
            ok_phy,
            ok_phy,
            thresholds,
            udp_jitter_results={"loss_pct": 2.5, "jitter_ms": 0.4},
        )
        self.assertEqual(verdict, "FALLO")
        self.assertTrue(any("Pérdida UDP" in r for r in reasons))

        verdict, reasons = evaluate_verdict(
            ok_conn,
            920.0,
            ok_ber,
            ok_phy,
            ok_phy,
            thresholds,
            full_duplex_results={
                "server_rx": {"throughput_mbps": 450.0},
                "client_rx": {"throughput_mbps": 900.0},
            },
        )
        self.assertEqual(verdict, "FALLO")
        self.assertTrue(any("Full-Duplex" in r for r in reasons))

        verdict, reasons = evaluate_verdict(
            ok_conn,
            920.0,
            ok_ber,
            ok_phy,
            ok_phy,
            thresholds,
            udp_sweep_results=[
                {"packet_size_bytes": 36, "pps_target": 5000, "server_rx": {"loss_pct": 3.2}}
            ],
        )
        self.assertEqual(verdict, "FALLO")
        self.assertTrue(any("Barrido UDP" in r for r in reasons))

    def test_build_remediations_for_100m_degradation(self) -> None:
        thresholds = {
            "expected_link_speed_mbps": 1000,
            "min_throughput_mbps": 500.0,
            "max_packet_loss_pct": 1.0,
            "max_nic_error_delta": 0,
            "max_ber": 0.0,
        }
        deg_phy = {
            "role": "cliente",
            "status": "DEGRADADO",
            "link_info": {"is_up": True, "speed_mbps": 100, "duplex": "full"},
            "total_nic_errors_delta": 0,
            "rx_crc_errors_delta": 0,
        }
        ok_phy = {
            "role": "servidor",
            "status": "OK",
            "link_info": {"is_up": True, "speed_mbps": 1000, "duplex": "full"},
            "total_nic_errors_delta": 0,
            "rx_crc_errors_delta": 0,
        }
        rems = build_remediations(
            {"reachable": True, "packet_loss_pct": 0.0},
            94.0,
            {"corrupted_blocks": 0},
            deg_phy,
            ok_phy,
            thresholds,
        )
        self.assertTrue(any("4-5" in r["cause"] for r in rems))
        self.assertTrue(any("umbral mínimo" in r["issue"] for r in rems))

    def test_filtered_icmp_with_tcp_ok_is_warning(self) -> None:
        thresholds = {
            "expected_link_speed_mbps": 1000,
            "min_throughput_mbps": 100.0,
            "max_packet_loss_pct": 1.0,
            "max_nic_error_delta": 0,
            "max_ber": 0.0,
        }
        ok_phy = {"status": "OK", "total_nic_errors_delta": 0, "findings": []}
        verdict, reasons = evaluate_verdict(
            {"reachable": False, "packet_loss_pct": 100.0},
            900.0,
            {"corrupted_blocks": 0, "application_ber": 0.0},
            ok_phy,
            ok_phy,
            thresholds,
            tcp_control_ok=True,
        )
        self.assertEqual(verdict, "ADVERTENCIA")
        self.assertTrue(any("ICMP bloqueado" in r for r in reasons))

    def test_diagnostic_config_clamps_bounds(self) -> None:
        cfg = DiagnosticConfig(server_ip="127.0.0.1", duration_s=0, streams=999, chunk_size=10)
        self.assertEqual(cfg.duration_s, 1)
        self.assertEqual(cfg.streams, 32)
        self.assertEqual(cfg.chunk_size, 1024)

    def test_discovery_beacon_and_port_blink(self) -> None:
        beacon = ServerBeacon(tcp_port=5099, listen_port=15001)
        beacon.start()
        beacon.wait_ready(timeout=2.0)
        try:
            servers = discover_servers(timeout_s=0.6, discovery_port=15001)
            self.assertTrue(any(s["port"] == 5099 for s in servers))
        finally:
            beacon.stop()
            beacon.join(timeout=1.5)

        pulses: list[bool] = []
        run_port_blink("127.0.0.1", duration_s=1, port=15009, on_pulse=pulses.append)
        self.assertIn(True, pulses)

    def test_html_and_csv_reports(self) -> None:
        import tempfile

        sample = {
            "metadata": {"project_name": "Obra X", "cable_id": "T-01", "technician": "Ana", "profile_name": "1G", "timestamp_utc": "2026-11-17T00:00:00Z"},
            "tests": {"connectivity_layer2": {"rtt_avg_ms": 0.3, "packet_loss_pct": 0.0}, "throughput": {"server_rx": {"throughput_mbps": 930.0}}, "data_integrity_ber": {"server_rx": {"corrupted_blocks": 0}}},
            "phy_link_diagnosis": {"client": {"link_info": {"speed_mbps": 1000}}, "server": {"link_info": {"speed_mbps": 1000}}},
            "network_autotest": {"lldp": {"neighbors": [{"switch_name": "SW-CORE", "port_id": "Gi1/0/5", "vlan_id": 10}]}},
            "verdict": "APROBADO",
            "verdict_reasons": [],
            "remediations": [],
        }
        with tempfile.TemporaryDirectory() as tmp:
            html_p = Path(tmp) / "rep.html"
            csv_p = Path(tmp) / "labels.csv"
            lbl_html_p = Path(tmp) / "labels.html"
            write_html_report(str(html_p), [sample])
            write_labels_csv(str(csv_p), [sample])
            write_labels_html(str(lbl_html_p), [sample])
            html_txt = html_p.read_text(encoding="utf-8")
            self.assertIn("T-01", html_txt)
            self.assertIn("SW-CORE / Gi1/0/5", html_txt)
            self.assertIn("<svg", html_txt)
            self.assertIn("viewport", html_txt)
            self.assertIn("table-wrap", html_txt)
            self.assertIn("Obra X,T-01,APROBADO,1000,930.0", csv_p.read_text(encoding="utf-8"))
            lbl_txt = lbl_html_p.read_text(encoding="utf-8")
            self.assertIn("<svg", lbl_txt)
            self.assertIn("@media(max-width:720px)", lbl_txt)

    def test_diagnostic_cancel_event(self) -> None:
        import threading
        from ethqual.core.engine import run_diagnostic, run_soak_test

        ev = threading.Event()
        ev.set()
        cfg = DiagnosticConfig(server_ip="127.0.0.1")
        with self.assertRaises(RuntimeError):
            run_diagnostic(cfg, cancel_event=ev)
        with self.assertRaises(RuntimeError):
            run_soak_test(cfg, rounds=2, interval_s=1, cancel_event=ev)

    def test_recv_ok_or_raise_handles_server_error(self) -> None:
        from ethqual.core.engine import _recv_ok_or_raise

        s1, s2 = socket.socketpair()
        with s1, s2:
            send_control_msg(s1, {"status": "ERROR", "error": "puerto ocupado"})
            with self.assertRaises(RuntimeError) as ctx:
                _recv_ok_or_raise(s2)
            self.assertIn("puerto ocupado", str(ctx.exception))

    def test_remediation_for_ip_conflict_and_dhcp(self) -> None:
        thresholds = {
            "expected_link_speed_mbps": 1000,
            "min_throughput_mbps": 100.0,
            "max_packet_loss_pct": 1.0,
            "max_nic_error_delta": 0,
            "max_ber": 0.0,
        }
        ok_phy = {"role": "cliente", "status": "OK", "link_info": {"is_up": True, "speed_mbps": 1000, "duplex": "full"}, "total_nic_errors_delta": 0}
        rems = build_remediations(
            {"reachable": True, "packet_loss_pct": 0.0},
            900.0,
            {"corrupted_blocks": 0},
            ok_phy,
            ok_phy,
            thresholds,
            autotest_results={
                "arp_conflict": {"conflict_detected": True, "target_ip": "192.168.1.50", "macs": ["aa:bb:cc:dd:ee:01", "aa:bb:cc:dd:ee:02"]},
                "dhcp_scan": {"multiple_dhcp_detected": True, "servers": ["192.168.1.1", "192.168.1.254"]},
            },
        )
        self.assertTrue(any("Conflicto de IP" in r["issue"] for r in rems))
        self.assertTrue(any("servidores DHCP" in r["issue"] for r in rems))


if __name__ == "__main__":
    unittest.main()
