from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from rich.console import Console
from rich.panel import Panel

from historical_bloodlines.application.services.build_genealogy import (
    BuildGenealogyUseCase,
    PageFormat,
)
from historical_bloodlines.config import (
    GraphvizRuntime,
    prepare_bundled_graphviz,
    runtime_resources_dir,
)


def run_self_test(console: Console) -> int:
    """Exercise bundled resources, Graphviz and the complete PDF pipeline."""
    try:
        runtime = prepare_bundled_graphviz()
        source = _example_workbook()
        with TemporaryDirectory(prefix="bloodlines_self_test_") as temporary:
            output = Path(temporary) / "self-test.pdf"
            result = BuildGenealogyUseCase().execute(
                source,
                output,
                page_format=PageFormat.A5,
            )
            if not result.output_path.is_file() or result.output_path.stat().st_size == 0:
                raise RuntimeError("Тестовый PDF не был создан.")
    except Exception as exc:
        console.print(
            Panel(
                str(exc),
                title="Portable self-test: ошибка",
                border_style="red",
            )
        )
        return 1

    console.print(
        Panel(
            _runtime_description(runtime),
            title="Portable self-test: успешно",
            border_style="green",
        )
    )
    return 0


def _example_workbook() -> Path:
    source = runtime_resources_dir() / "examples" / "input.example.xlsx"
    if not source.is_file():
        raise FileNotFoundError(
            f"В комплекте отсутствует тестовая книга: {source}"
        )
    return source


def _runtime_description(runtime: GraphvizRuntime) -> str:
    return (
        "Полный цикл Excel → Graphviz → PDF выполнен.\n"
        f"Graphviz: {runtime.source}\n"
        f"dot: {runtime.dot_path}\n"
        f"neato: {runtime.neato_path}"
    )
