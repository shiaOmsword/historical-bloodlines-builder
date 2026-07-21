from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any

from historical_bloodlines.presentation.launcher.navigation import (
    NavigationCommand,
    Route,
    Router,
    ScreenFactory,
)


class CommandScreen:
    def __init__(
        self,
        commands: Iterator[NavigationCommand],
        visited: list[Route],
        route: Route,
    ) -> None:
        self._commands = commands
        self._visited = visited
        self._route = route

    def run(self) -> NavigationCommand:
        self._visited.append(self._route)
        return next(self._commands)


def test_router_pushes_and_pops_screen_history() -> None:
    visited: list[Route] = []
    main_commands = iter(
        [
            NavigationCommand.push(Route.CONFIGURATION),
            NavigationCommand.exit(),
        ]
    )
    config_commands = iter([NavigationCommand.pop()])

    factory = ScreenFactory(
        {
            Route.MAIN: lambda params: CommandScreen(
                main_commands,
                visited,
                Route.MAIN,
            ),
            Route.CONFIGURATION: lambda params: CommandScreen(
                config_commands,
                visited,
                Route.CONFIGURATION,
            ),
        }
    )

    Router(factory, Route.MAIN).run()

    assert visited == [Route.MAIN, Route.CONFIGURATION, Route.MAIN]


def test_replace_does_not_leave_form_in_history() -> None:
    visited: list[Route] = []
    commands: dict[Route, Iterator[NavigationCommand]] = {
        Route.MAIN: iter(
            [
                NavigationCommand.push(Route.CUSTOM_BUILD),
                NavigationCommand.exit(),
            ]
        ),
        Route.CUSTOM_BUILD: iter(
            [NavigationCommand.replace(Route.BUILD_RESULT, token="request")]
        ),
        Route.BUILD_RESULT: iter([NavigationCommand.pop()]),
    }

    def builder(route: Route):
        def create(params: Mapping[str, Any]) -> CommandScreen:
            if route is Route.BUILD_RESULT:
                assert params == {"token": "request"}
            return CommandScreen(commands[route], visited, route)

        return create

    factory = ScreenFactory({route: builder(route) for route in commands})

    Router(factory, Route.MAIN).run()

    assert visited == [
        Route.MAIN,
        Route.CUSTOM_BUILD,
        Route.BUILD_RESULT,
        Route.MAIN,
    ]
