from __future__ import annotations

import sys
from collections.abc import Sequence

from rich.console import Console
from rich.panel import Panel
from rich.theme import Theme

from historical_bloodlines.application.services.build_genealogy import (
    BuildGenealogyUseCase,
)
from historical_bloodlines.config import (
    GraphvizRuntimeError,
    get_settings,
    prepare_bundled_graphviz,
)
from historical_bloodlines.presentation.launcher.navigation import (
    Route,
    Router,
    ScreenFactory,
)
from historical_bloodlines.presentation.launcher.screens import (
    BuildMenuScreen,
    BuildResultScreen,
    ConfigurationScreen,
    CustomBuildScreen,
    MainScreen,
    require_build_options,
)
from historical_bloodlines.presentation.launcher.self_test import run_self_test
from historical_bloodlines.presentation.launcher.terminal import prepare_terminal


LAUNCHER_THEME = Theme(
    {
        "info": "cyan",
        "success": "bold green",
        "warning": "yellow",
        "error": "bold red",
    }
)


def create_console() -> Console:
    terminal = prepare_terminal()
    return Console(
        theme=LAUNCHER_THEME,
        safe_box=True,
        emoji=False,
        force_terminal=None if terminal.interactive else False,
        legacy_windows=(
            not terminal.virtual_terminal_enabled
            if sys.platform == "win32" and terminal.interactive
            else False
        ),
    )


def build_router(console: Console | None = None) -> Router:
    launcher_console = console or create_console()
    settings = get_settings()
    build_genealogy = BuildGenealogyUseCase()

    factory = ScreenFactory(
        {
            Route.MAIN: lambda params: MainScreen(launcher_console, settings),
            Route.BUILD_MENU: lambda params: BuildMenuScreen(
                launcher_console,
                settings,
            ),
            Route.CUSTOM_BUILD: lambda params: CustomBuildScreen(
                launcher_console,
                settings,
            ),
            Route.BUILD_RESULT: lambda params: BuildResultScreen(
                launcher_console,
                build_genealogy,
                require_build_options(params),
            ),
            Route.CONFIGURATION: lambda params: ConfigurationScreen(
                launcher_console,
                settings,
            ),
        }
    )
    return Router(factory=factory, initial_route=Route.MAIN)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = tuple(sys.argv[1:] if argv is None else argv)
    console = create_console()

    try:
        prepare_bundled_graphviz()
    except GraphvizRuntimeError as exc:
        console.print(
            Panel(
                str(exc),
                title="Graphviz недоступен",
                border_style="red",
            )
        )
        return 1

    if "--self-test" in arguments:
        return run_self_test(console)

    unknown = [argument for argument in arguments if argument != "--self-test"]
    if unknown:
        console.print(
            Panel(
                f"Неизвестные аргументы: {' '.join(unknown)}",
                title="Ошибка запуска",
                border_style="red",
            )
        )
        return 2

    router = build_router(console)
    try:
        router.run()
    except (KeyboardInterrupt, EOFError):
        console.print("\n[yellow]Launcher остановлен пользователем.[/yellow]")
    else:
        console.print("\n[dim]До встречи.[/dim]")
    return 0
