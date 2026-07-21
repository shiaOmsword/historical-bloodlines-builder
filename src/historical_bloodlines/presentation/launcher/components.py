from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path

from rich.align import Align
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


MENU_WIDTH = 76


def render_header(
    console: Console,
    title: str,
    *,
    subtitle: str | None = None,
) -> None:
    console.clear()
    heading = Text("HISTORICAL BLOODLINES", style="bold white")
    caption = Text(title, style="bold cyan")
    content = Group(Align.center(heading), Align.center(caption))
    console.print(
        Panel(
            content,
            subtitle=subtitle,
            border_style="cyan",
            width=MENU_WIDTH,
        )
    )


def render_menu(
    console: Console,
    items: Iterable[tuple[str, str, str]],
) -> None:
    table = Table(
        show_header=False,
        box=None,
        padding=(0, 1),
        width=MENU_WIDTH - 2,
    )
    table.add_column("Key", justify="right", style="bold cyan", width=4)
    table.add_column("Action", style="bold white", width=24)
    table.add_column("Description", style="dim")

    for key, label, description in items:
        table.add_row(key, label, description)

    console.print(Panel(table, border_style="bright_black", width=MENU_WIDTH))


def render_paths(
    console: Console,
    *,
    input_path: Path,
    output_path: Path,
    page_format: str,
) -> None:
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column(style="bold cyan", width=18)
    table.add_column(style="white")
    table.add_row("Excel", str(input_path))
    table.add_row("Результат", str(output_path))
    table.add_row("Формат страницы", page_format.upper())
    console.print(Panel(table, title="Параметры сборки", border_style="cyan"))


def wait_for_enter(console: Console) -> None:
    console.input("\n[dim]Нажмите Enter, чтобы продолжить...[/dim]")


def graphviz_status() -> tuple[bool, str]:
    dot = shutil.which("dot")
    neato = shutil.which("neato")
    if dot and neato:
        return True, f"dot: {dot}\nneato: {neato}"
    missing = [name for name, value in (("dot", dot), ("neato", neato)) if not value]
    return False, f"Не найдены команды: {', '.join(missing)}"


def open_in_file_manager(path: Path) -> None:
    directory = path if path.is_dir() else path.parent
    directory.mkdir(parents=True, exist_ok=True)

    if os.name == "nt":
        os.startfile(directory)  # type: ignore[attr-defined]
        return
    if sys.platform == "darwin":
        subprocess.Popen(["open", str(directory)])
        return

    opener = shutil.which("xdg-open")
    if opener is None:
        raise RuntimeError("Команда xdg-open не найдена")
    subprocess.Popen([opener, str(directory)])
