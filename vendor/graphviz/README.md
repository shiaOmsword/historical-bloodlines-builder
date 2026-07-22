# Bundled Graphviz placeholder

The Windows Graphviz distribution is intentionally not committed to the source
archive. On Windows run:

```powershell
.\scripts\prepare_graphviz.ps1
```

The script copies the complete local Graphviz installation here. The PyInstaller
spec then embeds this directory into `_internal/graphviz` of the portable build.
Keep the Graphviz license files from the distribution when redistributing it.
