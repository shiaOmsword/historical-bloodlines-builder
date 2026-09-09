from pathlib import Path

import typer
from rich.console import Console

from historical_bloodlines.application.services.build_genealogy import (
    BuildGenealogyUseCase,
    PageFormat,
)
from historical_bloodlines.config import get_settings, prepare_bundled_graphviz

app = typer.Typer(
    help="Build book-style historical genealogy diagrams from Excel files.",
    no_args_is_help=True,
)
console = Console()


@app.command()
def build(
    input_path: Path | None = typer.Option(
        None,
        "--input",
        "-i",
        help="Input .xlsx workbook.",
    ),
    output_path: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Output .pdf, .svg, .png or .eps path.",
    ),
    page_format: PageFormat | None = typer.Option(
        None,
        "--page-format",
        "--paper",
        help="Override YAML PDF paper size: a5 or a4 (default without config: a5).",
        case_sensitive=False,
    ),
    render_config: Path | None = typer.Option(
        None,
        "--render-config",
        help="Render YAML path. Overrides BLOODLINES_RENDER_CONFIG and auto-discovery.",
    ),
) -> None:
    prepare_bundled_graphviz()
    settings = get_settings()
    source = input_path or settings.input_file
    target = output_path or settings.output_file

    try:
        builder = BuildGenealogyUseCase(render_config_path=render_config)
        style = builder.render_config
        console.print(
            f"Render config: {style.source_path or 'built-in defaults'}; "
            f"text {style.typography.font_size_pt:g} pt; "
            f"leading {style.typography.resolved_line_height_pt:g} pt"
        )
        result = builder.execute(
            source,
            target,
            page_format=page_format,
        )
    except Exception as exc:
        console.print(f"[red]Build failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(f"[green]Created:[/green] {result.output_path}")
    if result.warnings:
        console.print(f"[yellow]Warnings: {len(result.warnings)}[/yellow]")
        for item in result.warnings:
            console.print(f"  - {item}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
