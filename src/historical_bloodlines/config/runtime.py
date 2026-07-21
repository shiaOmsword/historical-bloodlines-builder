from __future__ import annotations

import os
import shutil
import subprocess
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


_VALIDATED_GRAPHVIZ_DIRECTORIES: set[Path] = set()
_PLUGIN_DIRECTORY_MARKER = ".historical-bloodlines-plugin-dir"
_LOCATION_MARKER = ".historical-bloodlines-location"


def prepare_bundled_graphviz(
    resources_dir: Path | None = None,
    *,
    require_bundled: bool | None = None,
    validate_plugins: bool | None = None,
) -> GraphvizRuntime:
    """Prefer bundled Graphviz and fall back to PATH in development.

    Windows Graphviz distributions do not all store plug-ins in the same
    directory. The build writes a relative plug-in-directory marker; when the
    marker is absent, the runtime discovers the directory containing
    ``gvplugin*.dll``. A real neato-to-SVG probe is used as the source of truth
    instead of assuming that ``bin/config6`` must exist.
    """
    resources = resources_dir or runtime_resources_dir()
    bundled_root = resources / "graphviz"
    bundled_bin = bundled_root / "bin"
    executable_suffix = ".exe" if os.name == "nt" else ""
    bundled_dot = bundled_bin / f"dot{executable_suffix}"
    bundled_neato = bundled_bin / f"neato{executable_suffix}"

    if bundled_dot.is_file() and bundled_neato.is_file():
        _prepend_to_path(bundled_bin)

        plugin_directory = bundled_bin
        if os.name == "nt":
            plugin_directory = _resolve_windows_plugin_directory(
                bundled_root,
                bundled_bin,
            )
        os.environ["GVBINDIR"] = str(plugin_directory)

        should_validate = (
            bool(getattr(sys, "frozen", False))
            if validate_plugins is None
            else validate_plugins
        )
        if os.name == "nt" and should_validate:
            _ensure_windows_plugins(
                bundled_dot,
                bundled_bin,
                plugin_directory,
            )

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


def _resolve_windows_plugin_directory(
    graphviz_root: Path,
    executable_directory: Path,
) -> Path:
    marker = graphviz_root / _PLUGIN_DIRECTORY_MARKER
    marked_directory = _read_plugin_directory_marker(graphviz_root, marker)
    if marked_directory is not None:
        return marked_directory

    candidates = _windows_plugin_directory_candidates(
        graphviz_root,
        executable_directory,
    )
    if not candidates:
        return executable_directory
    return candidates[0]


def _read_plugin_directory_marker(
    graphviz_root: Path,
    marker: Path,
) -> Path | None:
    try:
        relative_value = marker.read_text(encoding="utf-8-sig").strip()
    except (FileNotFoundError, OSError, UnicodeError):
        return None

    if not relative_value:
        return None

    # The marker is created on Windows, but keeping separator handling neutral
    # makes validation and tests deterministic on every development platform.
    relative_value = relative_value.replace("\\", os.sep).replace("/", os.sep)

    try:
        candidate = (graphviz_root / relative_value).resolve()
        root = graphviz_root.resolve()
        candidate.relative_to(root)
    except (OSError, ValueError):
        return None

    return candidate if candidate.is_dir() else None


def _windows_plugin_directory_candidates(
    graphviz_root: Path,
    executable_directory: Path,
) -> list[Path]:
    candidates: list[Path] = []

    try:
        plugin_files = sorted(graphviz_root.rglob("*gvplugin*.dll"))
    except OSError:
        plugin_files = []

    for plugin_file in plugin_files:
        directory = plugin_file.parent
        if directory not in candidates:
            candidates.append(directory)

    if executable_directory not in candidates:
        candidates.append(executable_directory)
    return candidates


def _ensure_windows_plugins(
    dot_path: Path,
    executable_directory: Path,
    plugin_directory: Path,
) -> None:
    normalized_plugin_directory = plugin_directory.resolve()
    if normalized_plugin_directory in _VALIDATED_GRAPHVIZ_DIRECTORIES:
        return

    marker = plugin_directory / _LOCATION_MARKER
    current_location = str(normalized_plugin_directory)
    recorded_location = _read_location_marker(marker)
    configuration: subprocess.CompletedProcess[bytes] | None = None

    # A generated Graphviz plug-in registry may contain paths from the machine
    # where the application was built. Rebuild it once after relocation. Some
    # Graphviz builds use statically registered plug-ins and create no config6,
    # so the subsequent render probe, not the file's presence, decides success.
    if recorded_location != current_location:
        configuration = _rebuild_plugin_configuration(
            dot_path,
            executable_directory,
            plugin_directory,
        )

    first_probe = _probe_neato_plugin(
        dot_path,
        executable_directory,
        plugin_directory,
    )
    if first_probe.returncode != 0:
        configuration = _rebuild_plugin_configuration(
            dot_path,
            executable_directory,
            plugin_directory,
        )
        second_probe = _probe_neato_plugin(
            dot_path,
            executable_directory,
            plugin_directory,
        )
        if second_probe.returncode != 0:
            details = _decode_process_output(second_probe.stderr)
            config_details = _decode_process_output(
                configuration.stderr if configuration is not None else None
            )
            diagnostic = details or config_details or "Graphviz не сообщил подробностей."
            raise GraphvizRuntimeError(
                "Portable Graphviz найден, но plug-in neato недоступен. "
                "Не удалось настроить каталог plug-inов.\n"
                f"Исполняемые файлы: {executable_directory}\n"
                f"Plug-inы: {plugin_directory}\n"
                f"Диагностика: {diagnostic}"
            )

    _write_location_marker(marker, current_location)
    _VALIDATED_GRAPHVIZ_DIRECTORIES.add(normalized_plugin_directory)


def _read_location_marker(marker: Path) -> str | None:
    try:
        return marker.read_text(encoding="utf-8").strip()
    except (FileNotFoundError, OSError, UnicodeError):
        return None


def _write_location_marker(marker: Path, location: str) -> None:
    try:
        marker.write_text(location, encoding="utf-8")
    except OSError as exc:
        raise GraphvizRuntimeError(
            "Portable Graphviz нужно настроить после распаковки, но папка "
            "приложения недоступна для записи. Распакуйте архив в обычную "
            "пользовательскую папку и запустите приложение снова.\n"
            f"Файл: {marker}"
        ) from exc


def _rebuild_plugin_configuration(
    dot_path: Path,
    executable_directory: Path,
    plugin_directory: Path,
) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            [str(dot_path), "-c"],
            cwd=plugin_directory,
            env=_graphviz_environment(
                executable_directory,
                plugin_directory,
            ),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except OSError as exc:
        raise GraphvizRuntimeError(
            f"Не удалось запустить portable Graphviz: {dot_path}"
        ) from exc


def _probe_neato_plugin(
    dot_path: Path,
    executable_directory: Path,
    plugin_directory: Path,
) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            [str(dot_path), "-Kneato", "-Tsvg"],
            cwd=plugin_directory,
            env=_graphviz_environment(
                executable_directory,
                plugin_directory,
            ),
            input=b"graph portable_probe { a -- b }\n",
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            check=False,
        )
    except OSError as exc:
        raise GraphvizRuntimeError(
            f"Не удалось запустить portable Graphviz: {dot_path}"
        ) from exc


def _graphviz_environment(
    executable_directory: Path,
    plugin_directory: Path,
) -> dict[str, str]:
    environment = os.environ.copy()
    environment["GVBINDIR"] = str(plugin_directory)
    current_path = environment.get("PATH", "")
    path_items = [str(executable_directory)]
    if plugin_directory != executable_directory:
        path_items.append(str(plugin_directory))
    if current_path:
        path_items.append(current_path)
    environment["PATH"] = os.pathsep.join(path_items)
    return environment


def _decode_process_output(data: bytes | None) -> str:
    if not data:
        return ""
    return data.decode("utf-8", errors="replace").strip()


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
