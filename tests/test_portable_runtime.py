from __future__ import annotations

import os
from pathlib import Path

from rich.console import Console

from historical_bloodlines.config.runtime import prepare_bundled_graphviz
from historical_bloodlines.config.settings import get_settings
from historical_bloodlines.presentation.launcher.self_test import run_self_test


def test_settings_create_user_data_directories(
    tmp_path: Path,
    monkeypatch,
) -> None:
    data_directory = tmp_path / "Documents" / "Historical Bloodlines"
    monkeypatch.setenv("BLOODLINES_DATA_DIR", str(data_directory))
    monkeypatch.delenv("BLOODLINES_INPUT_FILE", raising=False)
    monkeypatch.delenv("BLOODLINES_OUTPUT_FILE", raising=False)
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.input_file == data_directory / "input" / "input.xlsx"
    assert settings.output_file == data_directory / "output" / "genealogy.pdf"
    assert settings.input_file.parent.is_dir()
    assert settings.output_file.parent.is_dir()
    get_settings.cache_clear()


def test_prepare_bundled_graphviz_prefers_vendor_runtime(
    tmp_path: Path,
    monkeypatch,
) -> None:
    bin_directory = tmp_path / "graphviz" / "bin"
    bin_directory.mkdir(parents=True)
    suffix = ".exe" if os.name == "nt" else ""
    dot = bin_directory / f"dot{suffix}"
    neato = bin_directory / f"neato{suffix}"
    dot.write_bytes(b"placeholder")
    neato.write_bytes(b"placeholder")
    monkeypatch.setenv("PATH", "")
    monkeypatch.setenv("GVBINDIR", "")

    runtime = prepare_bundled_graphviz(tmp_path, require_bundled=True)

    assert runtime.source == "bundled"
    assert runtime.dot_path == dot
    assert runtime.neato_path == neato
    assert os.environ["PATH"].split(os.pathsep)[0] == str(bin_directory)
    assert os.environ["GVBINDIR"] == str(bin_directory)


def test_source_self_test_runs_complete_pipeline() -> None:
    exit_code = run_self_test(Console(record=True, width=100))

    assert exit_code == 0


def test_windows_plugin_registry_is_rebuilt_after_portable_relocation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import subprocess

    from historical_bloodlines.config import runtime as runtime_module

    bin_directory = tmp_path / "graphviz" / "bin"
    plugin_directory = tmp_path / "graphviz" / "lib" / "graphviz"
    bin_directory.mkdir(parents=True)
    plugin_directory.mkdir(parents=True)
    dot_path = bin_directory / "dot.exe"
    dot_path.write_bytes(b"placeholder")

    rebuild_calls: list[tuple[Path, Path]] = []
    probe_calls: list[tuple[Path, Path]] = []

    def fake_rebuild(dot: Path, executable: Path, plugins: Path):
        rebuild_calls.append((executable, plugins))
        return subprocess.CompletedProcess([str(dot), "-c"], 0, b"", b"")

    def fake_probe(dot: Path, executable: Path, plugins: Path):
        probe_calls.append((executable, plugins))
        return subprocess.CompletedProcess([str(dot), "-Kneato"], 0, b"", b"")

    monkeypatch.setattr(runtime_module, "_rebuild_plugin_configuration", fake_rebuild)
    monkeypatch.setattr(runtime_module, "_probe_neato_plugin", fake_probe)
    runtime_module._VALIDATED_GRAPHVIZ_DIRECTORIES.clear()

    runtime_module._ensure_windows_plugins(
        dot_path,
        bin_directory,
        plugin_directory,
    )

    assert rebuild_calls == [(bin_directory, plugin_directory)]
    assert probe_calls == [(bin_directory, plugin_directory)]
    marker = plugin_directory / ".historical-bloodlines-location"
    assert marker.read_text(encoding="utf-8") == str(plugin_directory.resolve())
    runtime_module._VALIDATED_GRAPHVIZ_DIRECTORIES.clear()


def test_windows_plugin_directory_uses_build_marker(tmp_path: Path) -> None:
    from historical_bloodlines.config import runtime as runtime_module

    graphviz_root = tmp_path / "graphviz"
    bin_directory = graphviz_root / "bin"
    plugin_directory = graphviz_root / "lib" / "graphviz"
    bin_directory.mkdir(parents=True)
    plugin_directory.mkdir(parents=True)
    (plugin_directory / "gvplugin_neato_layout.dll").write_bytes(b"placeholder")
    (graphviz_root / ".historical-bloodlines-plugin-dir").write_text(
        "lib\\graphviz",
        encoding="ascii",
    )

    result = runtime_module._resolve_windows_plugin_directory(
        graphviz_root,
        bin_directory,
    )

    assert result == plugin_directory.resolve()


def test_windows_plugin_directory_discovers_plugin_dlls(tmp_path: Path) -> None:
    from historical_bloodlines.config import runtime as runtime_module

    graphviz_root = tmp_path / "graphviz"
    bin_directory = graphviz_root / "bin"
    plugin_directory = graphviz_root / "plugins"
    bin_directory.mkdir(parents=True)
    plugin_directory.mkdir(parents=True)
    (plugin_directory / "gvplugin_core.dll").write_bytes(b"placeholder")

    result = runtime_module._resolve_windows_plugin_directory(
        graphviz_root,
        bin_directory,
    )

    assert result == plugin_directory


def test_windows_plugin_probe_can_succeed_without_config6(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import subprocess

    from historical_bloodlines.config import runtime as runtime_module

    bin_directory = tmp_path / "graphviz" / "bin"
    bin_directory.mkdir(parents=True)
    dot_path = bin_directory / "dot.exe"
    dot_path.write_bytes(b"placeholder")

    monkeypatch.setattr(
        runtime_module,
        "_rebuild_plugin_configuration",
        lambda *args: subprocess.CompletedProcess(
            [str(dot_path), "-c"],
            0,
            b"",
            b"",
        ),
    )
    monkeypatch.setattr(
        runtime_module,
        "_probe_neato_plugin",
        lambda *args: subprocess.CompletedProcess(
            [str(dot_path), "-Kneato"],
            0,
            b"",
            b"",
        ),
    )
    runtime_module._VALIDATED_GRAPHVIZ_DIRECTORIES.clear()

    runtime_module._ensure_windows_plugins(
        dot_path,
        bin_directory,
        bin_directory,
    )

    assert not (bin_directory / "config6").exists()
    runtime_module._VALIDATED_GRAPHVIZ_DIRECTORIES.clear()


def test_launcher_width_tracks_terminal_size() -> None:
    from historical_bloodlines.presentation.launcher.components import launcher_width

    assert launcher_width(Console(width=50)) == 48
    assert launcher_width(Console(width=200)) == 88
