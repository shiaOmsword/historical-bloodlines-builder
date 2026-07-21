from pathlib import Path

import typer
from rich.console import Console

from historical_bloodlines.application.services.build_genealogy import (
    BuildGenealogyUseCase,
    PageFormat,
)
from historical_bloodlines.config import get_settings

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
        help="Output .pdf, .svg or .png path.",
    ),
    page_format: PageFormat = typer.Option(
        PageFormat.A5,
        "--page-format",
        "--paper",
        help="Landscape PDF paper size: a5 (default) or a4.",
        case_sensitive=False,
    ),
) -> None:
    settings = get_settings()
    source = input_path or settings.input_file
    target = output_path or settings.output_file

    try:
        result = BuildGenealogyUseCase().execute(
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
