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
    """Exercise bundled resources plus the PDF and publisher EPS pipelines."""
    try:
        runtime = prepare_bundled_graphviz()
        source = _example_workbook()
        with TemporaryDirectory(prefix="bloodlines_self_test_") as temporary:
            temporary_path = Path(temporary)
            pdf_result = BuildGenealogyUseCase().execute(
                source,
                temporary_path / "self-test.pdf",
                page_format=PageFormat.A5,
            )
            if (
                not pdf_result.output_path.is_file()
                or pdf_result.output_path.stat().st_size == 0
            ):
                raise RuntimeError("Тестовый PDF не был создан.")

            eps_result = BuildGenealogyUseCase().execute(
                source,
                temporary_path / "self-test.eps",
            )
            eps_files = tuple(eps_result.output_path.glob("*.eps"))
            preview_files = tuple(eps_result.output_path.glob("*.preview.png"))
            if not eps_files or any(path.stat().st_size == 0 for path in eps_files):
                raise RuntimeError("Тестовый EPS не был создан.")
            if not preview_files or any(path.stat().st_size == 0 for path in preview_files):
                raise RuntimeError("Тестовый PNG-preview для EPS не был создан.")
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
        "Полный цикл Excel → Graphviz → PDF/EPS выполнен.\n"
        f"Graphviz: {runtime.source}\n"
        f"dot: {runtime.dot_path}\n"
        f"neato: {runtime.neato_path}"
    )
