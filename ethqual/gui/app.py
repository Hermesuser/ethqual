"""Interfaz gráfica nativa multiplataforma (PySide6) para ethqual."""

from __future__ import annotations

import json
import platform
import re
import socket
import sys
import threading
from pathlib import Path
from typing import Any

import psutil
from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ethqual.core.discovery import ServerBeacon, discover_servers, run_port_blink
from ethqual.core.engine import (
    PRESET_PROFILES,
    DiagnosticConfig,
    run_diagnostic,
    run_soak_test,
    write_markdown_summary,
)
from ethqual.core.protocol import recv_control_msg, send_control_msg
from ethqual.core.reports import write_html_report, write_labels_csv, write_labels_html
from ethqual.core.server_engine import handle_client_session

APP_STYLESHEET = """
QMainWindow, QWidget {
    background-color: #0F1115;
    color: #E6EAF2;
    font-family: -apple-system, "Segoe UI Variable", "Segoe UI", "Inter", "Noto Sans", sans-serif;
    font-size: 13px;
}
QFrame#Card {
    background-color: #161920;
    border: 1px solid #252A34;
    border-radius: 12px;
}
QFrame#VerdictNeutral {
    background-color: #161920;
    border: 1px solid #252A34;
    border-radius: 12px;
}
QFrame#VerdictPass {
    background-color: #0E231C;
    border: 1px solid #10B981;
    border-radius: 12px;
}
QFrame#VerdictWarn {
    background-color: #251D0F;
    border: 1px solid #F59E0B;
    border-radius: 12px;
}
QFrame#VerdictFail {
    background-color: #261215;
    border: 1px solid #EF4444;
    border-radius: 12px;
}
QLabel#Title {
    font-size: 18px;
    font-weight: 700;
    color: #F8FAFC;
}
QLabel#Subtitle {
    font-size: 12px;
    color: #8B95A7;
}
QLabel#CardTitle {
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.6px;
    color: #8B95A7;
}
QLabel#KpiValue {
    font-size: 22px;
    font-weight: 700;
    color: #F8FAFC;
}
QLabel#KpiSub {
    font-size: 12px;
    color: #9AA4B5;
}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background-color: #0F1115;
    border: 1px solid #2A303C;
    border-radius: 8px;
    padding: 7px 10px;
    color: #F1F5F9;
    selection-background-color: #3B82F6;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
    border: 1px solid #3B82F6;
}
QPushButton {
    background-color: #1F242E;
    border: 1px solid #2E3543;
    border-radius: 8px;
    padding: 8px 14px;
    font-weight: 600;
    color: #E2E8F0;
}
QPushButton:hover {
    background-color: #272E3B;
}
QPushButton:disabled {
    color: #5C6577;
    background-color: #14171D;
    border-color: #1E222B;
}
QPushButton#PrimaryBtn {
    background-color: #2563EB;
    border: 1px solid #3B82F6;
    color: #FFFFFF;
}
QPushButton#PrimaryBtn:hover {
    background-color: #1D4ED8;
}
QPushButton#PrimaryBtn:disabled {
    background-color: #1E3A8A;
    border-color: #1E3A8A;
    color: #93C5FD;
}
QPushButton#DangerBtn {
    background-color: #991B1B;
    border: 1px solid #EF4444;
    color: #FFFFFF;
}
QPushButton#DangerBtn:hover {
    background-color: #7F1D1D;
}
QPushButton#SegBtn {
    background-color: transparent;
    border: none;
    border-radius: 7px;
    padding: 6px 14px;
    color: #8B95A7;
    font-weight: 600;
}
QPushButton#SegBtn:checked {
    background-color: #252A34;
    color: #F8FAFC;
}
QFrame#SegContainer {
    background-color: #161920;
    border: 1px solid #252A34;
    border-radius: 9px;
    padding: 2px;
}
QProgressBar {
    background-color: #161920;
    border: none;
    border-radius: 3px;
    height: 6px;
    text-align: center;
}
QProgressBar::chunk {
    background-color: #3B82F6;
    border-radius: 3px;
}
QPlainTextEdit, QTextBrowser {
    background-color: #0B0D10;
    border: 1px solid #252A34;
    border-radius: 8px;
    padding: 8px;
    font-family: "SF Mono", "Cascadia Code", "JetBrains Mono", monospace;
    font-size: 12px;
    color: #CBD5E1;
}
QTextBrowser#GuideBrowser {
    font-family: -apple-system, "Segoe UI Variable", "Segoe UI", "Inter", sans-serif;
    font-size: 13px;
    padding: 16px;
}
QLabel#StepPill {
    background-color: #161920;
    border: 1px solid #252A34;
    border-radius: 6px;
    padding: 4px 10px;
    font-size: 11px;
    font-weight: 600;
    color: #64748B;
}
QLabel#StepPill[state="active"] {
    background-color: #1E3A8A;
    border-color: #3B82F6;
    color: #EFF6FF;
}
QLabel#StepPill[state="done"] {
    background-color: #064E3B;
    border-color: #10B981;
    color: #D1FAE5;
}
QLabel#StepPill[state="error"] {
    background-color: #7F1D1D;
    border-color: #EF4444;
    color: #FEE2E2;
}
QCheckBox {
    spacing: 6px;
    color: #CBD5E1;
}
"""


class DiagnosticWorker(QThread):
    """Hilo en segundo plano para ejecutar la batería de pruebas sin bloquear la UI."""

    progress = Signal(int, str)
    finished_report = Signal(dict)
    failed = Signal(str)

    def __init__(self, cfg: DiagnosticConfig, soak_rounds: int = 1, soak_interval_s: int = 10) -> None:
        super().__init__()
        self.cfg = cfg
        self.soak_rounds = soak_rounds
        self.soak_interval_s = soak_interval_s
        self.cancel_event = threading.Event()

    def request_cancel(self) -> None:
        self.cancel_event.set()

    def run(self) -> None:
        try:
            if self.soak_rounds > 1:
                report = run_soak_test(
                    self.cfg,
                    rounds=self.soak_rounds,
                    interval_s=self.soak_interval_s,
                    on_progress=lambda pct, msg: self.progress.emit(pct, msg),
                    cancel_event=self.cancel_event,
                )
            else:
                report = run_diagnostic(
                    self.cfg,
                    on_progress=lambda pct, msg: self.progress.emit(pct, msg),
                    cancel_event=self.cancel_event,
                )
            self.finished_report.emit(report)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class ServerWorker(QThread):
    """Hilo pasivo del servidor con parada limpia por timeout."""

    log_line = Signal(str)
    stopped = Signal()
    failed = Signal(str)

    def __init__(self, host: str, port: int, iface: str | None) -> None:
        super().__init__()
        self.host = host
        self.port = port
        self.iface = iface
        self._stop_requested = False

    def request_stop(self) -> None:
        self._stop_requested = True

    def run(self) -> None:
        beacon = ServerBeacon(tcp_port=self.port)
        beacon.start()
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
                srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                srv.bind((self.host, self.port))
                srv.listen(4)
                srv.settimeout(0.5)
                self.log_line.emit(
                    f"Escuchando en {self.host}:{self.port} ({platform.system()}) + Beacon LAN activo"
                )
                while not self._stop_requested:
                    try:
                        conn, addr = srv.accept()
                    except socket.timeout:
                        continue
                    self.log_line.emit(f"Sesión iniciada desde {addr[0]}:{addr[1]}")
                    with conn:
                        handle_client_session(conn, self.iface)
                    self.log_line.emit(f"Sesión finalizada ({addr[0]}:{addr[1]})")
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))
        finally:
            beacon.stop()
            self.stopped.emit()


class BlinkWorker(QThread):
    """Hilo ligero para parpadear el LED del puerto del switch."""

    finished_blink = Signal()

    def __init__(self, target_ip: str, duration_s: int = 8) -> None:
        super().__init__()
        self.target_ip = target_ip
        self.duration_s = duration_s
        self.cancel_event = threading.Event()

    def run(self) -> None:
        run_port_blink(
            self.target_ip,
            duration_s=self.duration_s,
            cancel_event=self.cancel_event,
        )
        self.finished_blink.emit()


class WiggleWorker(QThread):
    """Hilo de Wiggle Test en vivo: envía sondas UDP continuas para detectar micro-cortes."""

    sample = Signal(float, float)  # loss_pct, avg_rtt_ms
    failed = Signal(str)
    finished_wiggle = Signal()

    def __init__(self, server_ip: str, port: int) -> None:
        super().__init__()
        self.server_ip = server_ip
        self.port = port
        self._stop_event = threading.Event()

    def request_stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        import struct
        import time

        try:
            with socket.create_connection((self.server_ip, self.port), timeout=10.0) as ctrl:
                ctrl.settimeout(10.0)
                send_control_msg(ctrl, {"cmd": "START_WIGGLE", "max_duration_s": 120})
                ready = recv_control_msg(ctrl)
                udp_port = int(ready["data_port"])

                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
                    udp.settimeout(0.05)
                    seq = 0
                    while not self._stop_event.is_set():
                        sent = 10
                        received = 0
                        rtts: list[float] = []
                        for _ in range(sent):
                            if self._stop_event.is_set():
                                break
                            t0 = time.perf_counter()
                            pkt = struct.pack("!Qd", seq, t0) + b"\x55" * 32
                            seq += 1
                            udp.sendto(pkt, (self.server_ip, udp_port))
                            try:
                                _data, _ = udp.recvfrom(512)
                                received += 1
                                rtts.append((time.perf_counter() - t0) * 1000.0)
                            except socket.timeout:
                                pass
                            time.sleep(0.03)
                        loss_pct = round(((sent - received) / sent) * 100.0, 1)
                        avg_rtt = round(sum(rtts) / len(rtts), 2) if rtts else 0.0
                        self.sample.emit(loss_pct, avg_rtt)
                    try:
                        udp.sendto(b"WIGGLE_STOP", (self.server_ip, udp_port))
                    except OSError:
                        pass
                send_control_msg(ctrl, {"cmd": "BYE"})
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))
        finally:
            self.finished_wiggle.emit()


class WiggleSparkline(QWidget):
    """Gráfica temporal minimalista de estabilidad (verde = 0% pérdida, rojo = micro-corte)."""

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumHeight(38)
        self.setMaximumHeight(44)
        self._samples: list[float] = []  # pérdida % por ventana

    def add_sample(self, loss_pct: float) -> None:
        self._samples.append(loss_pct)
        if len(self._samples) > 48:
            self._samples.pop(0)
        self.update()

    def clear_samples(self) -> None:
        self._samples.clear()
        self.update()

    def paintEvent(self, _event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect()
        painter.fillRect(rect, QColor("#0B0D10"))
        painter.setPen(QPen(QColor("#252A34"), 1))
        painter.drawRoundedRect(rect.adjusted(0, 0, -1, -1), 6, 6)

        if not self._samples:
            painter.setPen(QColor("#64748B"))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "Wiggle Test inactivo (mueve conectores para probar falsos contactos)")
            return

        w = max(4, (rect.width() - 16) // 48)
        x0 = 8
        h_max = rect.height() - 10
        for i, loss in enumerate(self._samples):
            ok_pct = max(0.05, (100.0 - loss) / 100.0)
            bar_h = max(4, int(h_max * ok_pct))
            color = QColor("#10B981") if loss == 0.0 else QColor("#EF4444")
            painter.fillRect(x0 + i * w, rect.height() - 5 - bar_h, max(2, w - 2), bar_h, color)


def _make_kpi_card(title: str) -> tuple[QFrame, QLabel, QLabel]:
    card = QFrame()
    card.setObjectName("Card")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(16, 14, 16, 14)
    layout.setSpacing(6)

    lbl_title = QLabel(title)
    lbl_title.setObjectName("CardTitle")
    lbl_val = QLabel("—")
    lbl_val.setObjectName("KpiValue")
    lbl_sub = QLabel("Sin datos")
    lbl_sub.setObjectName("KpiSub")
    lbl_sub.setWordWrap(True)

    layout.addWidget(lbl_title)
    layout.addWidget(lbl_val)
    layout.addWidget(lbl_sub)
    layout.addStretch(1)
    return card, lbl_val, lbl_sub


def _list_ipv4_interfaces() -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    for iface, addrs in psutil.net_if_addrs().items():
        for addr in addrs:
            if addr.family == socket.AF_INET and not addr.address.startswith("127."):
                items.append((iface, addr.address))
    return items


class EthqualMainWindow(QMainWindow):
    """Ventana principal minimalista para Cliente y Servidor ethqual."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("ethqual — Diagnóstico Ethernet")
        self.resize(960, 680)
        self.setMinimumSize(820, 580)

        self._last_report: dict[str, Any] | None = None
        self._autosave_path = Path.home() / ".ethqual" / "last_session.jsonl"
        self._session_reports: list[dict[str, Any]] = self._load_autosave()
        self._diag_worker: DiagnosticWorker | None = None
        self._srv_worker: ServerWorker | None = None
        self._blink_worker: BlinkWorker | None = None
        self._wiggle_worker: WiggleWorker | None = None

        root = QWidget()
        self.setCentralWidget(root)
        main_layout = QVBoxLayout(root)
        main_layout.setContentsMargins(24, 20, 24, 20)
        main_layout.setSpacing(16)

        main_layout.addLayout(self._build_header())

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_client_page())
        self.stack.addWidget(self._build_server_page())
        self.stack.addWidget(self._build_guide_page())
        main_layout.addWidget(self.stack, 1)

    def _build_header(self) -> QHBoxLayout:
        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(2)

        lbl_title = QLabel("ethqual")
        lbl_title.setObjectName("Title")
        lbl_sub = QLabel(
            f"Cualificación de enlaces Ethernet · {platform.system()} ({platform.machine()})"
        )
        lbl_sub.setObjectName("Subtitle")
        title_box.addWidget(lbl_title)
        title_box.addWidget(lbl_sub)

        seg_frame = QFrame()
        seg_frame.setObjectName("SegContainer")
        seg_layout = QHBoxLayout(seg_frame)
        seg_layout.setContentsMargins(2, 2, 2, 2)
        seg_layout.setSpacing(2)

        self.btn_mode_client = QPushButton("Modo Cliente")
        self.btn_mode_client.setObjectName("SegBtn")
        self.btn_mode_client.setCheckable(True)
        self.btn_mode_client.setChecked(True)

        self.btn_mode_server = QPushButton("Modo Servidor")
        self.btn_mode_server.setObjectName("SegBtn")
        self.btn_mode_server.setCheckable(True)

        self.btn_mode_guide = QPushButton("Guía de Uso")
        self.btn_mode_guide.setObjectName("SegBtn")
        self.btn_mode_guide.setCheckable(True)

        self.btn_mode_client.clicked.connect(lambda: self._switch_mode(0))
        self.btn_mode_server.clicked.connect(lambda: self._switch_mode(1))
        self.btn_mode_guide.clicked.connect(lambda: self._switch_mode(2))

        seg_layout.addWidget(self.btn_mode_client)
        seg_layout.addWidget(self.btn_mode_server)
        seg_layout.addWidget(self.btn_mode_guide)

        header.addLayout(title_box)
        header.addStretch(1)
        header.addWidget(seg_frame)
        return header

    def _switch_mode(self, idx: int) -> None:
        self.btn_mode_client.setChecked(idx == 0)
        self.btn_mode_server.setChecked(idx == 1)
        self.btn_mode_guide.setChecked(idx == 2)
        self.stack.setCurrentIndex(idx)

    def _build_client_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        ctrl_card = QFrame()
        ctrl_card.setObjectName("Card")
        ctrl_layout = QVBoxLayout(ctrl_card)
        ctrl_layout.setContentsMargins(16, 14, 16, 14)
        ctrl_layout.setSpacing(10)

        row1 = QHBoxLayout()
        row1.setSpacing(10)
        self.in_server_ip = QLineEdit("127.0.0.1")
        self.in_server_ip.setPlaceholderText("IP del servidor (ej. 192.168.50.20)")
        self.in_port = QSpinBox()
        self.in_port.setRange(1, 65535)
        self.in_port.setValue(5000)
        self.in_duration = QSpinBox()
        self.in_duration.setRange(1, 300)
        self.in_duration.setValue(5)
        self.in_duration.setSuffix(" s")
        self.in_streams = QSpinBox()
        self.in_streams.setRange(1, 16)
        self.in_streams.setValue(1)

        self.btn_run = QPushButton("Iniciar Diagnóstico")
        self.btn_run.setObjectName("PrimaryBtn")
        self.btn_run.clicked.connect(self._start_diagnostic)

        self.btn_cancel = QPushButton("Cancelar")
        self.btn_cancel.setObjectName("DangerBtn")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._cancel_diagnostic)

        self.btn_discover = QPushButton("Buscar LAN")
        self.btn_discover.setToolTip("Detectar automáticamente servidores ethqual en la red local")
        self.btn_discover.clicked.connect(self._discover_lan_servers)

        self.in_discovered_servers = QComboBox()
        self.in_discovered_servers.setMinimumWidth(140)
        self.in_discovered_servers.addItem("Servidores LAN...", None)
        self.in_discovered_servers.currentIndexChanged.connect(self._on_discovered_selected)

        self.btn_blink = QPushButton("Blink Puerto")
        self.btn_blink.setToolTip("Envía ráfagas 1 Hz para hacer parpadear el LED del puerto en el switch (8 s)")
        self.btn_blink.clicked.connect(self._start_port_blink)

        self.btn_wiggle = QPushButton("Wiggle Test")
        self.btn_wiggle.setToolTip("Monitor en vivo con gráfica y alerta sonora para detectar falsos contactos al mover el cable")
        self.btn_wiggle.clicked.connect(self._toggle_wiggle)

        row1.addWidget(QLabel("Servidor:"))
        row1.addWidget(self.in_server_ip, 2)
        row1.addWidget(self.btn_discover)
        row1.addWidget(self.in_discovered_servers)
        row1.addWidget(QLabel("Puerto:"))
        row1.addWidget(self.in_port)
        row1.addWidget(QLabel("Duración:"))
        row1.addWidget(self.in_duration)
        row1.addWidget(QLabel("Flujos:"))
        row1.addWidget(self.in_streams)
        row1.addWidget(self.btn_blink)
        row1.addWidget(self.btn_wiggle)
        row1.addWidget(self.btn_run)
        row1.addWidget(self.btn_cancel)

        row2 = QHBoxLayout()
        row2.setSpacing(14)
        self.in_expected_speed = QComboBox()
        self.in_expected_speed.addItems(["1000", "2500", "100", "10"])
        self.in_min_tp = QDoubleSpinBox()
        self.in_min_tp.setRange(1.0, 100000.0)
        self.in_min_tp.setValue(100.0)
        self.in_min_tp.setSuffix(" Mbps")
        self.chk_reverse = QCheckBox("Reverso (S→C)")
        self.chk_duplex = QCheckBox("Full-Duplex simultáneo")
        self.chk_udp = QCheckBox("UDP Jitter")
        self.chk_udp_sweep = QCheckBox("Barrido UDP")
        self.chk_dhcp = QCheckBox("DHCP")
        self.in_soak_rounds = QSpinBox()
        self.in_soak_rounds.setRange(1, 100)
        self.in_soak_rounds.setValue(1)
        self.in_soak_rounds.setToolTip("Rondas Soak Test (>1 ejecuta estabilidad prolongada cada 10 s)")

        row2.addWidget(QLabel("Enlace (Mbps):"))
        row2.addWidget(self.in_expected_speed)
        row2.addWidget(QLabel("Mín. Mbps:"))
        row2.addWidget(self.in_min_tp)
        row2.addWidget(self.chk_reverse)
        row2.addWidget(self.chk_duplex)
        row2.addWidget(self.chk_udp)
        row2.addWidget(self.chk_udp_sweep)
        row2.addWidget(self.chk_dhcp)
        row2.addWidget(QLabel("Soak:"))
        row2.addWidget(self.in_soak_rounds)
        row2.addStretch(1)

        row0 = QHBoxLayout()
        row0.setSpacing(10)
        self.in_project = QLineEdit("Proyecto Obra")
        self.in_cable_id = QLineEdit("TOMA-01")
        self.in_technician = QLineEdit()
        self.in_technician.setPlaceholderText("Técnico")
        self.in_profile = QComboBox()
        self.in_profile.addItem("Personalizado")
        for name in PRESET_PROFILES:
            self.in_profile.addItem(name)
        self.in_profile.currentTextChanged.connect(self._apply_profile)

        self.in_project.setToolTip("Nombre de la obra o sitio para agrupar el reporte HTML")
        self.in_cable_id.setToolTip("Identificador único de la toma o patch panel (ej. P1-R2-08)")
        self.in_profile.setToolTip("Selecciona un perfil preconfigurado según el tipo de enlace a cualificar")
        self.in_server_ip.setToolTip("IP del equipo ejecutando ethqual en Modo Servidor")
        self.in_streams.setToolTip("Cantidad de flujos TCP paralelos (usa 4 para saturar 2.5G/10G)")
        self.chk_duplex.setToolTip("Transmite y recibe simultáneamente para detectar diafonía (NEXT)")
        self.chk_udp_sweep.setToolTip("Barrido de tramas UDP (36B, 256B, 1400B) a distintas tasas PPS")

        row0.addWidget(QLabel("Proyecto:"))
        row0.addWidget(self.in_project, 2)
        row0.addWidget(QLabel("ID Toma:"))
        row0.addWidget(self.in_cable_id, 1)
        row0.addWidget(QLabel("Técnico:"))
        row0.addWidget(self.in_technician, 1)
        row0.addWidget(QLabel("Perfil:"))
        row0.addWidget(self.in_profile, 1)

        ctrl_layout.addLayout(row0)
        ctrl_layout.addLayout(row1)
        ctrl_layout.addLayout(row2)
        layout.addWidget(ctrl_card)

        # Stepper visual + barra de progreso
        prog_box = QVBoxLayout()
        prog_box.setSpacing(6)
        stepper_row = QHBoxLayout()
        stepper_row.setSpacing(8)
        self._step_pills: list[QLabel] = []
        for label in ("1. L2 / ICMP", "2. Handshake", "3. Carga TCP", "4. BER / UDP", "5. NIC / AutoTest"):
            pill = QLabel(label)
            pill.setObjectName("StepPill")
            pill.setProperty("state", "idle")
            stepper_row.addWidget(pill)
            self._step_pills.append(pill)
        stepper_row.addStretch(1)

        self.lbl_progress = QLabel("Listo para iniciar diagnóstico.")
        self.lbl_progress.setObjectName("Subtitle")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        prog_box.addLayout(stepper_row)
        prog_box.addWidget(self.lbl_progress)
        prog_box.addWidget(self.progress_bar)
        layout.addLayout(prog_box)

        self.verdict_card = QFrame()
        self.verdict_card.setObjectName("VerdictNeutral")
        v_layout = QVBoxLayout(self.verdict_card)
        v_layout.setContentsMargins(16, 14, 16, 14)
        v_layout.setSpacing(4)
        self.lbl_verdict = QLabel("ESPERANDO EJECUCIÓN")
        self.lbl_verdict.setFont(QFont("", 16, QFont.Weight.Bold))
        self.lbl_verdict_detail = QLabel(
            "Conecta el equipo remoto en Modo Servidor e inicia la prueba."
        )
        self.lbl_verdict_detail.setObjectName("KpiSub")
        self.lbl_verdict_detail.setWordWrap(True)
        v_layout.addWidget(self.lbl_verdict)
        v_layout.addWidget(self.lbl_verdict_detail)
        layout.addWidget(self.verdict_card)

        grid = QGridLayout()
        grid.setSpacing(12)
        c_tp, self.kpi_tp_val, self.kpi_tp_sub = _make_kpi_card("Rendimiento TCP")
        c_l2, self.kpi_l2_val, self.kpi_l2_sub = _make_kpi_card("Conectividad y Capa 2")
        c_ber, self.kpi_ber_val, self.kpi_ber_sub = _make_kpi_card("Integridad y UDP")
        c_phy, self.kpi_phy_val, self.kpi_phy_sub = _make_kpi_card("Enlace Físico (PHY)")

        grid.addWidget(c_tp, 0, 0)
        grid.addWidget(c_l2, 0, 1)
        grid.addWidget(c_ber, 1, 0)
        grid.addWidget(c_phy, 1, 1)
        layout.addLayout(grid, 1)

        self.wiggle_chart = WiggleSparkline()
        layout.addWidget(self.wiggle_chart)

        # Registro de errores, eventos y remediales sugeridos
        self.client_log = QPlainTextEdit()
        self.client_log.setReadOnly(True)
        self.client_log.setMaximumHeight(115)
        self.client_log.setPlaceholderText(
            "Registro de ejecución, errores y acciones remediales sugeridas..."
        )
        layout.addWidget(self.client_log)

        footer = QHBoxLayout()
        self.lbl_batch = QLabel(f"Lote actual: {len(self._session_reports)} toma(s)")
        self.lbl_batch.setObjectName("Subtitle")
        self.btn_clear_batch = QPushButton("Limpiar Lote")
        self.btn_clear_batch.clicked.connect(self._clear_batch)
        footer.addWidget(self.lbl_batch)
        footer.addWidget(self.btn_clear_batch)
        footer.addStretch(1)
        self.btn_export_json = QPushButton("Exportar reporte.json")
        self.btn_export_json.setEnabled(False)
        self.btn_export_json.clicked.connect(self._export_json)
        self.btn_export_md = QPushButton("Exportar resumen.md")
        self.btn_export_md.setEnabled(False)
        self.btn_export_md.clicked.connect(self._export_md)
        self.btn_export_html = QPushButton("Exportar Reporte HTML")
        self.btn_export_html.setEnabled(bool(self._session_reports))
        self.btn_export_html.clicked.connect(self._export_html)
        self.btn_export_labels = QPushButton("Etiquetas Patch Panel")
        self.btn_export_labels.setEnabled(bool(self._session_reports))
        self.btn_export_labels.clicked.connect(self._export_labels)
        footer.addWidget(self.btn_export_json)
        footer.addWidget(self.btn_export_md)
        footer.addWidget(self.btn_export_html)
        footer.addWidget(self.btn_export_labels)
        layout.addLayout(footer)

        return page

    def _build_server_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        card = QFrame()
        card.setObjectName("Card")
        c_layout = QVBoxLayout(card)
        c_layout.setContentsMargins(16, 14, 16, 14)
        c_layout.setSpacing(10)

        row = QHBoxLayout()
        row.setSpacing(10)
        self.in_srv_host = QLineEdit("0.0.0.0")
        self.in_srv_port = QSpinBox()
        self.in_srv_port.setRange(1, 65535)
        self.in_srv_port.setValue(5000)

        self.in_srv_iface = QComboBox()
        self.in_srv_iface.addItem("Auto-detectar", None)
        for iface, ip in _list_ipv4_interfaces():
            self.in_srv_iface.addItem(f"{iface} ({ip})", iface)

        self.btn_srv_toggle = QPushButton("Iniciar Servidor")
        self.btn_srv_toggle.setObjectName("PrimaryBtn")
        self.btn_srv_toggle.clicked.connect(self._toggle_server)

        row.addWidget(QLabel("Escucha:"))
        row.addWidget(self.in_srv_host)
        row.addWidget(QLabel("Puerto:"))
        row.addWidget(self.in_srv_port)
        row.addWidget(QLabel("Interfaz:"))
        row.addWidget(self.in_srv_iface, 1)
        row.addWidget(self.btn_srv_toggle)

        ips = ", ".join(f"{iface}: {ip}" for iface, ip in _list_ipv4_interfaces()) or "Solo loopback (127.0.0.1)"
        ip_row = QHBoxLayout()
        lbl_ips = QLabel(f"IPs locales detectadas: {ips}")
        lbl_ips.setObjectName("Subtitle")
        btn_copy_ip = QPushButton("Copiar IP")
        btn_copy_ip.setFixedWidth(96)
        btn_copy_ip.clicked.connect(self._copy_first_local_ip)
        ip_row.addWidget(lbl_ips, 1)
        ip_row.addWidget(btn_copy_ip)

        c_layout.addLayout(row)
        c_layout.addLayout(ip_row)
        layout.addWidget(card)

        self.srv_log = QPlainTextEdit()
        self.srv_log.setReadOnly(True)
        self.srv_log.setPlaceholderText("El registro de sesiones aparecerá aquí...")
        layout.addWidget(self.srv_log, 1)
        return page

    def _build_guide_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        guide = QTextBrowser()
        guide.setObjectName("GuideBrowser")
        guide.setHtml(
            """
            <h2 style="color:#F8FAFC;margin-top:0">Guía Rápida de Cualificación en Campo</h2>
            <p style="color:#9AA4B5">Sigue estos pasos para evaluar un enlace Ethernet entre dos notebooks:</p>
            <ol style="line-height:1.6;color:#E2E8F0">
              <li><b>Preparación física:</b> Conecta ambas notebooks mediante el cable UTP o switch no gestionado. Si no hay DHCP, asigna IPs en la misma subred (ej. Servidor <code>192.168.50.20/24</code>, Cliente <code>192.168.50.10/24</code>).</li>
              <li><b>Equipo Servidor:</b> Abre la pestaña <b>Modo Servidor</b>, verifica tu IP local (usa <i>Copiar IP</i>) y pulsa <b>Iniciar Servidor</b>.</li>
              <li><b>Equipo Cliente:</b> En <b>Modo Cliente</b>, ingresa <i>Proyecto</i>, <i>ID Toma</i> (ej. <code>P1-R1-04</code>), selecciona un <i>Perfil</i> e introduce la IP del servidor.</li>
              <li><b>Ejecución y Diagnóstico:</b> Pulsa <b>Iniciar Diagnóstico</b>. El stepper superior muestra las 5 fases en tiempo real; al finalizar verás el veredicto y las <b>acciones remediales</b> si hubiera fallos.</li>
              <li><b>Entrega de Obra:</b> Cambia el <i>ID Toma</i> para probar más puntos en el mismo lote y exporta el consolidado con <b>Exportar Reporte HTML</b> (imprimible a PDF).</li>
            </ol>
            <h3 style="color:#F8FAFC">Qué significa cada veredicto</h3>
            <ul style="line-height:1.6;color:#CBD5E1">
              <li><b style="color:#10B981">APROBADO:</b> Velocidad esperada, Full-Duplex, throughput dentro de umbral, pérdida nula y cero errores NIC.</li>
              <li><b style="color:#F59E0B">ADVERTENCIA:</b> Enlace operativo pero degradado (ej. caída de 1000 a 100 Mbps por fallo en pares 4-5/7-8, Half-Duplex o errores CRC).</li>
              <li><b style="color:#EF4444">FALLO:</b> Host inalcanzable, throughput insuficiente, pérdida de paquetes UDP/ICMP o corrupción de bloques.</li>
            </ul>
            <p style="color:#8B95A7;font-size:12px"><i>Nota técnica: ethqual cualifica rendimiento, integridad y negociación activa IEEE 802.3; no reemplaza certificación RF de capa física (NEXT/FEXT/Atenuación en dB) bajo TIA-568.2-D.</i></p>
            """
        )
        layout.addWidget(guide)
        return page

    def _apply_profile(self, name: str) -> None:
        preset = PRESET_PROFILES.get(name)
        if not preset:
            return
        self.in_expected_speed.setCurrentText(str(preset["expected_speed_mbps"]))
        self.in_min_tp.setValue(float(preset["min_throughput_mbps"]))
        self.in_streams.setValue(int(preset["streams"]))
        self.chk_reverse.setChecked(bool(preset["reverse"]))
        self.chk_duplex.setChecked(bool(preset["full_duplex"]))
        self.chk_udp.setChecked(bool(preset["udp_jitter"]))
        self.chk_udp_sweep.setChecked(bool(preset["udp_sweep"]))

    def _discover_lan_servers(self) -> None:
        self.client_log.appendPlainText("Buscando servidores ethqual en la red local...")
        servers = discover_servers(timeout_s=0.9)
        self.in_discovered_servers.blockSignals(True)
        self.in_discovered_servers.clear()
        if not servers:
            self.in_discovered_servers.addItem("Sin servidores LAN", None)
            self.in_discovered_servers.blockSignals(False)
            self.client_log.appendPlainText("No se detectaron servidores en LAN.")
            return
        for s in servers:
            self.in_discovered_servers.addItem(f"{s['hostname']} ({s['ip']}:{s['port']})", s)
        self.in_discovered_servers.setCurrentIndex(0)
        self.in_discovered_servers.blockSignals(False)
        self._on_discovered_selected(0)
        for s in servers:
            self.client_log.appendPlainText(
                f"Servidor detectado: {s['hostname']} ({s['os']}) -> {s['ip']}:{s['port']}"
            )

    def _on_discovered_selected(self, idx: int) -> None:
        data = self.in_discovered_servers.itemData(idx)
        if isinstance(data, dict):
            self.in_server_ip.setText(str(data["ip"]))
            self.in_port.setValue(int(data["port"]))

    def _start_port_blink(self) -> None:
        if self._blink_worker and self._blink_worker.isRunning():
            self._blink_worker.cancel_event.set()
            return
        target = self.in_server_ip.text().strip()
        if not target:
            return
        self.btn_blink.setText("Detener Blink")
        self.client_log.appendPlainText(f"Port Blink activo hacia {target} (8 s)...")
        self._blink_worker = BlinkWorker(target, duration_s=8)
        self._blink_worker.finished_blink.connect(self._on_blink_finished)
        self._blink_worker.start()

    def _on_blink_finished(self) -> None:
        self.btn_blink.setText("Blink Puerto")
        self.client_log.appendPlainText("Port Blink finalizado.")

    def _toggle_wiggle(self) -> None:
        if self._wiggle_worker and self._wiggle_worker.isRunning():
            self.btn_wiggle.setEnabled(False)
            self._wiggle_worker.request_stop()
            return
        server_ip = self.in_server_ip.text().strip()
        if not server_ip:
            return
        self.wiggle_chart.clear_samples()
        self.btn_wiggle.setText("Detener Wiggle")
        self.btn_wiggle.setObjectName("DangerBtn")
        self.btn_wiggle.style().unpolish(self.btn_wiggle)
        self.btn_wiggle.style().polish(self.btn_wiggle)
        self.client_log.appendPlainText(
            f"Wiggle Test iniciado contra {server_ip}:{self.in_port.value()}. Mueve los conectores..."
        )
        self._wiggle_worker = WiggleWorker(server_ip, self.in_port.value())
        self._wiggle_worker.sample.connect(self._on_wiggle_sample)
        self._wiggle_worker.failed.connect(
            lambda err: self.client_log.appendPlainText(f"[Wiggle ERROR] {err}")
        )
        self._wiggle_worker.finished_wiggle.connect(self._on_wiggle_finished)
        self._wiggle_worker.start()

    def _on_wiggle_sample(self, loss_pct: float, avg_rtt: float) -> None:
        self.wiggle_chart.add_sample(loss_pct)
        if loss_pct > 0.0:
            QApplication.beep()
            self.client_log.appendPlainText(
                f"[ALERTA WIGGLE] Micro-corte detectado: pérdida={loss_pct}% (RTT={avg_rtt} ms)"
            )

    def _on_wiggle_finished(self) -> None:
        self.btn_wiggle.setEnabled(True)
        self.btn_wiggle.setText("Wiggle Test")
        self.btn_wiggle.setObjectName("")
        self.btn_wiggle.style().unpolish(self.btn_wiggle)
        self.btn_wiggle.style().polish(self.btn_wiggle)
        self.client_log.appendPlainText("Wiggle Test finalizado.")

    def _copy_first_local_ip(self) -> None:
        ifaces = _list_ipv4_interfaces()
        ip_to_copy = ifaces[0][1] if ifaces else "127.0.0.1"
        QApplication.clipboard().setText(ip_to_copy)
        self.srv_log.appendPlainText(f"IP copiada al portapapeles: {ip_to_copy}")

    def _set_step_state(self, active_idx: int, failed: bool = False) -> None:
        for i, pill in enumerate(self._step_pills):
            if failed and i == active_idx:
                state = "error"
            elif i < active_idx:
                state = "done"
            elif i == active_idx:
                state = "active"
            else:
                state = "idle"
            pill.setProperty("state", state)
            pill.style().unpolish(pill)
            pill.style().polish(pill)

    def _start_diagnostic(self) -> None:
        server_ip = self.in_server_ip.text().strip()
        if not server_ip:
            QMessageBox.warning(self, "Dato requerido", "Ingresa la IP del servidor.")
            return

        self.client_log.clear()
        self._set_step_state(0)
        self.client_log.appendPlainText(
            f"Iniciando cualificación de '{self.in_cable_id.text().strip()}' contra {server_ip}:{self.in_port.value()}..."
        )

        cfg = DiagnosticConfig(
            server_ip=server_ip,
            port=self.in_port.value(),
            project_name=self.in_project.text().strip() or "Proyecto General",
            cable_id=self.in_cable_id.text().strip() or "TOMA-01",
            technician=self.in_technician.text().strip(),
            profile_name=self.in_profile.currentText(),
            duration_s=self.in_duration.value(),
            streams=self.in_streams.value(),
            reverse=self.chk_reverse.isChecked(),
            full_duplex=self.chk_duplex.isChecked(),
            udp_jitter=self.chk_udp.isChecked(),
            udp_sweep=self.chk_udp_sweep.isChecked(),
            check_dhcp=self.chk_dhcp.isChecked(),
            expected_speed_mbps=int(self.in_expected_speed.currentText()),
            min_throughput_mbps=self.in_min_tp.value(),
        )
        self.btn_run.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.btn_export_json.setEnabled(False)
        self.btn_export_md.setEnabled(False)
        self.progress_bar.setValue(5)
        self._set_verdict_style(
            "VerdictNeutral", "EJECUTANDO...", "Realizando pruebas secuenciales en el enlace."
        )

        self._diag_worker = DiagnosticWorker(
            cfg, soak_rounds=self.in_soak_rounds.value(), soak_interval_s=10
        )
        self._diag_worker.progress.connect(self._on_diag_progress)
        self._diag_worker.finished_report.connect(self._on_diag_finished)
        self._diag_worker.failed.connect(self._on_diag_failed)
        self._diag_worker.start()

    def _on_diag_progress(self, pct: int, msg: str) -> None:
        self.progress_bar.setValue(pct)
        self.lbl_progress.setText(msg)
        self.client_log.appendPlainText(msg)
        if pct < 25:
            self._set_step_state(0)
        elif pct < 40:
            self._set_step_state(1)
        elif pct < 75:
            self._set_step_state(2)
        elif pct < 95:
            self._set_step_state(3)
        elif pct < 100:
            self._set_step_state(4)
        else:
            self._set_step_state(5)

    def _set_verdict_style(self, obj_name: str, title: str, detail: str) -> None:
        self.verdict_card.setObjectName(obj_name)
        self.verdict_card.style().unpolish(self.verdict_card)
        self.verdict_card.style().polish(self.verdict_card)
        self.lbl_verdict.setText(title)
        self.lbl_verdict_detail.setText(detail)

    def _load_autosave(self) -> list[dict[str, Any]]:
        if not self._autosave_path.exists():
            return []
        loaded: list[dict[str, Any]] = []
        try:
            for line in self._autosave_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    loaded.append(json.loads(line))
        except (OSError, json.JSONDecodeError):
            return []
        return loaded

    def _append_autosave(self, report: dict[str, Any]) -> None:
        try:
            self._autosave_path.parent.mkdir(parents=True, exist_ok=True)
            with self._autosave_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(report, ensure_ascii=False) + "\n")
        except OSError:
            pass

    def _clear_batch(self) -> None:
        self._session_reports.clear()
        self.lbl_batch.setText("Lote actual: 0 toma(s)")
        self.btn_export_html.setEnabled(False)
        self.btn_export_labels.setEnabled(False)
        try:
            if self._autosave_path.exists():
                self._autosave_path.unlink()
        except OSError:
            pass

    def _increment_cable_id(self) -> None:
        cur = self.in_cable_id.text().strip()
        m = re.search(r"(\d+)$", cur)
        if m:
            num_str = m.group(1)
            next_num = str(int(num_str) + 1).zfill(len(num_str))
            self.in_cable_id.setText(cur[: m.start(1)] + next_num)

    def _cancel_diagnostic(self) -> None:
        if self._diag_worker and self._diag_worker.isRunning():
            self.btn_cancel.setEnabled(False)
            self._diag_worker.request_cancel()
            self.client_log.appendPlainText("Cancelación solicitada...")

    def _on_diag_finished(self, report: dict[str, Any]) -> None:
        self._last_report = report
        self._session_reports.append(report)
        self._append_autosave(report)
        self._increment_cable_id()
        self.lbl_batch.setText(f"Lote actual: {len(self._session_reports)} toma(s)")
        self.btn_run.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.btn_export_json.setEnabled(True)
        self.btn_export_md.setEnabled(True)
        self.btn_export_html.setEnabled(True)
        self.btn_export_labels.setEnabled(True)

        verdict = report["verdict"]
        reasons = report["verdict_reasons"]
        style_map = {
            "APROBADO": "VerdictPass",
            "ADVERTENCIA": "VerdictWarn",
            "FALLO": "VerdictFail",
        }
        detail = (
            " · ".join(reasons)
            if reasons
            else "Todos los parámetros se encuentran dentro de los umbrales configurados."
        )
        self._set_verdict_style(
            style_map.get(verdict, "VerdictNeutral"), f"VEREDICTO: {verdict}", detail
        )

        tests = report["tests"]
        tp_rx = tests["throughput"]["server_rx"].get("throughput_mbps", 0.0)
        tp_rev = tests["throughput"].get("reverse")
        tp_dup = tests["throughput"].get("full_duplex")
        streams = tests["throughput"]["server_rx"].get("streams", 1)
        if tp_rev:
            rev_mbps = tp_rev["client_rx"].get("throughput_mbps", 0.0)
            self.kpi_tp_val.setText(f"{tp_rx} / {rev_mbps} Mbps")
        else:
            self.kpi_tp_val.setText(f"{tp_rx} Mbps")

        dup_note = (
            f" · Full-Duplex: {tp_dup['server_rx'].get('throughput_mbps')}/{tp_dup['client_rx'].get('throughput_mbps')} Mbps"
            if tp_dup
            else ""
        )
        self.kpi_tp_sub.setText(f"{streams} flujo(s) TCP{dup_note}")

        conn = tests["connectivity_layer2"]
        rtt = conn.get("rtt_avg_ms")
        auto = report.get("network_autotest", {})
        gw = auto.get("gateway_ip") or "N/A"
        dns_ok = "OK" if auto.get("dns", {}).get("ok") else "Sin DNS"
        neighbors = auto.get("lldp", {}).get("neighbors") or []
        lldp_txt = (
            f" · LLDP: {neighbors[0].get('switch_name')}/{neighbors[0].get('port_id')}"
            if neighbors
            else ""
        )
        self.kpi_l2_val.setText(f"{rtt if rtt is not None else '—'} ms")
        self.kpi_l2_sub.setText(
            f"Pérdida: {conn.get('packet_loss_pct')}% · MAC: {conn.get('arp_mac') or 'N/A'}\n"
            f"GW: {gw} · DNS: {dns_ok}{lldp_txt}"
        )

        ber = tests["data_integrity_ber"]["server_rx"]
        udp = tests.get("udp_jitter")
        sweep = tests.get("udp_sweep")
        self.kpi_ber_val.setText(f"BER {ber.get('application_ber', 0.0)}")
        udp_parts = []
        if udp:
            udp_parts.append(f"UDP: {udp['server_rx']['loss_pct']}% / {udp['server_rx']['jitter_ms']} ms")
        if sweep:
            worst = max(sweep, key=lambda x: float(x["server_rx"].get("loss_pct", 0.0)))
            udp_parts.append(f"Barrido ({len(sweep)} pasos): máx pérdida {worst['server_rx']['loss_pct']}%")
        udp_txt = " · ".join(udp_parts) if udp_parts else "UDP Jitter no ejecutado"
        self.kpi_ber_sub.setText(
            f"Bloques corruptos: {ber.get('corrupted_blocks', 0)} · {udp_txt}"
        )

        phy_c = report["phy_link_diagnosis"]["client"]
        phy_s = report["phy_link_diagnosis"]["server"]
        self.kpi_phy_val.setText(
            f"{phy_c['link_info'].get('speed_mbps')} / {phy_s['link_info'].get('speed_mbps')} Mbps"
        )
        self.kpi_phy_sub.setText(
            f"Cliente: {phy_c['status']} (err Δ={phy_c['total_nic_errors_delta']}) · "
            f"Servidor: {phy_s['status']} (err Δ={phy_s['total_nic_errors_delta']})"
        )

        rems = report.get("remediations") or []
        if rems:
            self.client_log.appendPlainText("--- REMEDIALES SUGERIDOS ---")
            for rm in rems:
                self.client_log.appendPlainText(
                    f"[{rm['severity']}] {rm['issue']}\n"
                    f"  Causa: {rm['cause']}\n"
                    f"  Acción: {rm['action']}"
                )
        else:
            self.client_log.appendPlainText("Sin hallazgos: el enlace cumple todos los umbrales.")

    def _on_diag_failed(self, err: str) -> None:
        self.btn_run.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.progress_bar.setValue(0)
        self.lbl_progress.setText("Error durante la ejecución.")
        self._set_step_state(0, failed=True)
        self.client_log.appendPlainText(f"[ERROR] {err}")
        self.client_log.appendPlainText(
            "  Acción sugerida: Verificar que el Servidor esté iniciado, la IP/puerto 5000 sean correctos y el firewall permita TCP/ICMP."
        )
        self._set_verdict_style("VerdictFail", "ERROR DE CONEXIÓN", err)

    def _export_json(self) -> None:
        if not self._last_report:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Guardar reporte JSON", "reporte.json", "JSON (*.json)"
        )
        if path:
            Path(path).write_text(
                json.dumps(self._last_report, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

    def _export_md(self) -> None:
        if not self._last_report:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Exportar resumen Markdown", "resumen.md", "Markdown (*.md)"
        )
        if path:
            write_markdown_summary(path, self._last_report)

    def _export_html(self) -> None:
        if not self._session_reports:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Exportar Reporte HTML de Obra", "reporte_obra.html", "HTML (*.html)"
        )
        if path:
            write_html_report(path, self._session_reports)

    def _export_labels(self) -> None:
        if not self._session_reports:
            return
        path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Exportar Etiquetas Patch Panel",
            "etiquetas.html",
            "Hoja Imprimible HTML (*.html);;Etiquetas CSV (*.csv)",
        )
        if not path:
            return
        if path.lower().endswith(".csv") or "CSV" in selected_filter:
            write_labels_csv(path, self._session_reports)
        else:
            write_labels_html(path, self._session_reports)

    def _toggle_server(self) -> None:
        if self._srv_worker and self._srv_worker.isRunning():
            self.btn_srv_toggle.setEnabled(False)
            self._srv_worker.request_stop()
            return

        host = self.in_srv_host.text().strip() or "0.0.0.0"
        port = self.in_srv_port.value()
        iface = self.in_srv_iface.currentData()

        self._srv_worker = ServerWorker(host, port, iface)
        self._srv_worker.log_line.connect(self.srv_log.appendPlainText)
        self._srv_worker.failed.connect(
            lambda err: self.srv_log.appendPlainText(f"[ERROR] {err}")
        )
        self._srv_worker.stopped.connect(self._on_server_stopped)
        self._srv_worker.start()

        self.btn_srv_toggle.setText("Detener Servidor")
        self.btn_srv_toggle.setObjectName("DangerBtn")
        self.btn_srv_toggle.style().unpolish(self.btn_srv_toggle)
        self.btn_srv_toggle.style().polish(self.btn_srv_toggle)

    def _on_server_stopped(self) -> None:
        self.btn_srv_toggle.setEnabled(True)
        self.btn_srv_toggle.setText("Iniciar Servidor")
        self.btn_srv_toggle.setObjectName("PrimaryBtn")
        self.btn_srv_toggle.style().unpolish(self.btn_srv_toggle)
        self.btn_srv_toggle.style().polish(self.btn_srv_toggle)
        self.srv_log.appendPlainText("Servidor detenido.")

    def closeEvent(self, event: Any) -> None:
        if self._srv_worker and self._srv_worker.isRunning():
            self._srv_worker.request_stop()
            self._srv_worker.wait(1500)
        super().closeEvent(event)


def _resolve_icon_path() -> Path | None:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent.parent))
    for candidate in (base / "ethqual" / "assets" / "icon.png", base / "assets" / "icon.png"):
        if candidate.is_file():
            return candidate
    return None


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("ethqual")
    icon_path = _resolve_icon_path()
    if icon_path is not None:
        app.setWindowIcon(QIcon(str(icon_path)))
    app.setStyleSheet(APP_STYLESHEET)
    win = EthqualMainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
