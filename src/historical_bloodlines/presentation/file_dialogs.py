from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


class FileDialogError(RuntimeError):
    """Raised when the native file dialog cannot be initialized."""


@contextmanager
def _hidden_tk_root() -> Iterator[object]:
    try:
        from tkinter import Tk, TclError
    except ImportError as exc:  # pragma: no cover - standard on Windows Python
        raise FileDialogError("Tkinter недоступен в этой сборке Python.") from exc

    root = None
    try:
        root = Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        root.update_idletasks()
        yield root
    except TclError as exc:
        raise FileDialogError(
            "Не удалось открыть системное окно выбора файла."
        ) from exc
    finally:
        if root is not None:
            root.destroy()


def select_excel_file(initial_path: Path) -> Path | None:
    filedialog = _load_filedialog()

    initial_directory = _existing_directory(initial_path.parent)
    with _hidden_tk_root() as root:
        selected = filedialog.askopenfilename(
            parent=root,
            title="Выберите Excel-файл с родословной",
            initialdir=str(initial_directory),
            initialfile=initial_path.name,
            filetypes=(
                ("Excel workbook", "*.xlsx"),
                ("Все файлы", "*.*"),
            ),
        )
    return Path(selected) if selected else None


def select_output_file(
    initial_path: Path,
    *,
    output_format: str,
) -> Path | None:
    normalized_format = output_format.casefold().removeprefix(".")
    if normalized_format not in {"pdf", "svg", "png"}:
        raise ValueError(f"Unsupported output format: {output_format}")

    filedialog = _load_filedialog()

    target = initial_path.with_suffix(f".{normalized_format}")
    initial_directory = _existing_directory(target.parent)
    label = normalized_format.upper()
    with _hidden_tk_root() as root:
        selected = filedialog.asksaveasfilename(
            parent=root,
            title="Сохранить родословную",
            initialdir=str(initial_directory),
            initialfile=target.name,
            defaultextension=f".{normalized_format}",
            filetypes=((label, f"*.{normalized_format}"),),
        )
    if not selected:
        return None
    return Path(selected).with_suffix(f".{normalized_format}")


def _existing_directory(path: Path) -> Path:
    candidate = path.expanduser()
    while not candidate.exists() and candidate != candidate.parent:
        candidate = candidate.parent
    return candidate if candidate.is_dir() else Path.home()


def _load_filedialog():
    try:
        from tkinter import filedialog
    except ImportError as exc:  # pragma: no cover - standard on Windows Python
        raise FileDialogError("Tkinter недоступен в этой сборке Python.") from exc
    return filedialog
