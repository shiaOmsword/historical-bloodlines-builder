from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from historical_bloodlines.application.services.build_genealogy import (
    BuildGenealogyUseCase,
    PageFormat,
)
from historical_bloodlines.config.settings import Settings
from historical_bloodlines.presentation.file_dialogs import (
    FileDialogError,
    select_excel_file,
    select_output_file,
)
from historical_bloodlines.presentation.launcher.components import (
    graphviz_status,
    launcher_width,
    open_in_file_manager,
    open_path,
    render_header,
    render_menu,
    render_paths,
    wait_for_enter,
)
from historical_bloodlines.presentation.launcher.navigation import (
    NavigationCommand,
    Route,
)


@dataclass(frozen=True, slots=True)
class BuildOptions:
    input_path: Path
    output_path: Path
    page_format: PageFormat = PageFormat.A5


class MainScreen:
    def __init__(self, console: Console, settings: Settings) -> None:
        self._console = console
        self._settings = settings

    def run(self) -> NavigationCommand:
        render_header(
            self._console,
            "Rich launcher",
            subtitle="Интерактивная оболочка над bloodlines build",
        )
        render_menu(
            self._console,
            (
                ("1", "Собрать родословную", "Быстрый или настраиваемый запуск"),
                ("2", "Конфигурация", "Пути по умолчанию и Graphviz"),
                ("3", "Открыть результаты", "Открыть папку в Документах"),
                ("0", "Выход", "Завершить launcher"),
            ),
        )

        choice = Prompt.ask(
            "[bold cyan]Выберите действие[/bold cyan]",
            choices=["1", "2", "3", "0"],
            console=self._console,
        )

        match choice:
            case "1":
                return NavigationCommand.push(Route.BUILD_MENU)
            case "2":
                return NavigationCommand.push(Route.CONFIGURATION)
            case "3":
                self._open_output_directory()
                return NavigationCommand.stay()
            case _:
                return NavigationCommand.exit()

    def _open_output_directory(self) -> None:
        try:
            open_in_file_manager(self._settings.output_file)
        except Exception as exc:
            self._console.print(
                Panel(str(exc), title="Не удалось открыть папку", border_style="red")
            )
            wait_for_enter(self._console)


class BuildMenuScreen:
    def __init__(self, console: Console, settings: Settings) -> None:
        self._console = console
        self._settings = settings

    def run(self) -> NavigationCommand:
        render_header(self._console, "Сборка родословной")
        render_menu(
            self._console,
            (
                ("1", "Быстрая сборка", "Использовать пути и A5 по умолчанию"),
                ("2", "Настроить сборку", "Выбрать Excel, формат и файл результата"),
                ("0", "Назад", "Вернуться в главное меню"),
            ),
        )

        choice = Prompt.ask(
            "[bold cyan]Режим[/bold cyan]",
            choices=["1", "2", "0"],
            console=self._console,
        )

        match choice:
            case "1":
                options = BuildOptions(
                    input_path=self._settings.input_file,
                    output_path=self._settings.output_file,
                    page_format=PageFormat.A5,
                )
                return NavigationCommand.push(
                    Route.BUILD_RESULT,
                    options=options,
                )
            case "2":
                return NavigationCommand.push(Route.CUSTOM_BUILD)
            case _:
                return NavigationCommand.pop()


class CustomBuildScreen:
    def __init__(self, console: Console, settings: Settings) -> None:
        self._console = console
        self._settings = settings

    def run(self) -> NavigationCommand:
        render_header(
            self._console,
            "Настройка сборки",
            subtitle="Файлы выбираются через стандартные окна Windows",
        )

        if not Confirm.ask(
            "Выбрать Excel-файл?",
            default=True,
            console=self._console,
        ):
            return NavigationCommand.pop()

        try:
            input_path = select_excel_file(self._settings.input_file)
        except FileDialogError as exc:
            self._show_dialog_error(exc)
            return NavigationCommand.pop()
        if input_path is None:
            return NavigationCommand.pop()

        output_format = Prompt.ask(
            "Формат результата",
            choices=["pdf", "svg", "png"],
            default=self._default_output_format(),
            console=self._console,
        )

        default_output = self._settings.output_file.with_suffix(f".{output_format}")
        try:
            output_path = select_output_file(
                default_output,
                output_format=output_format,
            )
        except FileDialogError as exc:
            self._show_dialog_error(exc)
            return NavigationCommand.pop()
        if output_path is None:
            return NavigationCommand.pop()

        page_format = PageFormat.A5
        if output_format == "pdf":
            page_format = PageFormat(
                Prompt.ask(
                    "Формат страницы",
                    choices=[PageFormat.A5.value, PageFormat.A4.value],
                    default=PageFormat.A5.value,
                    console=self._console,
                )
            )

        options = BuildOptions(
            input_path=input_path,
            output_path=output_path,
            page_format=page_format,
        )
        render_paths(
            self._console,
            input_path=options.input_path,
            output_path=options.output_path,
            page_format=options.page_format.value,
        )

        if not Confirm.ask(
            "Запустить сборку?",
            default=True,
            console=self._console,
        ):
            return NavigationCommand.pop()

        # The setup form should not remain in history. Back from the result
        # returns to the build menu instead of reopening all prompts.
        return NavigationCommand.replace(
            Route.BUILD_RESULT,
            options=options,
        )

    def _default_output_format(self) -> str:
        suffix = self._settings.output_file.suffix.casefold().removeprefix(".")
        return suffix if suffix in {"pdf", "svg", "png"} else "pdf"

    def _show_dialog_error(self, error: Exception) -> None:
        self._console.print(
            Panel(
                str(error),
                title="Не удалось открыть окно выбора файла",
                border_style="red",
            )
        )
        wait_for_enter(self._console)


class BuildResultScreen:
    def __init__(
        self,
        console: Console,
        use_case: BuildGenealogyUseCase,
        options: BuildOptions,
    ) -> None:
        self._console = console
        self._use_case = use_case
        self._options = options

    def run(self) -> NavigationCommand:
        render_header(self._console, "Выполнение сборки")
        render_paths(
            self._console,
            input_path=self._options.input_path,
            output_path=self._options.output_path,
            page_format=self._options.page_format.value,
        )

        if not self._options.input_path.exists():
            self._console.print(
                Panel(
                    f"Excel-файл не найден:\n{self._options.input_path}",
                    title="Ошибка",
                    border_style="red",
                )
            )
            wait_for_enter(self._console)
            return NavigationCommand.pop()

        try:
            with self._console.status(
                "[bold cyan]Читаю Excel и строю графы...[/bold cyan]",
                spinner="dots",
            ):
                result = self._use_case.execute(
                    self._options.input_path,
                    self._options.output_path,
                    page_format=self._options.page_format,
                )
        except Exception as exc:
            self._console.print(
                Panel(
                    str(exc),
                    title="Сборка завершилась ошибкой",
                    border_style="red",
                )
            )
            wait_for_enter(self._console)
            return NavigationCommand.pop()

        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column(style="bold cyan", width=16)
        table.add_column()
        table.add_row("Создано", str(result.output_path))
        table.add_row("Предупреждения", str(len(result.warnings)))

        self._console.print(
            Panel(
                table,
                title="Готово",
                border_style="green",
                width=launcher_width(self._console),
            )
        )
        if result.warnings:
            warning_text = "\n".join(f"• {warning}" for warning in result.warnings)
            self._console.print(
                Panel(
                    warning_text,
                    title="Предупреждения",
                    border_style="yellow",
                    width=launcher_width(self._console),
                )
            )

        return self._result_actions(result.output_path)

    def _result_actions(self, result_path: Path) -> NavigationCommand:
        render_menu(
            self._console,
            (
                ("1", "Открыть результат", "Открыть созданный файл или каталог"),
                ("2", "Показать в папке", "Открыть Проводник рядом с результатом"),
                ("0", "Назад", "Вернуться к выбору режима"),
            ),
        )
        choice = Prompt.ask(
            "[bold cyan]Что сделать дальше?[/bold cyan]",
            choices=["1", "2", "0"],
            default="1",
            console=self._console,
        )

        try:
            if choice == "1":
                open_path(result_path)
            elif choice == "2":
                open_in_file_manager(result_path)
        except Exception as exc:
            self._console.print(
                Panel(str(exc), title="Не удалось открыть результат", border_style="red")
            )
            wait_for_enter(self._console)

        return NavigationCommand.pop()


class ConfigurationScreen:
    def __init__(self, console: Console, settings: Settings) -> None:
        self._console = console
        self._settings = settings

    def run(self) -> NavigationCommand:
        render_header(self._console, "Конфигурация")
        graphviz_ready, graphviz_details = graphviz_status()

        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column(style="bold cyan", width=22)
        table.add_column()
        table.add_row("Excel по умолчанию", str(self._settings.input_file))
        table.add_row(
            "Excel существует",
            "[green]да[/green]" if self._settings.input_file.exists() else "[red]нет[/red]",
        )
        table.add_row("Результат по умолчанию", str(self._settings.output_file))
        table.add_row("Страница PDF", "A5 landscape")
        table.add_row(
            "Graphviz",
            "[green]готов[/green]" if graphviz_ready else "[red]не готов[/red]",
        )
        table.add_row("Команды Graphviz", graphviz_details)

        self._console.print(
            Panel(
                table,
                border_style="bright_black",
                width=launcher_width(self._console),
            )
        )
        wait_for_enter(self._console)
        return NavigationCommand.pop()


def require_build_options(params: Mapping[str, Any]) -> BuildOptions:
    options = params.get("options")
    if not isinstance(options, BuildOptions):
        raise TypeError("Route BUILD_RESULT requires BuildOptions")
    return options
