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

The copied Graphviz runtime discovers the directory containing the Windows
plug-in DLLs, runs `dot -c`, and validates the result with a real `neato -> SVG`
smoke test. The render probe is authoritative: some Graphviz builds do not create
`bin/config6` at all. A frozen application repeats the validation after the
onedir folder is moved or extracted. Keep the extracted folder writable.

The launcher switches the Windows console to UTF-8 where possible and uses
adaptive panel widths for cmd.exe, PowerShell and Windows Terminal.
