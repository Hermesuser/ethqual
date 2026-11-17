# Reglas de Ingeniería — `ethqual`

Para evitar regresiones en ejecutables nativos sin consola (`--windowed`) y multiplataforma (macOS ARM64/Intel, Windows 11, Linux):

1. **Sin ventanas de consola emergentes en Windows:** Todo `subprocess.run(...)` invocado desde el núcleo (`metrics.py`, `autotest.py`, `lldp.py`) debe incluir `**no_window_kwargs()` (`subprocess.CREATE_NO_WINDOW` en Windows).
2. **Registro de errores sin consola:** La GUI (`ethqual/gui/app.py`) debe mantener `_setup_windowed_logging()` (`~/.ethqual/ethqual.log` + `sys.excepthook`) para que ninguna excepción muera en silencio en modo `--windowed`.
3. **Sincronía de versiones:** Al liberar una versión, actualizar simultáneamente `ethqual/__init__.py`, `pyproject.toml`, `CHANGELOG.md`, `app.setApplicationVersion(...)` y `CFBundleShortVersionString` en el bundle macOS.
4. **Compilación multiplataforma:** PyInstaller no realiza cross-compilation entre SO; usar `.github/workflows/build-native.yml` para compilar macOS Intel (`macos-13`), macOS ARM64 (`macos-14`), Windows 11 (`windows-latest`) y Linux (`ubuntu-latest`).
