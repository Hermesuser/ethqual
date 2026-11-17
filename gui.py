"""Punto de entrada de la interfaz gráfica nativa de ethqual."""

from __future__ import annotations

from ethqual.gui.app import APP_STYLESHEET, EthqualMainWindow, main

__all__ = ["APP_STYLESHEET", "EthqualMainWindow", "main"]

if __name__ == "__main__":
    main()
