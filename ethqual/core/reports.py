"""Generador de reportes HTML imprimibles estilo LinkWare para entregas de obra."""

from __future__ import annotations

import csv
import html
from pathlib import Path
from typing import Any


_CODE39_TABLE: dict[str, str] = {
    "0": "nnnwwnwnn", "1": "wnnwnnnnw", "2": "nnwwnnnnw", "3": "wnwwnnnnn",
    "4": "nnnwwnnnw", "5": "wnnwwnnnn", "6": "nnwwwnnnn", "7": "nnnwnnwnw",
    "8": "wnnwnnwnn", "9": "nnwwnnwnn", "A": "wnnnnwnnw", "B": "nnwnnwnnw",
    "C": "wnwnnwnnn", "D": "nnnnwwnnw", "E": "wnnnwwnnn", "F": "nnwnwwnnn",
    "G": "nnnnnwwnw", "H": "wnnnnwwnn", "I": "nnwnnwwnn", "J": "nnnnwwwnn",
    "K": "wnnnnnnww", "L": "nnwnnnnww", "M": "wnwnnnnwn", "N": "nnnnwnnww",
    "O": "wnnnwnnwn", "P": "nnwnwnnwn", "Q": "nnnnnnwww", "R": "wnnnnnwwn",
    "S": "nnwnnnwwn", "T": "nnnnwnwwn", "U": "wwnnnnnnw", "V": "nwwnnnnnw",
    "W": "wwwnnnnnn", "X": "nwnnwnnnw", "Y": "wwnnwnnnn", "Z": "nwwnwnnnn",
    "-": "nwnnnnwnw", ".": "wwnnnnwnn", " ": "nwwnnnwnn", "*": "nwnnwnwnn",
}


def _code39_svg(text: str, height: int = 24) -> str:
    """Genera un código de barras Code-39 SVG escaneable sin dependencias externas."""
    cleaned = "".join(ch for ch in text.upper() if ch in _CODE39_TABLE and ch != "*") or "TOMA"
    encoded = f"*{cleaned}*"
    x = 0
    rects: list[str] = []
    for ch in encoded:
        pattern = _CODE39_TABLE[ch]
        for idx, sym in enumerate(pattern):
            w = 3 if sym == "w" else 1
            if idx % 2 == 0:
                rects.append(f'<rect x="{x}" y="0" width="{w}" height="{height}" fill="#0F172A"/>')
            x += w
        x += 1
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{x}" height="{height}" viewBox="0 0 {x} {height}">{"".join(rects)}</svg>'


def _badge_class(verdict: str) -> str:
    if verdict == "APROBADO":
        return "pass"
    if verdict == "ADVERTENCIA":
        return "warn"
    return "fail"


def write_html_report(path: str, reports: list[dict[str, Any]]) -> None:
    """Genera un reporte HTML autocontenido e imprimible para 1 o N tomas de un proyecto."""
    if not reports:
        raise ValueError("Se requiere al menos un reporte para generar el HTML.")

    first_meta = reports[0].get("metadata", {})
    project = html.escape(str(first_meta.get("project_name") or "Proyecto Ethernet"))
    technician = html.escape(str(first_meta.get("technician") or "No especificado"))
    generated = html.escape(str(reports[-1].get("metadata", {}).get("timestamp_utc", "")))

    total = len(reports)
    passed = sum(1 for r in reports if r.get("verdict") == "APROBADO")
    warned = sum(1 for r in reports if r.get("verdict") == "ADVERTENCIA")
    failed = sum(1 for r in reports if r.get("verdict") == "FALLO")

    rows_html: list[str] = []
    for idx, rep in enumerate(reports, start=1):
        meta = rep.get("metadata", {})
        tests = rep.get("tests", {})
        conn = tests.get("connectivity_layer2", {})
        tp_rx = tests.get("throughput", {}).get("server_rx", {})
        tp_rev = tests.get("throughput", {}).get("reverse")
        ber = tests.get("data_integrity_ber", {}).get("server_rx", {})
        phy_c = rep.get("phy_link_diagnosis", {}).get("client", {})
        phy_s = rep.get("phy_link_diagnosis", {}).get("server", {})
        lldp = rep.get("network_autotest", {}).get("lldp", {})
        neighbors = lldp.get("neighbors") or []
        if neighbors:
            nb = neighbors[0]
            lldp_txt = html.escape(
                f"{nb.get('switch_name') or '?'} / {nb.get('port_id') or '?'} (VLAN {nb.get('vlan_id') or '-'})"
            )
        else:
            lldp_txt = "<span class='muted'>N/A</span>"
        verdict = str(rep.get("verdict", "FALLO"))
        cable_id = html.escape(str(meta.get("cable_id") or f"TOMA-{idx:02d}"))
        profile = html.escape(str(meta.get("profile_name") or "Estándar"))
        rev_txt = (
            f" / {tp_rev['client_rx'].get('throughput_mbps')} Mbps"
            if tp_rev and tp_rev.get("client_rx")
            else ""
        )
        reasons = "; ".join(rep.get("verdict_reasons") or []) or "Dentro de umbrales"
        rem_list = rep.get("remediations") or []
        rem_html = (
            "<br>".join(
                f"<span class='muted'><b>Solución:</b> {html.escape(rm['action'])}</span>"
                for rm in rem_list
            )
            if rem_list
            else ""
        )

        rows_html.append(
            f"<tr>"
            f"<td><strong>{cable_id}</strong><br><span class='muted'>{profile}</span><br>{_code39_svg(cable_id, 18)}</td>"
            f"<td><span class='badge {_badge_class(verdict)}'>{html.escape(verdict)}</span></td>"
            f"<td>{tp_rx.get('throughput_mbps', 0)} Mbps{rev_txt}</td>"
            f"<td>{conn.get('rtt_avg_ms', '—')} ms ({conn.get('packet_loss_pct', 0)}%)</td>"
            f"<td>{phy_c.get('link_info', {}).get('speed_mbps', '—')} / "
            f"{phy_s.get('link_info', {}).get('speed_mbps', '—')} Mbps</td>"
            f"<td>{lldp_txt}</td>"
            f"<td>{ber.get('corrupted_blocks', 0)} err</td>"
            f"<td class='muted'>{html.escape(reasons)}{'<br>' + rem_html if rem_html else ''}</td>"
            f"</tr>"
        )

    doc = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>Reporte de Cualificación Ethernet — {project}</title>
<style>
  body {{ font-family: -apple-system, "Segoe UI", Inter, sans-serif; color: #111827; margin: 32px; background: #fff; }}
  .header {{ display: flex; justify-content: space-between; align-items: flex-start; border-bottom: 2px solid #1E293B; padding-bottom: 16px; margin-bottom: 20px; }}
  h1 {{ margin: 0 0 6px 0; font-size: 22px; color: #0F172A; }}
  .meta {{ font-size: 13px; color: #475569; line-height: 1.5; }}
  .summary {{ display: flex; gap: 12px; margin-bottom: 22px; }}
  .stat {{ flex: 1; border: 1px solid #CBD5E1; border-radius: 8px; padding: 12px 16px; }}
  .stat .k {{ font-size: 11px; text-transform: uppercase; color: #64748B; font-weight: 600; }}
  .stat .v {{ font-size: 22px; font-weight: 700; margin-top: 4px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th {{ text-align: left; background: #F1F5F9; color: #334155; padding: 10px; border-bottom: 2px solid #CBD5E1; font-size: 12px; text-transform: uppercase; }}
  td {{ padding: 10px; border-bottom: 1px solid #E2E8F0; vertical-align: top; }}
  .badge {{ display: inline-block; padding: 3px 9px; border-radius: 999px; font-size: 11px; font-weight: 700; }}
  .pass {{ background: #D1FAE5; color: #065F46; }}
  .warn {{ background: #FEF3C7; color: #92400E; }}
  .fail {{ background: #FEE2E2; color: #991B1B; }}
  .muted {{ color: #64748B; font-size: 12px; }}
  .footer {{ margin-top: 28px; padding-top: 12px; border-top: 1px solid #CBD5E1; font-size: 11px; color: #64748B; }}
  @media print {{ body {{ margin: 12mm; }} }}
</style>
</head>
<body>
  <div class="header">
    <div>
      <h1>Reporte de Cualificación de Enlaces Ethernet</h1>
      <div class="meta">
        <strong>Proyecto:</strong> {project} &nbsp;|&nbsp;
        <strong>Técnico:</strong> {technician} &nbsp;|&nbsp;
        <strong>Fecha (UTC):</strong> {generated}
      </div>
    </div>
    <div class="meta" style="text-align:right">
      <strong>Herramienta:</strong> ethqual<br>
      <strong>Alcance:</strong> Cualificación activa IEEE 802.3 (no certificación RF TIA-568)
    </div>
  </div>
  <div class="summary">
    <div class="stat"><div class="k">Tomas Evaluadas</div><div class="v">{total}</div></div>
    <div class="stat"><div class="k">Aprobadas</div><div class="v" style="color:#059669">{passed}</div></div>
    <div class="stat"><div class="k">Advertencias</div><div class="v" style="color:#D97706">{warned}</div></div>
    <div class="stat"><div class="k">Fallos</div><div class="v" style="color:#DC2626">{failed}</div></div>
  </div>
  <table>
    <thead>
      <tr>
        <th>ID Toma / Perfil</th>
        <th>Veredicto</th>
        <th>Throughput TCP</th>
        <th>ICMP RTT / Pérdida</th>
        <th>Enlace PHY (C / S)</th>
        <th>Switch / Puerto (LLDP)</th>
        <th>BER App</th>
        <th>Observaciones</th>
      </tr>
    </thead>
    <tbody>
      {"".join(rows_html)}
    </tbody>
  </table>
  <div class="footer">
    Generado por ethqual. Nota técnica: Este documento cualifica el rendimiento, integridad y negociación de enlace activo entre dos equipos. No reemplaza una certificación de capa física RF (NEXT/FEXT/Atenuación en dB) conforme a ANSI/TIA-568.2-D.
  </div>
</body>
</html>
"""
    Path(path).write_text(doc, encoding="utf-8")


def write_labels_csv(path: str, reports: list[dict[str, Any]]) -> None:
    """Exporta etiquetas por toma en CSV listas para impresoras de rotulación (Dymo/P-Touch)."""
    with Path(path).open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["Proyecto", "ID_Toma", "Veredicto", "Velocidad_Mbps", "Throughput_Mbps", "Fecha_UTC"])
        for idx, rep in enumerate(reports, start=1):
            meta = rep.get("metadata", {})
            tp = rep.get("tests", {}).get("throughput", {}).get("server_rx", {}).get("throughput_mbps", 0)
            spd = rep.get("phy_link_diagnosis", {}).get("client", {}).get("link_info", {}).get("speed_mbps", "")
            writer.writerow([
                meta.get("project_name") or "Proyecto",
                meta.get("cable_id") or f"TOMA-{idx:02d}",
                rep.get("verdict", ""),
                spd,
                tp,
                meta.get("timestamp_utc", ""),
            ])


def write_labels_html(path: str, reports: list[dict[str, Any]]) -> None:
    """Genera una hoja HTML imprimible de etiquetas para patch panel con código de barras."""
    cards: list[str] = []
    for idx, rep in enumerate(reports, start=1):
        meta = rep.get("metadata", {})
        cable_id = html.escape(str(meta.get("cable_id") or f"TOMA-{idx:02d}"))
        proj = html.escape(str(meta.get("project_name") or "Proyecto"))
        spd = rep.get("phy_link_diagnosis", {}).get("client", {}).get("link_info", {}).get("speed_mbps", "—")
        verdict = html.escape(str(rep.get("verdict", "")))
        cards.append(
            f"<div class='label'>"
            f"<div class='cid'>{cable_id}</div>"
            f"<div class='sub'>{proj} · {spd} Mbps · <b>{verdict}</b></div>"
            f"<div class='bc'>{_code39_svg(cable_id, 22)}</div>"
            f"</div>"
        )
    doc = (
        "<!DOCTYPE html><html lang='es'><head><meta charset='utf-8'>"
        "<title>Etiquetas Patch Panel — ethqual</title>"
        "<style>body{font-family:sans-serif;margin:16px}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}"
        ".label{border:1px dashed #94A3B8;padding:10px;border-radius:6px;text-align:center}"
        ".cid{font-size:15px;font-weight:700}.sub{font-size:11px;color:#475569;margin:4px 0}.bc{margin-top:4px}</style>"
        f"</head><body><div class='grid'>{''.join(cards)}</div></body></html>"
    )
    Path(path).write_text(doc, encoding="utf-8")
