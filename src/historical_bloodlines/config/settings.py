from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[3]


@dataclass(frozen=True, slots=True)
class Settings:
    input_file: Path
    output_file: Path


@lru_cache
def get_settings() -> Settings:
    data_dir = Path(os.getenv("BLOODLINES_DATA_DIR", BASE_DIR / "data"))
    return Settings(
        input_file=Path(
            os.getenv(
                "BLOODLINES_INPUT_FILE",
                data_dir / "input" / "input.xlsx",
            )
        ),
        output_file=Path(
            os.getenv(
                "BLOODLINES_OUTPUT_FILE",
                data_dir / "output" / "genealogy.pdf",
            )
        ),
    )
