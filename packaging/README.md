# Windows portable build

Build on Windows because PyInstaller creates platform-specific executables.

```powershell
poetry install --with dev
.\scripts\build_windows.ps1
```

When Graphviz is not on `PATH`, pass its installation directory:

```powershell
.\scripts\build_windows.ps1 -GraphvizHome "C:\Program Files\Graphviz"
```

Output:

```text
dist/HistoricalBloodlines/HistoricalBloodlines.exe
release/HistoricalBloodlines-windows-x64.zip
```

The build script runs tests, copies Graphviz into the bundle, creates an onedir
build and executes `HistoricalBloodlines.exe --self-test` with Python and system
Graphviz removed from `PATH`. The test copy is placed in a directory containing
spaces to exercise portable path handling.
