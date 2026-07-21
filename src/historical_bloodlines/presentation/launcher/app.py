from __future__ import annotations

from rich.console import Console
from rich.theme import Theme

from historical_bloodlines.application.services.build_genealogy import (
    BuildGenealogyUseCase,
)
from historical_bloodlines.config import get_settings
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


LAUNCHER_THEME = Theme(
    {
        "info": "cyan",
        "success": "bold green",
        "warning": "yellow",
        "error": "bold red",
    }
)


def build_router(console: Console | None = None) -> Router:
    launcher_console = console or Console(theme=LAUNCHER_THEME)
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


def main() -> None:
    console = Console(theme=LAUNCHER_THEME)
    router = build_router(console)
    try:
        router.run()
    except (KeyboardInterrupt, EOFError):
        console.print("\n[yellow]Launcher остановлен пользователем.[/yellow]")
    else:
        console.print("\n[dim]До встречи.[/dim]")
