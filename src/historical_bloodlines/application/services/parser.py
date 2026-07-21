from __future__ import annotations

import re

from historical_bloodlines.application.dto import (
    ParsedGenealogyRowDTO,
    PersonReferenceDTO,
    RawGenealogyRowDTO,
)
from historical_bloodlines.domain import ReignPeriod, SourcePersonKey

_LIST_SPLIT_RE = re.compile(r"\s*[;\n]+\s*")
_ORDER_RE = re.compile(r"^\s*(?P<order>\d+)\s*[).:-]\s*(?P<value>.+)$")
_TRAILING_PAREN_RE = re.compile(r"\s*\((?P<qualifier>[^()]*)\)\s*$")
_YEAR_RE = re.compile(r"-?\d{3,4}")


class GenealogyRowParser:
    def parse(self, row: RawGenealogyRowDTO) -> ParsedGenealogyRowDTO:
        return ParsedGenealogyRowDTO(
            source_key=SourcePersonKey(row.source_sheet, row.row_number),
            name=self._normalize_text(row.person_name),
            dynasty=self._normalize_text(row.source_sheet),
            titles=self._parse_titles(row.title_raw),
            reign_periods=self._parse_reign_periods(
                row.reign_start_raw,
                row.reign_end_raw,
            ),
            children=self._parse_people(row.children_raw),
            spouses=self._parse_people(row.spouses_raw),
        )

    @staticmethod
    def _normalize_text(value: str) -> str:
        return " ".join(str(value).split())

    def _parse_titles(self, value: str | None) -> tuple[str, ...]:
        if not value:
            return ()
        return tuple(
            self._normalize_text(item)
            for item in _LIST_SPLIT_RE.split(str(value))
            if item.strip()
        )

    def _parse_reign_periods(
        self,
        starts_raw: int | str | None,
        ends_raw: int | str | None,
    ) -> tuple[ReignPeriod, ...]:
        starts = self._parse_years(starts_raw)
        ends = self._parse_years(ends_raw)
        if not starts or not ends:
            return ()
        if len(starts) != len(ends):
            raise ValueError(
                f"Reign periods mismatch: starts={starts!r}, ends={ends!r}"
            )
        return tuple(ReignPeriod(start, end) for start, end in zip(starts, ends))

    @staticmethod
    def _parse_years(value: int | str | None) -> tuple[int, ...]:
        if value is None or value == "":
            return ()
        if isinstance(value, int):
            return (value,)
        return tuple(int(match.group()) for match in _YEAR_RE.finditer(str(value)))

    def _parse_people(self, value: str | None) -> tuple[PersonReferenceDTO, ...]:
        if not value:
            return ()

        references: list[PersonReferenceDTO] = []
        for chunk in _LIST_SPLIT_RE.split(str(value)):
            raw = self._normalize_text(chunk)
            if not raw:
                continue

            order: int | None = None
            order_match = _ORDER_RE.match(raw)
            raw_name = raw
            if order_match:
                order = int(order_match.group("order"))
                raw_name = self._normalize_text(order_match.group("value"))

            # A comma usually introduces a title, not a part of the personal name.
            name_part = raw_name.split(",", maxsplit=1)[0].strip()
            qualifier: str | None = None
            paren_match = _TRAILING_PAREN_RE.search(name_part)
            if paren_match:
                qualifier = self._normalize_text(paren_match.group("qualifier"))
                base_name = _TRAILING_PAREN_RE.sub("", name_part).strip()
            else:
                base_name = name_part

            if base_name:
                references.append(
                    PersonReferenceDTO(
                        name=base_name,
                        order=order,
                        raw_value=raw,
                        qualifier=qualifier,
                    )
                )
        return tuple(references)
