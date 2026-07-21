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
