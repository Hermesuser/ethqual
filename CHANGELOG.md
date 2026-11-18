# Changelog

Todos los cambios relevantes de **ethqual** se documentan en este archivo.

## [0.3.0] — 2026-11-18
### Mejorado
- **Interfaz gráfica responsive:** `FlowLayout` adaptable, scroll vertical automático, 3 breakpoints de tarjetas KPI (1/2/4 columnas) desde `360×440`, búsqueda LAN asíncrona (`DiscoverWorker`), exclusión mutua de pruebas, auto-reset a `"Personalizado"` y persistencia de preferencias/geometría (`~/.ethqual/prefs.json`).
- **Gestión de lote y atajos:** diálogo **Ver Lote** con eliminación por fila, botón **Deshacer última**, botón **Actualizar IPs** en Modo Servidor y atajos `Ctrl+Enter` / `Esc`.
- **Motor y reportes:** cancelación completa en todas las fases (`cancel_event`), servidor concurrente por sesión (`Semaphore(4)`), pacing UDP híbrido, propagación explícita de errores del servidor (`_recv_ok_or_raise`), reportes HTML/etiquetas responsive y selección de gateway por menor métrica en Windows.

## [0.2.0] — 2026-11-17
### Añadido
- **Icono oficial minimalista** (`ethqual/assets/icon.svg`, `.png`, `.icns`, `.ico`) integrado en ventana Qt y bundles nativos.
- **Autodescubrimiento LAN Zero-Config:** `ServerBeacon` (UDP `5001`), `--discover` en CLI, botón `Buscar LAN` y selector desplegable de servidores en GUI.
- **Port Blink:** `--blink` en CLI y botón `Blink Puerto` en GUI (1 Hz para localizar puerto físico en switch).
- **Wiggle Test en vivo:** Comando `START_WIGGLE`, gráfica temporal `WiggleSparkline` y alerta sonora (`beep`) ante micro-cortes.
- **Modo Soak Test:** Estabilidad prolongada por rondas (`--soak-rounds`, `--soak-interval` y control `Soak` en GUI).
- **AutoTest avanzado:** Detección de conflicto de IP por ARP, escaneo opcional de doble DHCP (`--check-dhcp`) y consulta pasiva LLDP (`lldpctl`/`networkctl` en Linux).
- **Etiquetas y Reportes:** Hoja imprimible HTML (`write_labels_html`), exportación CSV (`--labels-csv`), códigos de barras Code-39 SVG escaneables y columna LLDP en el Reporte HTML.
- **Resiliencia y UX:** Botón `Cancelar`, autoguardado de lote (`~/.ethqual/last_session.jsonl`), auto-incremento de `ID Toma` y manejo de ICMP filtrado en Windows 11.

## [0.1.0] — 2026-11-16
### Añadido
- MVP Cliente/Servidor TCP con protocolo híbrido (`!I` + JSON y sockets de datos efímeros).
- Pruebas secuenciales: Conectividad ICMP/ARP, Throughput TCP (multi-flujo, reverso y Full-Duplex simultáneo), Integridad BER, UDP Jitter y barrido UDP (RFC 2544).
- Telemetría diferencial de NIC (`psutil` + Linux `sysfs`), diagnóstico PHY (detección 1000 → 100 Mbps) y veredicto (`APROBADO`, `ADVERTENCIA`, `FALLO`).
- Interfaz gráfica nativa PySide6, perfiles preconfigurados, motor de remediales y guía integrada.
