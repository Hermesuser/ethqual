# Manual de Usuario en Campo — `ethqual v0.2.0`

Esta guía describe paso a paso cómo operar **ethqual** (GUI nativa y CLI) para cualificar enlaces Ethernet entre dos notebooks (macOS Apple Silicon/Intel, Windows 11 o Linux).

---

## 1. Preparación de los Equipos

1. **Conexión física:** Conecta ambas notebooks mediante el cable UTP bajo prueba o a través de un switch no gestionado.
2. **Configuración IP (si no hay servidor DHCP):**
   - **Servidor:** IP estática `192.168.50.20`, máscara `255.255.255.0`.
   - **Cliente:** IP estática `192.168.50.10`, máscara `255.255.255.0`.
3. **Firewall:** Permite **ICMP** y **TCP 5000** (además de UDP `5001` si usas autodescubrimiento LAN).

---

## 2. Operación en Interfaz Gráfica (`python3 gui.py`)

### Paso A — Equipo Servidor
1. Abre la pestaña **Modo Servidor**.
2. Pulsa **Iniciar Servidor** (arranca el receptor TCP y el Beacon de autodescubrimiento LAN).
3. Usa **Copiar IP** si necesitas compartir la IP manualmente.

### Paso B — Equipo Cliente
1. Abre **Modo Cliente**.
2. Completa **Proyecto**, **ID Toma** (ej. `P1-R1-01`), **Técnico** y selecciona un **Perfil**:
   - `1000BASE-T Oficina`: Prueba Gigabit bidireccional (umbral 800 Mbps).
   - `2.5GBASE-T Enlace`: 4 flujos paralelos + Full-Duplex (umbral 2000 Mbps).
   - `VoIP / Streaming`: Jitter UDP + barrido de tramas.
   - `Estrés Full-Duplex`: Carga simultánea TX/RX + barrido UDP.
3. Pulsa **Buscar LAN** para detectar automáticamente servidores en la red y selecciónalo en el desplegable **Servidores LAN** (o escribe la IP manualmente).
4. **Herramientas rápidas en rack:**
   - **Blink Puerto:** Hace parpadear el LED del puerto del switch a 1 Hz durante 8 s para identificar bocas sin etiquetar.
   - **Wiggle Test:** Inicia una gráfica en tiempo real mientras mueves los conectores RJ45; emite una alerta sonora (`beep`) y marca en rojo si ocurre cualquier micro-corte.
   - **Soak / DHCP:** Configura `Soak > 1` para pruebas de estabilidad prolongada en varias rondas, y marca `DHCP` si deseas escanear servidores DHCP duplicados en la red.
5. Pulsa **Iniciar Diagnóstico** (puedes abortar en cualquier momento con **Cancelar**).
6. Al finalizar:
   - El **Stepper de 5 fases** y el **Banner de Veredicto** muestran `APROBADO`, `ADVERTENCIA` o `FALLO`.
   - El panel inferior detalla errores y **Remediales Sugeridos** (causa probable + solución).
   - El **ID Toma** se auto-incrementa (`P1-R1-01` → `P1-R1-02`) y el lote se autoguarda en `~/.ethqual/last_session.jsonl`.
7. Exporta el entregable con **Exportar Reporte HTML** (imprimible a PDF, incluye LLDP y código de barras), **Etiquetas Patch Panel** (hoja HTML o CSV), **Exportar reporte.json** o **Exportar resumen.md**.

---

## 3. Interpretación de Veredictos y Remediales

| Veredicto | Significado | Acción Recomendada |
| :--- | :--- | :--- |
| **APROBADO** | Todos los umbrales cumplidos y cero errores NIC. | Toma lista para entrega. |
| **ADVERTENCIA** | Enlace funcional con degradación o ICMP filtrado. | **1000 → 100 Mbps:** revisar ponchado de pares `4-5` (azul) y `7-8` (marrón).<br>**Half-Duplex:** activar Autonegociación.<br>**ICMP bloqueado:** revisar firewall Windows. |
| **FALLO** | Host inaccesible, throughput bajo, pérdida UDP o corrupción. | Revisar IP/subred/firewall, usar adaptador USB 3.0/PCIe, desactivar *Energy Efficient Ethernet (EEE)* ante pérdida UDP. |
