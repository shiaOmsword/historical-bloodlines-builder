from __future__ import annotations

import re

from historical_bloodlines.application.dto import (
    ParsedGenealogyRowDTO,
    PersonReferenceDTO,
    RawGenealogyRowDTO,
)
from historical_bloodlines.domain import ReignPeriod, SourcePersonKey, normalize_title

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
            layout_generation=self._parse_positive_integer(
                row.generation_raw,
                field_name="Поколение",
                row=row,
            ),
            layout_order=self._parse_positive_integer(
                row.generation_order_raw,
                field_name="Порядок в поколении",
                row=row,
            ),
        )

    @staticmethod
    def _normalize_text(value: str) -> str:
        return " ".join(str(value).split())

    def _parse_titles(self, value: str | None) -> tuple[str, ...]:
        if not value:
            return ()
        return tuple(
            normalize_title(item)
            for item in _LIST_SPLIT_RE.split(str(value))
            if item.strip()
        )

    def _parse_reign_periods(
        self,
        starts_raw: int | str | None,
        ends_raw: int | str | None,
    ) -> tuple[ReignPeriod, ...]:
        starts = self._parse_year_slots(starts_raw)
        ends = self._parse_year_slots(ends_raw)
        if not starts:
            if any(end is not None for end in ends):
                raise ValueError(
                    f"Reign periods mismatch: starts={starts!r}, ends={ends!r}"
                )
            return ()

        if len(ends) > len(starts) and any(
            end is not None for end in ends[len(starts) :]
        ):
            raise ValueError(
                f"Reign periods mismatch: starts={starts!r}, ends={ends!r}"
            )

        padded_ends = (*ends[: len(starts)], *(None for _ in range(len(starts) - len(ends))))
        periods: list[ReignPeriod] = []
        for index, start in enumerate(starts):
            end = padded_ends[index]
            if start is None:
                if end is not None:
                    raise ValueError(
                        f"Reign periods mismatch: starts={starts!r}, ends={ends!r}"
                    )
                continue
            periods.append(ReignPeriod(start, end))
        return tuple(periods)

    @staticmethod
    def _parse_year_slots(
        value: int | float | str | None,
    ) -> tuple[int | None, ...]:
        if value is None or value == "":
            return ()
        if isinstance(value, int):
            return (value,)
        if isinstance(value, float) and value.is_integer():
            return (int(value),)

        text = str(value)
        if ";" in text or "\n" in text:
            slots: list[int | None] = []
            for chunk in re.split(r"[;\n]", text):
                match = _YEAR_RE.search(chunk)
                slots.append(int(match.group()) if match else None)
            while slots and slots[-1] is None:
                # Preserve one trailing empty slot: it denotes an open-ended
                # final reign, e.g. starts ``936; 962`` and ends ``973;``.
                if len(slots) < 2 or slots[-2] is None:
                    slots.pop()
                else:
                    break
            return tuple(slots)

        return tuple(int(match.group()) for match in _YEAR_RE.finditer(text))

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

    @staticmethod
    def _parse_positive_integer(
        value: int | float | str | None,
        *,
        field_name: str,
        row: RawGenealogyRowDTO,
    ) -> int | None:
        if value is None or value == "":
            return None

        parsed: int | None = None
        if isinstance(value, bool):
            parsed = None
        elif isinstance(value, int):
            parsed = value
        elif isinstance(value, float):
            if value.is_integer():
                parsed = int(value)
        else:
            normalized = str(value).strip()
            if normalized.isdigit():
                parsed = int(normalized)

        if parsed is None or parsed < 1:
            raise ValueError(
                f"{row.source_sheet}:{row.row_number}: {field_name} must be "
                f"a positive integer, got {value!r}"
            )
        return parsed
