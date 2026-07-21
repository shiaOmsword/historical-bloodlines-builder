from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from historical_bloodlines.config.paths import default_data_directory


@dataclass(frozen=True, slots=True)
class Settings:
    input_file: Path
    output_file: Path


@lru_cache
def get_settings() -> Settings:
    data_dir = Path(
        os.getenv("BLOODLINES_DATA_DIR", str(default_data_directory()))
    ).expanduser()
    input_directory = data_dir / "input"
    output_directory = data_dir / "output"
    input_directory.mkdir(parents=True, exist_ok=True)
    output_directory.mkdir(parents=True, exist_ok=True)

    return Settings(
        input_file=Path(
            os.getenv(
                "BLOODLINES_INPUT_FILE",
                str(input_directory / "input.xlsx"),
            )
        ).expanduser(),
        output_file=Path(
            os.getenv(
                "BLOODLINES_OUTPUT_FILE",
                str(output_directory / "genealogy.pdf"),
            )
        ).expanduser(),
    )
