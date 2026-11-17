# ethqual v0.2.0 — Cualificación y Diagnóstico de Enlaces Ethernet

Herramienta CLI y GUI nativa multiplataforma (macOS Apple Silicon/Intel, Windows 11 y Linux) en Python 3.10+ para cualificar enlaces Ethernet punto a punto entre dos notebooks estándar sin hardware certificador dedicado.

> **Alcance técnico:** `ethqual` cualifica el enlace Ethernet activo (capas 1/2/4: negociación PHY, throughput TCP multi-flujo/Full-Duplex, pérdida/jitter UDP, integridad de datos y telemetría NIC). **No sustituye** a un certificador físico RF (ej. Fluke DSX-5000/8000) para medición de NEXT, FEXT, atenuación en dB o resistencia DC bajo ANSI/TIA-568.2-D.

---

## Características Principales

- **Arquitectura Cliente / Servidor desacoplada:** Canal de control TCP con framing binario (`!I` + JSON) y sockets efímeros puros para tráfico de datos.
- **Autodescubrimiento Zero-Config en LAN:** Detección automática de servidores activos (`--discover` / botón `Buscar LAN`) mediante sondas UDP en puerto `5001`.
- **Port Blink (`--blink` / botón `Blink Puerto`):** Envía ráfagas 1 Hz para hacer parpadear el LED del puerto físico en el switch y localizar tomas sin etiquetar.
- **Wiggle Test en vivo (GUI):** Gráfica temporal en tiempo real con alerta sonora (`beep`) ante micro-cortes mientras se mueven los conectores RJ45.
- **Pruebas de Carga Avanzadas:**
  - Flujos TCP paralelos (`--streams N`), prueba reversa (`--reverse`) y **Full-Duplex simultáneo** (`--full-duplex`).
  - Integridad / BER en capa de aplicación (`CRC32` + patrón determinista).
  - **UDP Jitter (RFC 3550)** y **Barrido UDP por tamaño de trama y PPS (estilo RFC 2544)** (`--udp-sweep`).
- **Telemetría NIC y AutoTest:** Lectura diferencial de contadores (`errin`, `errout`, `dropin`, `dropout`, `rx_crc_errors` en Linux), Gateway, DNS, detección de conflicto IP/doble DHCP (`--check-dhcp`), `ethtool --cable-test` y descubrimiento pasivo **LLDP** (`lldpctl`/`networkctl`) en Linux.
- **Modo Soak Test:** Pruebas periódicas de estabilidad prolongada (`--soak-rounds`, `--soak-interval`) con resumen de tendencia.
- **Flujo de Obra, Etiquetas y Remediales:** Perfiles preconfigurados (`1000BASE-T Oficina`, `2.5GBASE-T Enlace`, `VoIP / Streaming`, `Estrés Full-Duplex`), autoguardado de lote (`~/.ethqual/last_session.jsonl`), remediales accionables, reporte HTML imprimible con códigos de barras Code-39 SVG y exportación de etiquetas para patch panel (`--labels-csv` / HTML).

---

## Estructura del Proyecto

```text
ethqual/
├── ethqual/
│   ├── core/
│   │   ├── protocol.py       # Framing binario/JSON, cabeceras BER y UDP
│   │   ├── metrics.py        # Telemetría NIC, ICMP, ARP y análisis PHY
│   │   ├── autotest.py       # Gateway, DNS y ethtool --cable-test (Linux)
│   │   ├── lldp.py           # Descubrimiento pasivo LLDP (Linux)
│   │   ├── discovery.py      # Beacon LAN UDP y Port Blink
│   │   ├── remediation.py    # Motor de causas probables y acciones correctivas
│   │   ├── reports.py        # Generador de reporte HTML imprimible
│   │   ├── engine.py         # Orquestador cliente y perfiles
│   │   └── server_engine.py  # Servidor concurrente multi-flujo / Full-Duplex / Wiggle
│   └── gui/
│       └── app.py            # Interfaz gráfica nativa PySide6 (Qt 6)
├── tests/
│   └── test_ethqual.py       # Suite de pruebas unitarias
├── client.py                 # Punto de entrada CLI Cliente
├── server.py                 # Punto de entrada CLI Servidor
├── gui.py                    # Punto de entrada GUI
├── GUIA_USO.md               # Manual de usuario en campo
├── pyproject.toml            # Empaquetado e instalación
└── requirements.txt          # Dependencias base
```

---

## Instalación

```bash
python3 -m venv .venv
source .venv/bin/activate  # En Windows: .venv\Scripts\activate
pip install -r requirements.txt
# Para interfaz gráfica nativa:
pip install PySide6
```

---

## Uso Rápido

### Interfaz Gráfica (Recomendado en campo)
```bash
python3 gui.py
```

### Línea de Comandos (CLI)
1. **Servidor (equipo pasivo):**
   ```bash
   python3 server.py --port 5000
   ```
2. **Descubrir servidores en LAN:**
   ```bash
   python3 client.py --discover
   ```
3. **Ejecutar cualificación con perfil y reporte HTML:**
   ```bash
   python3 client.py --server 192.168.50.20 --project "Edificio Central" --cable-id "P2-R1-04" --profile "1000BASE-T Oficina" --report-html reporte_obra.html
   ```
4. **Cualificación máxima (Full-Duplex + Barrido UDP):**
   ```bash
   python3 client.py --server 192.168.50.20 --streams 4 --full-duplex --udp-sweep --summary-md resumen.md
   ```

---

## Pruebas y Empaquetado

```bash
# Pruebas unitarias
python3 -m unittest discover -s tests -v

# Empaquetado Wheel (universal para macOS, Windows 11 y Linux)
pip wheel --no-deps --no-build-isolation -w dist .

# Compilación de ejecutable nativo local (PyInstaller)
pyinstaller --windowed --name ethqual --icon ethqual/assets/icon.icns --add-data "ethqual/assets/icon.png:ethqual/assets" gui.py
```

### Compilación multiplataforma (macOS Intel, macOS ARM64, Windows 11 y Linux)
PyInstaller no realiza *cross-compilation* entre sistemas operativos. El workflow [`.github/workflows/build-native.yml`](.github/workflows/build-native.yml) compila automáticamente los 4 binarios nativos con su icono correspondiente al publicar un tag `v*` (por ejemplo `git push origin v0.2.0`) o mediante ejecución manual (`workflow_dispatch`) en GitHub Actions.

Consulta el manual completo de operación en [GUIA_USO.md](GUIA_USO.md) y el historial de versiones en [CHANGELOG.md](CHANGELOG.md).
