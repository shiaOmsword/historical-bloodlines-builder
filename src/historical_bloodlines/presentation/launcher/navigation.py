from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol, TypeAlias


class Route(StrEnum):
    MAIN = "main"
    BUILD_MENU = "build_menu"
    CUSTOM_BUILD = "custom_build"
    BUILD_RESULT = "build_result"
    CONFIGURATION = "configuration"


class NavigationAction(StrEnum):
    PUSH = "push"
    POP = "pop"
    REPLACE = "replace"
    RESET = "reset"
    STAY = "stay"
    EXIT = "exit"


@dataclass(frozen=True, slots=True)
class NavigationCommand:
    action: NavigationAction
    route: Route | None = None
    params: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def push(cls, route: Route, **params: Any) -> NavigationCommand:
        return cls(NavigationAction.PUSH, route, params)

    @classmethod
    def pop(cls) -> NavigationCommand:
        return cls(NavigationAction.POP)

    @classmethod
    def replace(cls, route: Route, **params: Any) -> NavigationCommand:
        return cls(NavigationAction.REPLACE, route, params)

    @classmethod
    def reset(cls, route: Route, **params: Any) -> NavigationCommand:
        return cls(NavigationAction.RESET, route, params)

    @classmethod
    def stay(cls) -> NavigationCommand:
        return cls(NavigationAction.STAY)

    @classmethod
    def exit(cls) -> NavigationCommand:
        return cls(NavigationAction.EXIT)


@dataclass(slots=True)
class RouteEntry:
    route: Route
    params: dict[str, Any] = field(default_factory=dict)


class Screen(Protocol):
    def run(self) -> NavigationCommand:
        """Render one screen and return a navigation intention."""


ScreenBuilder: TypeAlias = Callable[[Mapping[str, Any]], Screen]


class ScreenFactory:
    def __init__(self, builders: Mapping[Route, ScreenBuilder]) -> None:
        self._builders = dict(builders)

    def create(self, entry: RouteEntry) -> Screen:
        try:
            builder = self._builders[entry.route]
        except KeyError as exc:
            raise LookupError(
                f"No screen is registered for route {entry.route!s}"
            ) from exc
        return builder(entry.params)


class Router:
    """Run screens and keep browser-like navigation history in a stack."""

    def __init__(self, factory: ScreenFactory, initial_route: Route) -> None:
        self._factory = factory
        self._stack = [RouteEntry(initial_route)]
        self._running = False

    @property
    def current_entry(self) -> RouteEntry:
        return self._stack[-1]

    @property
    def history(self) -> tuple[RouteEntry, ...]:
        return tuple(self._stack)

    def run(self) -> None:
        self._running = True
        while self._running:
            screen = self._factory.create(self.current_entry)
            command = screen.run()
            self._apply(command)

    def _apply(self, command: NavigationCommand) -> None:
        match command.action:
            case NavigationAction.PUSH:
                self._stack.append(self._entry_from(command))
            case NavigationAction.POP:
                self._pop()
            case NavigationAction.REPLACE:
                self._stack[-1] = self._entry_from(command)
            case NavigationAction.RESET:
                self._stack = [self._entry_from(command)]
            case NavigationAction.STAY:
                pass
            case NavigationAction.EXIT:
                self._running = False

    def _pop(self) -> None:
        if len(self._stack) == 1:
            self._running = False
            return
        self._stack.pop()

    @staticmethod
    def _entry_from(command: NavigationCommand) -> RouteEntry:
        if command.route is None:
            raise ValueError(f"{command.action} requires a target route")
        return RouteEntry(command.route, dict(command.params))
