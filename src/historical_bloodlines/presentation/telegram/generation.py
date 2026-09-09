from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from historical_bloodlines.application.services.build_genealogy import (
    BuildGenealogyUseCase,
)


@dataclass(frozen=True, slots=True)
class GenerationBundle:
    pdf_path: Path
    publisher_zip_path: Path
    warnings: tuple[str, ...]
    genealogy_count: int


class TelegramGenerationService:
    """Generate Telegram-friendly artifacts from one uploaded workbook."""

    def __init__(self, builder: BuildGenealogyUseCase | None = None) -> None:
        self._builder = builder

    def build(self, input_path: Path, output_directory: Path) -> GenerationBundle:
        # Reload once per workbook, never between EPS/PNG and PDF. Editing the
        # mounted YAML affects the next request without rebuilding the image.
        builder = self._builder or BuildGenealogyUseCase()
        output_directory.mkdir(parents=True, exist_ok=True)

        with TemporaryDirectory(prefix="bloodlines_tg_", dir=output_directory) as raw_tmp:
            temporary_directory = Path(raw_tmp)
            eps_target = temporary_directory / "publisher.eps"
            pdf_target = temporary_directory / "genealogy.pdf"

            eps_result = builder.execute(input_path, eps_target)
            pdf_result = builder.execute(input_path, pdf_target)

            publisher_directory = eps_result.output_path
            eps_files = sorted(publisher_directory.glob("*.eps"))
            preview_files = sorted(publisher_directory.glob("*.preview.png"))
            if not eps_files:
                raise RuntimeError("Publisher package contains no EPS files")

            final_pdf = output_directory / "genealogy.pdf"
            shutil.copy2(pdf_result.output_path, final_pdf)

            staging_directory = temporary_directory / "genealogy_publisher"
            staging_directory.mkdir(parents=True, exist_ok=True)
            for file_path in (*eps_files, *preview_files):
                shutil.copy2(file_path, staging_directory / file_path.name)

            (staging_directory / "render-settings.yaml").write_text(
                builder.render_config.to_yaml(), encoding="utf-8"
            )

            zip_base = output_directory / "genealogy_publisher"
            zip_path = Path(
                shutil.make_archive(
                    str(zip_base),
                    "zip",
                    root_dir=temporary_directory,
                    base_dir=staging_directory.name,
                )
            )

            warnings = tuple(dict.fromkeys((*eps_result.warnings, *pdf_result.warnings)))
            return GenerationBundle(
                pdf_path=final_pdf,
                publisher_zip_path=zip_path,
                warnings=warnings,
                genealogy_count=len(eps_files),
            )
