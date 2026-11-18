"""Interfaz gráfica nativa multiplataforma (PySide6) para ethqual."""

from __future__ import annotations

import json
import logging
import platform
import re
import socket
import sys
import threading
import traceback
from pathlib import Path
from typing import Any

import psutil
from PySide6.QtCore import QPoint, QRect, QSize, QThread, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QKeySequence, QPainter, QPen, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLayout,
    QLayoutItem,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
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
QScrollArea {
    background-color: transparent;
    border: none;
}
QScrollBar:vertical {
    background: #0F1115;
    width: 8px;
    margin: 0;
    border-radius: 4px;
}
QScrollBar::handle:vertical {
    background: #2A303C;
    min-height: 24px;
    border-radius: 4px;
}
QScrollBar::handle:vertical:hover {
    background: #3B4455;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
QScrollBar:horizontal {
    background: #0F1115;
    height: 8px;
    margin: 0;
    border-radius: 4px;
}
QScrollBar::handle:horizontal {
    background: #2A303C;
    min-width: 24px;
    border-radius: 4px;
}
QScrollBar::handle:horizontal:hover {
    background: #3B4455;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
}
QTableWidget {
    background-color: #0B0D10;
    border: 1px solid #252A34;
    border-radius: 8px;
    gridline-color: #1F242E;
    color: #E2E8F0;
    selection-background-color: #1E3A8A;
    selection-color: #F8FAFC;
}
QHeaderView::section {
    background-color: #161920;
    color: #94A3B8;
    border: none;
    border-bottom: 1px solid #252A34;
    padding: 6px 8px;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
}
QTableCornerButton::section {
    background-color: #161920;
    border: none;
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
        session_sem = threading.Semaphore(4)

        def _serve(conn: socket.socket, addr: tuple[str, int]) -> None:
            try:
                self.log_line.emit(f"Sesión iniciada desde {addr[0]}:{addr[1]}")
                with conn:
                    handle_client_session(conn, self.iface)
                self.log_line.emit(f"Sesión finalizada ({addr[0]}:{addr[1]})")
            except Exception as sess_exc:  # noqa: BLE001
                self.log_line.emit(
                    f"[ERROR sesión {addr[0]}:{addr[1]}] {sess_exc}"
                )
            finally:
                session_sem.release()

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
                    session_sem.acquire()
                    t = threading.Thread(
                        target=_serve, args=(conn, addr), daemon=True
                    )
                    t.start()
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


class DiscoverWorker(QThread):
    """Hilo en segundo plano para descubrir servidores ethqual en LAN sin congelar la UI."""

    discovered = Signal(list)
    failed = Signal(str)

    def __init__(self, timeout_s: float = 0.9) -> None:
        super().__init__()
        self.timeout_s = timeout_s

    def run(self) -> None:
        try:
            servers = discover_servers(timeout_s=self.timeout_s)
            self.discovered.emit(servers)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class FlowLayout(QLayout):
    """Layout adaptable que acomoda widgets en múltiples filas según el ancho disponible."""

    def __init__(
        self,
        parent: QWidget | None = None,
        margin: int = 0,
        h_spacing: int = 10,
        v_spacing: int = 8,
    ) -> None:
        super().__init__(parent)
        self._items: list[QLayoutItem] = []
        self._h_space = h_spacing
        self._v_space = v_spacing
        self.setContentsMargins(margin, margin, margin, margin)

    def __del__(self) -> None:
        item = self.takeAt(0)
        while item is not None:
            item = self.takeAt(0)

    def addItem(self, item: QLayoutItem) -> None:
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int) -> QLayoutItem | None:
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index: int) -> QLayoutItem | None:
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self) -> Qt.Orientation:
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect: QRect) -> None:
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def _do_layout(self, rect: QRect, test_only: bool) -> int:
        margins = self.contentsMargins()
        effective = rect.adjusted(margins.left(), margins.top(), -margins.right(), -margins.bottom())
        x = effective.x()
        y = effective.y()
        line_height = 0

        for item in self._items:
            wid = item.widget()
            if wid is not None and not wid.isVisibleTo(wid.parentWidget()):
                continue
            item_size = item.sizeHint()
            next_x = x + item_size.width() + self._h_space
            if next_x - self._h_space > effective.right() + 1 and line_height > 0:
                x = effective.x()
                y = y + line_height + self._v_space
                next_x = x + item_size.width() + self._h_space
                line_height = 0

            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), item_size))

            x = next_x
            line_height = max(line_height, item_size.height())

        return y + line_height - rect.y() + margins.bottom()


def _field_group(label_text: str, widget: QWidget) -> QWidget:
    """Agrupa una etiqueta y su control para que no se separen al hacer wrap."""
    container = QWidget()
    container.setStyleSheet("background: transparent;")
    lay = QHBoxLayout(container)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(6)
    lbl = QLabel(label_text)
    lbl.setStyleSheet("background: transparent;")
    lay.addWidget(lbl)
    lay.addWidget(widget)
    return container


def _make_scrollable_page(content: QWidget) -> QScrollArea:
    """Envuelve una página en un QScrollArea sin bordes para pantallas pequeñas."""
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setWidget(content)
    return scroll


class WiggleSparkline(QWidget):
    """Gráfica temporal minimalista de estabilidad (verde = 0% pérdida, rojo = micro-corte)."""

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumHeight(42)
        self.setMaximumHeight(48)
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
            painter.drawText(
                rect.adjusted(8, 2, -8, -2),
                Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                "Wiggle Test inactivo (mueve conectores para probar falsos contactos)",
            )
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
    card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    layout = QVBoxLayout(card)
    layout.setContentsMargins(16, 14, 16, 14)
    layout.setSpacing(6)

    lbl_title = QLabel(title)
    lbl_title.setObjectName("CardTitle")
    lbl_title.setWordWrap(True)
    lbl_val = QLabel("—")
    lbl_val.setObjectName("KpiValue")
    lbl_val.setWordWrap(True)
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
    """Ventana principal minimalista y responsive para Cliente y Servidor ethqual."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("ethqual — Diagnóstico Ethernet")
        self.resize(980, 720)
        self.setMinimumSize(360, 440)

        self._last_report: dict[str, Any] | None = None
        self._autosave_path = Path.home() / ".ethqual" / "last_session.jsonl"
        self._prefs_path = Path.home() / ".ethqual" / "prefs.json"
        self._session_reports: list[dict[str, Any]] = self._load_autosave()
        self._diag_worker: DiagnosticWorker | None = None
        self._srv_worker: ServerWorker | None = None
        self._blink_worker: BlinkWorker | None = None
        self._wiggle_worker: WiggleWorker | None = None
        self._discover_worker: DiscoverWorker | None = None
        self._kpi_cols: int = 0
        self._applying_profile: bool = False

        root = QWidget()
        self.setCentralWidget(root)
        self._main_layout = QVBoxLayout(root)
        self._main_layout.setContentsMargins(20, 16, 20, 16)
        self._main_layout.setSpacing(14)

        self._main_layout.addLayout(self._build_header())

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_client_page())
        self.stack.addWidget(self._build_server_page())
        self.stack.addWidget(self._build_guide_page())
        self._main_layout.addWidget(self.stack, 1)

        self._load_prefs()
        self._update_responsive_layout(self.width())

        QShortcut(QKeySequence("Ctrl+Return"), self, self._start_diagnostic)
        QShortcut(QKeySequence("Escape"), self, self._cancel_diagnostic)

    def resizeEvent(self, event: Any) -> None:
        super().resizeEvent(event)
        self._load_prefs()
        self._update_responsive_layout(self.width())

        QShortcut(QKeySequence("Ctrl+Return"), self, self._start_diagnostic)
        QShortcut(QKeySequence("Escape"), self, self._cancel_diagnostic)

    def _update_responsive_layout(self, width: int) -> None:
        """Adapta márgenes y columnas de tarjetas KPI según el ancho de la ventana."""
        if width < 600:
            margins = (12, 12, 12, 12)
            spacing = 10
            target_cols = 1
        elif width < 1120:
            margins = (20, 16, 20, 16)
            spacing = 12
            target_cols = 2
        else:
            margins = (24, 20, 24, 20)
            spacing = 14
            target_cols = 4

        self._main_layout.setContentsMargins(*margins)
        self._main_layout.setSpacing(spacing)

        if target_cols != self._kpi_cols and hasattr(self, "_kpi_cards"):
            self._kpi_cols = target_cols
            while self._kpi_grid.count():
                self._kpi_grid.takeAt(0)
            for c in range(4):
                self._kpi_grid.setColumnStretch(c, 0)
            for idx, card in enumerate(self._kpi_cards):
                row = idx // target_cols
                col = idx % target_cols
                self._kpi_grid.addWidget(card, row, col)
            for c in range(target_cols):
                self._kpi_grid.setColumnStretch(c, 1)

    def _build_header(self) -> FlowLayout:
        header = FlowLayout(h_spacing=12, v_spacing=8)

        title_widget = QWidget()
        title_widget.setStyleSheet("background: transparent;")
        title_box = QVBoxLayout(title_widget)
        title_box.setContentsMargins(0, 0, 0, 0)
        title_box.setSpacing(2)

        lbl_title = QLabel("ethqual")
        lbl_title.setObjectName("Title")
        lbl_sub = QLabel(
            f"Cualificación de enlaces Ethernet · {platform.system()} ({platform.machine()})"
        )
        lbl_sub.setObjectName("Subtitle")
        lbl_sub.setWordWrap(True)
        title_box.addWidget(lbl_title)
        title_box.addWidget(lbl_sub)

        seg_frame = QFrame()
        seg_frame.setObjectName("SegContainer")
        seg_frame.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
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

        header.addWidget(title_widget)
        header.addWidget(seg_frame)
        return header

    def _switch_mode(self, idx: int) -> None:
        self.btn_mode_client.setChecked(idx == 0)
        self.btn_mode_server.setChecked(idx == 1)
        self.btn_mode_guide.setChecked(idx == 2)
        self.stack.setCurrentIndex(idx)
        if idx == 1:
            self._refresh_server_interfaces()

    def _build_client_page(self) -> QScrollArea:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 4, 0)
        layout.setSpacing(14)

        ctrl_card = QFrame()
        ctrl_card.setObjectName("Card")
        ctrl_layout = QVBoxLayout(ctrl_card)
        ctrl_layout.setContentsMargins(14, 12, 14, 12)
        ctrl_layout.setSpacing(10)

        row1 = FlowLayout(h_spacing=10, v_spacing=8)
        self.in_server_ip = QLineEdit("127.0.0.1")
        self.in_server_ip.setMinimumWidth(140)
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
        self.in_discovered_servers.setMinimumWidth(150)
        self.in_discovered_servers.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.in_discovered_servers.addItem("Servidores LAN...", None)
        self.in_discovered_servers.currentIndexChanged.connect(self._on_discovered_selected)

        self.btn_blink = QPushButton("Blink Puerto")
        self.btn_blink.setToolTip("Envía ráfagas 1 Hz para hacer parpadear el LED del puerto en el switch (8 s)")
        self.btn_blink.clicked.connect(self._start_port_blink)

        self.btn_wiggle = QPushButton("Wiggle Test")
        self.btn_wiggle.setToolTip("Monitor en vivo con gráfica y alerta sonora para detectar falsos contactos al mover el cable")
        self.btn_wiggle.clicked.connect(self._toggle_wiggle)

        row1.addWidget(_field_group("Servidor:", self.in_server_ip))
        row1.addWidget(self.btn_discover)
        row1.addWidget(self.in_discovered_servers)
        row1.addWidget(_field_group("Puerto:", self.in_port))
        row1.addWidget(_field_group("Duración:", self.in_duration))
        row1.addWidget(_field_group("Flujos:", self.in_streams))
        row1.addWidget(self.btn_blink)
        row1.addWidget(self.btn_wiggle)
        row1.addWidget(self.btn_run)
        row1.addWidget(self.btn_cancel)

        row2 = FlowLayout(h_spacing=12, v_spacing=8)
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

        row2.addWidget(_field_group("Enlace (Mbps):", self.in_expected_speed))
        row2.addWidget(_field_group("Mín. Mbps:", self.in_min_tp))
        row2.addWidget(self.chk_reverse)
        row2.addWidget(self.chk_duplex)
        row2.addWidget(self.chk_udp)
        row2.addWidget(self.chk_udp_sweep)
        row2.addWidget(self.chk_dhcp)
        row2.addWidget(_field_group("Soak:", self.in_soak_rounds))

        row0 = FlowLayout(h_spacing=10, v_spacing=8)
        self.in_project = QLineEdit("Proyecto Obra")
        self.in_project.setMinimumWidth(140)
        self.in_cable_id = QLineEdit("TOMA-01")
        self.in_cable_id.setMinimumWidth(100)
        self.in_technician = QLineEdit()
        self.in_technician.setMinimumWidth(110)
        self.in_technician.setPlaceholderText("Técnico")
        self.in_profile = QComboBox()
        self.in_profile.setMinimumWidth(130)
        self.in_profile.addItem("Personalizado")
        for name in PRESET_PROFILES:
            self.in_profile.addItem(name)
        self.in_profile.currentTextChanged.connect(self._apply_profile)
        self.in_expected_speed.currentIndexChanged.connect(self._mark_profile_custom)
        self.in_min_tp.valueChanged.connect(self._mark_profile_custom)
        self.in_streams.valueChanged.connect(self._mark_profile_custom)
        self.chk_reverse.toggled.connect(self._mark_profile_custom)
        self.chk_duplex.toggled.connect(self._mark_profile_custom)
        self.chk_udp.toggled.connect(self._mark_profile_custom)
        self.chk_udp_sweep.toggled.connect(self._mark_profile_custom)

        self.in_project.setToolTip("Nombre de la obra o sitio para agrupar el reporte HTML")
        self.in_cable_id.setToolTip("Identificador único de la toma o patch panel (ej. P1-R2-08)")
        self.in_profile.setToolTip("Selecciona un perfil preconfigurado según el tipo de enlace a cualificar")
        self.in_server_ip.setToolTip("IP del equipo ejecutando ethqual en Modo Servidor")
        self.in_streams.setToolTip("Cantidad de flujos TCP paralelos (usa 4 para saturar 2.5G/10G)")
        self.chk_duplex.setToolTip("Transmite y recibe simultáneamente para detectar diafonía (NEXT)")
        self.chk_udp_sweep.setToolTip("Barrido de tramas UDP (36B, 256B, 1400B) a distintas tasas PPS")

        row0.addWidget(_field_group("Proyecto:", self.in_project))
        row0.addWidget(_field_group("ID Toma:", self.in_cable_id))
        row0.addWidget(_field_group("Técnico:", self.in_technician))
        row0.addWidget(_field_group("Perfil:", self.in_profile))

        ctrl_layout.addLayout(row0)
        ctrl_layout.addLayout(row1)
        ctrl_layout.addLayout(row2)
        layout.addWidget(ctrl_card)

        # Stepper visual + barra de progreso
        prog_box = QVBoxLayout()
        prog_box.setSpacing(6)
        stepper_row = FlowLayout(h_spacing=6, v_spacing=6)
        self._step_pills: list[QLabel] = []
        for label in ("1. L2 / ICMP", "2. Handshake", "3. Carga TCP", "4. BER / UDP", "5. NIC / AutoTest"):
            pill = QLabel(label)
            pill.setObjectName("StepPill")
            pill.setProperty("state", "idle")
            stepper_row.addWidget(pill)
            self._step_pills.append(pill)

        self.lbl_progress = QLabel("Listo para iniciar diagnóstico.")
        self.lbl_progress.setObjectName("Subtitle")
        self.lbl_progress.setWordWrap(True)
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
        self.lbl_verdict.setWordWrap(True)
        self.lbl_verdict_detail = QLabel(
            "Conecta el equipo remoto en Modo Servidor e inicia la prueba."
        )
        self.lbl_verdict_detail.setObjectName("KpiSub")
        self.lbl_verdict_detail.setWordWrap(True)
        v_layout.addWidget(self.lbl_verdict)
        v_layout.addWidget(self.lbl_verdict_detail)
        layout.addWidget(self.verdict_card)

        self._kpi_grid = QGridLayout()
        self._kpi_grid.setSpacing(12)
        c_tp, self.kpi_tp_val, self.kpi_tp_sub = _make_kpi_card("Rendimiento TCP")
        c_l2, self.kpi_l2_val, self.kpi_l2_sub = _make_kpi_card("Conectividad y Capa 2")
        c_ber, self.kpi_ber_val, self.kpi_ber_sub = _make_kpi_card("Integridad y UDP")
        c_phy, self.kpi_phy_val, self.kpi_phy_sub = _make_kpi_card("Enlace Físico (PHY)")

        self._kpi_cards = [c_tp, c_l2, c_ber, c_phy]
        layout.addLayout(self._kpi_grid, 1)

        self.wiggle_chart = WiggleSparkline()
        layout.addWidget(self.wiggle_chart)

        # Registro de errores, eventos y remediales sugeridos
        self.client_log = QPlainTextEdit()
        self.client_log.setReadOnly(True)
        self.client_log.setMinimumHeight(90)
        self.client_log.setMaximumHeight(160)
        self.client_log.setPlaceholderText(
            "Registro de ejecución, errores y acciones remediales sugeridas..."
        )
        layout.addWidget(self.client_log)

        footer = FlowLayout(h_spacing=8, v_spacing=8)
        self.lbl_batch = QLabel(f"Lote actual: {len(self._session_reports)} toma(s)")
        self.lbl_batch.setObjectName("Subtitle")
        self.btn_view_batch = QPushButton("Ver Lote")
        self.btn_view_batch.setEnabled(bool(self._session_reports))
        self.btn_view_batch.clicked.connect(self._show_batch_dialog)
        self.btn_undo_batch = QPushButton("Deshacer última")
        self.btn_undo_batch.setEnabled(bool(self._session_reports))
        self.btn_undo_batch.clicked.connect(self._undo_last_batch)
        self.btn_clear_batch = QPushButton("Limpiar Lote")
        self.btn_clear_batch.clicked.connect(self._clear_batch)
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

        footer.addWidget(self.lbl_batch)
        footer.addWidget(self.btn_view_batch)
        footer.addWidget(self.btn_undo_batch)
        footer.addWidget(self.btn_clear_batch)
        footer.addWidget(self.btn_export_json)
        footer.addWidget(self.btn_export_md)
        footer.addWidget(self.btn_export_html)
        footer.addWidget(self.btn_export_labels)
        layout.addLayout(footer)

        return _make_scrollable_page(page)

    def _build_server_page(self) -> QScrollArea:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 4, 0)
        layout.setSpacing(14)

        card = QFrame()
        card.setObjectName("Card")
        c_layout = QVBoxLayout(card)
        c_layout.setContentsMargins(14, 12, 14, 12)
        c_layout.setSpacing(10)

        row = FlowLayout(h_spacing=10, v_spacing=8)
        self.in_srv_host = QLineEdit("0.0.0.0")
        self.in_srv_host.setMinimumWidth(110)
        self.in_srv_port = QSpinBox()
        self.in_srv_port.setRange(1, 65535)
        self.in_srv_port.setValue(5000)

        self.in_srv_iface = QComboBox()
        self.in_srv_iface.setMinimumWidth(160)
        self.in_srv_iface.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.in_srv_iface.addItem("Auto-detectar", None)
        for iface, ip in _list_ipv4_interfaces():
            self.in_srv_iface.addItem(f"{iface} ({ip})", iface)

        self.btn_srv_toggle = QPushButton("Iniciar Servidor")
        self.btn_srv_toggle.setObjectName("PrimaryBtn")
        self.btn_srv_toggle.clicked.connect(self._toggle_server)

        row.addWidget(_field_group("Escucha:", self.in_srv_host))
        row.addWidget(_field_group("Puerto:", self.in_srv_port))
        row.addWidget(_field_group("Interfaz:", self.in_srv_iface))
        row.addWidget(self.btn_srv_toggle)

        ip_row = FlowLayout(h_spacing=10, v_spacing=6)
        self.lbl_srv_ips = QLabel()
        self.lbl_srv_ips.setObjectName("Subtitle")
        self.lbl_srv_ips.setWordWrap(True)
        btn_refresh_ip = QPushButton("Actualizar IPs")
        btn_refresh_ip.clicked.connect(self._refresh_server_interfaces)
        btn_copy_ip = QPushButton("Copiar IP")
        btn_copy_ip.clicked.connect(self._copy_first_local_ip)
        ip_row.addWidget(self.lbl_srv_ips)
        ip_row.addWidget(btn_refresh_ip)
        ip_row.addWidget(btn_copy_ip)
        self._refresh_server_interfaces()

        c_layout.addLayout(row)
        c_layout.addLayout(ip_row)
        layout.addWidget(card)

        self.srv_log = QPlainTextEdit()
        self.srv_log.setReadOnly(True)
        self.srv_log.setMinimumHeight(180)
        self.srv_log.setPlaceholderText("El registro de sesiones aparecerá aquí...")
        layout.addWidget(self.srv_log, 1)
        return _make_scrollable_page(page)

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
        self._applying_profile = True
        try:
            self.in_expected_speed.setCurrentText(str(preset["expected_speed_mbps"]))
            self.in_min_tp.setValue(float(preset["min_throughput_mbps"]))
            self.in_streams.setValue(int(preset["streams"]))
            self.chk_reverse.setChecked(bool(preset["reverse"]))
            self.chk_duplex.setChecked(bool(preset["full_duplex"]))
            self.chk_udp.setChecked(bool(preset["udp_jitter"]))
            self.chk_udp_sweep.setChecked(bool(preset["udp_sweep"]))
        finally:
            self._applying_profile = False

    def _mark_profile_custom(self) -> None:
        if self._applying_profile:
            return
        if self.in_profile.currentText() != "Personalizado":
            self.in_profile.blockSignals(True)
            self.in_profile.setCurrentText("Personalizado")
            self.in_profile.blockSignals(False)

    def _refresh_server_interfaces(self) -> None:
        if not hasattr(self, "in_srv_iface"):
            return
        prev_data = self.in_srv_iface.currentData()
        ifaces = _list_ipv4_interfaces()
        self.in_srv_iface.blockSignals(True)
        self.in_srv_iface.clear()
        self.in_srv_iface.addItem("Auto-detectar", None)
        for iface, ip in ifaces:
            self.in_srv_iface.addItem(f"{iface} ({ip})", iface)
        if prev_data is not None:
            idx = self.in_srv_iface.findData(prev_data)
            if idx >= 0:
                self.in_srv_iface.setCurrentIndex(idx)
        self.in_srv_iface.blockSignals(False)
        ips = ", ".join(f"{iface}: {ip}" for iface, ip in ifaces) or "Solo loopback (127.0.0.1)"
        self.lbl_srv_ips.setText(f"IPs locales detectadas: {ips}")

    def _set_test_buttons_busy(self, active_mode: str | None) -> None:
        """Garantiza exclusión mutua entre Diagnóstico, Wiggle Test y Blink Puerto."""
        if active_mode is None:
            self.btn_run.setEnabled(True)
            self.btn_cancel.setEnabled(False)
            self.btn_wiggle.setEnabled(True)
            self.btn_blink.setEnabled(True)
        elif active_mode == "diag":
            self.btn_run.setEnabled(False)
            self.btn_cancel.setEnabled(True)
            self.btn_wiggle.setEnabled(False)
            self.btn_blink.setEnabled(False)
        elif active_mode == "wiggle":
            self.btn_run.setEnabled(False)
            self.btn_cancel.setEnabled(False)
            self.btn_wiggle.setEnabled(True)
            self.btn_blink.setEnabled(False)
        elif active_mode == "blink":
            self.btn_run.setEnabled(False)
            self.btn_cancel.setEnabled(False)
            self.btn_wiggle.setEnabled(False)
            self.btn_blink.setEnabled(True)

    def _discover_lan_servers(self) -> None:
        if self._discover_worker and self._discover_worker.isRunning():
            return
        self.btn_discover.setEnabled(False)
        self.btn_discover.setText("Buscando...")
        self.client_log.appendPlainText("Buscando servidores ethqual en la red local...")
        self._discover_worker = DiscoverWorker(timeout_s=0.9)
        self._discover_worker.discovered.connect(self._on_discover_finished)
        self._discover_worker.failed.connect(self._on_discover_failed)
        self._discover_worker.start()

    def _on_discover_finished(self, servers: list[dict[str, Any]]) -> None:
        self.btn_discover.setEnabled(True)
        self.btn_discover.setText("Buscar LAN")
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

    def _on_discover_failed(self, err: str) -> None:
        self.btn_discover.setEnabled(True)
        self.btn_discover.setText("Buscar LAN")
        self.client_log.appendPlainText(f"[ERROR LAN] {err}")

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
        self._set_test_buttons_busy("blink")
        self.btn_blink.setText("Detener Blink")
        self.client_log.appendPlainText(f"Port Blink activo hacia {target} (8 s)...")
        self._blink_worker = BlinkWorker(target, duration_s=8)
        self._blink_worker.finished_blink.connect(self._on_blink_finished)
        self._blink_worker.start()

    def _on_blink_finished(self) -> None:
        self.btn_blink.setText("Blink Puerto")
        self._set_test_buttons_busy(None)
        self.client_log.appendPlainText("Port Blink finalizado.")

    def _toggle_wiggle(self) -> None:
        if self._wiggle_worker and self._wiggle_worker.isRunning():
            self.btn_wiggle.setEnabled(False)
            self._wiggle_worker.request_stop()
            return
        server_ip = self.in_server_ip.text().strip()
        if not server_ip:
            return
        self._set_test_buttons_busy("wiggle")
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
        self._set_test_buttons_busy(None)
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
        if not self.btn_run.isEnabled():
            return
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
        self._set_test_buttons_busy("diag")
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

    def _rewrite_autosave(self) -> None:
        try:
            if not self._session_reports:
                if self._autosave_path.exists():
                    self._autosave_path.unlink()
                return
            self._autosave_path.parent.mkdir(parents=True, exist_ok=True)
            lines = [json.dumps(r, ensure_ascii=False) for r in self._session_reports]
            self._autosave_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        except OSError:
            pass

    def _show_batch_dialog(self) -> None:
        if not self._session_reports:
            return
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Tomas en el lote actual ({len(self._session_reports)})")
        dlg.resize(760, 420)
        dlg.setMinimumSize(340, 260)
        v_lay = QVBoxLayout(dlg)

        table = QTableWidget(len(self._session_reports), 6, dlg)
        table.setHorizontalHeaderLabels(
            ["ID Toma", "Proyecto", "Veredicto", "Throughput", "PHY (C/S)", "RTT / Pérdida"]
        )
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        verdict_colors = {
            "APROBADO": QColor("#10B981"),
            "ADVERTENCIA": QColor("#F59E0B"),
            "FALLO": QColor("#EF4444"),
        }
        for row_idx, rep in enumerate(self._session_reports):
            meta = rep.get("metadata", {})
            tests = rep.get("tests", {})
            tp = tests.get("throughput", {}).get("server_rx", {}).get("throughput_mbps", 0.0)
            conn = tests.get("connectivity_layer2", {})
            phy_c = rep.get("phy_link_diagnosis", {}).get("client", {}).get("link_info", {}).get("speed_mbps", "—")
            phy_s = rep.get("phy_link_diagnosis", {}).get("server", {}).get("link_info", {}).get("speed_mbps", "—")
            verdict = str(rep.get("verdict") or "")
            vals = [
                str(meta.get("cable_id") or f"TOMA-{row_idx + 1}"),
                str(meta.get("project_name") or ""),
                verdict,
                f"{tp} Mbps",
                f"{phy_c} / {phy_s} Mbps",
                f"{conn.get('rtt_avg_ms', '—')} ms ({conn.get('packet_loss_pct', 0)}%)",
            ]
            for col_idx, txt in enumerate(vals):
                item = QTableWidgetItem(txt)
                if col_idx == 2 and verdict in verdict_colors:
                    item.setForeground(verdict_colors[verdict])
                table.setItem(row_idx, col_idx, item)

        v_lay.addWidget(table)
        btn_row = QHBoxLayout()
        btn_del = QPushButton("Eliminar seleccionada", dlg)
        btn_del.setObjectName("DangerBtn")

        def _delete_selected() -> None:
            row = table.currentRow()
            if row < 0 or row >= len(self._session_reports):
                return
            removed = self._session_reports.pop(row)
            table.removeRow(row)
            count = len(self._session_reports)
            self.lbl_batch.setText(f"Lote actual: {count} toma(s)")
            self.btn_view_batch.setEnabled(bool(count))
            self.btn_undo_batch.setEnabled(bool(count))
            self.btn_export_html.setEnabled(bool(count))
            self.btn_export_labels.setEnabled(bool(count))
            self._rewrite_autosave()
            cid = removed.get("metadata", {}).get("cable_id", "toma")
            self.client_log.appendPlainText(f"Se eliminó '{cid}' del lote actual.")
            dlg.setWindowTitle(f"Tomas en el lote actual ({count})")

        btn_del.clicked.connect(_delete_selected)
        btn_close = QPushButton("Cerrar", dlg)
        btn_close.clicked.connect(dlg.accept)
        btn_row.addWidget(btn_del)
        btn_row.addStretch(1)
        btn_row.addWidget(btn_close)
        v_lay.addLayout(btn_row)
        dlg.exec()

    def _undo_last_batch(self) -> None:
        if not self._session_reports:
            return
        removed = self._session_reports.pop()
        cable_id = removed.get("metadata", {}).get("cable_id", "toma")
        count = len(self._session_reports)
        self.lbl_batch.setText(f"Lote actual: {count} toma(s)")
        self.btn_view_batch.setEnabled(bool(count))
        self.btn_undo_batch.setEnabled(bool(count))
        self.btn_export_html.setEnabled(bool(count))
        self.btn_export_labels.setEnabled(bool(count))
        self._rewrite_autosave()
        self.client_log.appendPlainText(f"Se eliminó '{cable_id}' del lote actual.")

    def _clear_batch(self) -> None:
        self._session_reports.clear()
        self.lbl_batch.setText("Lote actual: 0 toma(s)")
        self.btn_view_batch.setEnabled(False)
        self.btn_undo_batch.setEnabled(False)
        self.btn_export_html.setEnabled(False)
        self.btn_export_labels.setEnabled(False)
        self._rewrite_autosave()

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
        self._set_test_buttons_busy(None)
        self.btn_view_batch.setEnabled(True)
        self.btn_undo_batch.setEnabled(True)
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
        self._set_test_buttons_busy(None)
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
        if not path:
            return
        try:
            Path(path).write_text(
                json.dumps(self._last_report, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            self.client_log.appendPlainText(f"Reporte JSON exportado: {path}")
        except OSError as exc:
            QMessageBox.critical(self, "Error al exportar JSON", str(exc))

    def _export_md(self) -> None:
        if not self._last_report:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Exportar resumen Markdown", "resumen.md", "Markdown (*.md)"
        )
        if not path:
            return
        try:
            write_markdown_summary(path, self._last_report)
            self.client_log.appendPlainText(f"Resumen Markdown exportado: {path}")
        except OSError as exc:
            QMessageBox.critical(self, "Error al exportar Markdown", str(exc))

    def _export_html(self) -> None:
        if not self._session_reports:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Exportar Reporte HTML de Obra", "reporte_obra.html", "HTML (*.html)"
        )
        if not path:
            return
        try:
            write_html_report(path, self._session_reports)
            self.client_log.appendPlainText(f"Reporte HTML de obra exportado: {path}")
        except OSError as exc:
            QMessageBox.critical(self, "Error al exportar HTML", str(exc))

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
        try:
            if path.lower().endswith(".csv") or "CSV" in selected_filter:
                write_labels_csv(path, self._session_reports)
            else:
                write_labels_html(path, self._session_reports)
            self.client_log.appendPlainText(f"Etiquetas exportadas: {path}")
        except OSError as exc:
            QMessageBox.critical(self, "Error al exportar etiquetas", str(exc))

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

    def _load_prefs(self) -> None:
        if not self._prefs_path.exists():
            return
        try:
            data = json.loads(self._prefs_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(data, dict):
            return
        if isinstance(data.get("project"), str) and data["project"]:
            self.in_project.setText(data["project"])
        if isinstance(data.get("technician"), str):
            self.in_technician.setText(data["technician"])
        if isinstance(data.get("server_ip"), str) and data["server_ip"]:
            self.in_server_ip.setText(data["server_ip"])
        if isinstance(data.get("port"), int) and 1 <= data["port"] <= 65535:
            self.in_port.setValue(data["port"])
        if isinstance(data.get("profile"), str):
            idx = self.in_profile.findText(data["profile"])
            if idx >= 0:
                self.in_profile.setCurrentIndex(idx)
        win_w = data.get("window_w")
        win_h = data.get("window_h")
        if isinstance(win_w, int) and isinstance(win_h, int) and win_w >= 360 and win_h >= 440:
            self.resize(win_w, win_h)

    def _save_prefs(self) -> None:
        payload = {
            "project": self.in_project.text().strip(),
            "technician": self.in_technician.text().strip(),
            "server_ip": self.in_server_ip.text().strip(),
            "port": self.in_port.value(),
            "profile": self.in_profile.currentText(),
            "window_w": self.width(),
            "window_h": self.height(),
        }
        try:
            self._prefs_path.parent.mkdir(parents=True, exist_ok=True)
            self._prefs_path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError:
            pass

    def closeEvent(self, event: Any) -> None:
        self._save_prefs()
        if self._diag_worker and self._diag_worker.isRunning():
            self._diag_worker.request_cancel()
            self._diag_worker.wait(1000)
        if self._wiggle_worker and self._wiggle_worker.isRunning():
            self._wiggle_worker.request_stop()
            self._wiggle_worker.wait(1000)
        if self._blink_worker and self._blink_worker.isRunning():
            self._blink_worker.cancel_event.set()
            self._blink_worker.wait(500)
        if self._discover_worker and self._discover_worker.isRunning():
            self._discover_worker.wait(500)
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


def _setup_windowed_logging() -> None:
    """Registra errores en ~/.ethqual/ethqual.log cuando la app corre sin consola (--windowed)."""
    log_dir = Path.home() / ".ethqual"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(
            filename=str(log_dir / "ethqual.log"),
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
        )
    except OSError:
        pass

    def _excepthook(exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        tb_text = "".join(traceback.format_exception(exc_type, exc_val, exc_tb))
        logging.error("Excepción no controlada:\n%s", tb_text)
        if QApplication.instance() is not None:
            QMessageBox.critical(None, "Error inesperado — ethqual", f"{exc_val}\n\nDetalle guardado en ~/.ethqual/ethqual.log")

    sys.excepthook = _excepthook


def main() -> None:
    _setup_windowed_logging()
    app = QApplication(sys.argv)
    app.setApplicationName("ethqual")
    app.setApplicationVersion("0.3.0")
    icon_path = _resolve_icon_path()
    if icon_path is not None:
        app.setWindowIcon(QIcon(str(icon_path)))
    app.setStyleSheet(APP_STYLESHEET)
    win = EthqualMainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
