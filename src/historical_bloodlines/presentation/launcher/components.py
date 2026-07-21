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


MAX_MENU_WIDTH = 88


def launcher_width(console: Console) -> int:
    """Keep all launcher panels aligned and inside the current terminal."""
    available = max(24, console.size.width - 2)
    return min(MAX_MENU_WIDTH, available)


def render_header(
    console: Console,
    title: str,
    *,
    subtitle: str | None = None,
) -> None:
    console.clear(home=True)
    width = launcher_width(console)
    heading = Text("HISTORICAL BLOODLINES", style="bold white")
    caption = Text(title, style="bold cyan")
    content = Group(Align.center(heading), Align.center(caption))
    console.print(
        Panel(
            content,
            subtitle=subtitle,
            border_style="cyan",
            width=width,
        )
    )


def render_menu(
    console: Console,
    items: Iterable[tuple[str, str, str]],
) -> None:
    width = launcher_width(console)
    table = Table(
        show_header=False,
        box=None,
        padding=(0, 1),
        width=width - 2,
    )
    table.add_column("Key", justify="right", style="bold cyan", width=4)
    action_width = min(24, max(14, width // 3))
    table.add_column("Action", style="bold white", width=action_width)
    table.add_column("Description", style="dim")

    for key, label, description in items:
        table.add_row(key, label, description)

    console.print(Panel(table, border_style="bright_black", width=width))


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
    console.print(
        Panel(
            table,
            title="Параметры сборки",
            border_style="cyan",
            width=launcher_width(console),
        )
    )


def wait_for_enter(console: Console) -> None:
    console.input("\n[dim]Нажмите Enter, чтобы продолжить...[/dim]")


def graphviz_status() -> tuple[bool, str]:
    dot = shutil.which("dot")
    neato = shutil.which("neato")
    if dot and neato:
        return True, f"dot: {dot}\nneato: {neato}"
    missing = [name for name, value in (("dot", dot), ("neato", neato)) if not value]
    return False, f"Не найдены команды: {', '.join(missing)}"


def open_path(path: Path) -> None:
    target = path.expanduser().resolve()
    if not target.exists():
        raise FileNotFoundError(f"Путь не найден: {target}")

    if os.name == "nt":
        os.startfile(target)  # type: ignore[attr-defined]
        return
    if sys.platform == "darwin":
        subprocess.Popen(["open", str(target)])
        return

    opener = shutil.which("xdg-open")
    if opener is None:
        raise RuntimeError("Команда xdg-open не найдена")
    subprocess.Popen([opener, str(target)])


def open_in_file_manager(path: Path) -> None:
    target = path.expanduser()
    directory = target if target.is_dir() else target.parent
    directory.mkdir(parents=True, exist_ok=True)

    if os.name == "nt":
        if target.exists() and target.is_file():
            subprocess.Popen(["explorer", "/select,", str(target.resolve())])
        else:
            os.startfile(directory.resolve())  # type: ignore[attr-defined]
        return
    if sys.platform == "darwin":
        if target.exists() and target.is_file():
            subprocess.Popen(["open", "-R", str(target.resolve())])
        else:
            subprocess.Popen(["open", str(directory.resolve())])
        return

    opener = shutil.which("xdg-open")
    if opener is None:
        raise RuntimeError("Команда xdg-open не найдена")
    subprocess.Popen([opener, str(directory.resolve())])
