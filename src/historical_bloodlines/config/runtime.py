from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from historical_bloodlines.config.paths import runtime_resources_dir


class GraphvizRuntimeError(RuntimeError):
    """Raised when the renderer cannot find the required Graphviz programs."""


@dataclass(frozen=True, slots=True)
class GraphvizRuntime:
    dot_path: Path
    neato_path: Path
    source: str
    root: Path | None = None


def prepare_bundled_graphviz(
    resources_dir: Path | None = None,
    *,
    require_bundled: bool | None = None,
) -> GraphvizRuntime:
    """Prefer the bundled Graphviz runtime and fall back to PATH in development.

    Frozen builds require the bundled runtime by default. Source launches may use
    a system Graphviz installation so contributors do not need a vendor folder.
    """
    resources = resources_dir or runtime_resources_dir()
    bundled_root = resources / "graphviz"
    bundled_bin = bundled_root / "bin"
    executable_suffix = ".exe" if os.name == "nt" else ""
    bundled_dot = bundled_bin / f"dot{executable_suffix}"
    bundled_neato = bundled_bin / f"neato{executable_suffix}"

    if bundled_dot.is_file() and bundled_neato.is_file():
        _prepend_to_path(bundled_bin)
        # Windows Graphviz normally stores config6 and plugin DLLs in bin.
        # Setting GVBINDIR makes that location explicit for portable builds.
        os.environ["GVBINDIR"] = str(bundled_bin)
        return GraphvizRuntime(
            dot_path=bundled_dot,
            neato_path=bundled_neato,
            source="bundled",
            root=bundled_root,
        )

    must_be_bundled = (
        getattr(sys, "frozen", False)
        if require_bundled is None
        else require_bundled
    )
    if must_be_bundled:
        raise GraphvizRuntimeError(
            "В комплекте приложения отсутствует Graphviz. "
            "Ожидались файлы graphviz/bin/dot.exe и graphviz/bin/neato.exe."
        )

    system_dot = shutil.which("dot")
    system_neato = shutil.which("neato")
    if system_dot and system_neato:
        return GraphvizRuntime(
            dot_path=Path(system_dot),
            neato_path=Path(system_neato),
            source="system",
        )

    raise GraphvizRuntimeError(
        "Graphviz не найден. Для запуска из исходников установите Graphviz "
        "и добавьте dot/neato в PATH."
    )


def _prepend_to_path(directory: Path) -> None:
    current_path = os.environ.get("PATH", "")
    path_items = [item for item in current_path.split(os.pathsep) if item]
    normalized_directory = os.path.normcase(os.path.abspath(directory))
    if any(
        os.path.normcase(os.path.abspath(item)) == normalized_directory
        for item in path_items
    ):
        return
    os.environ["PATH"] = str(directory) + os.pathsep + current_path
