from dataclasses import dataclass

from historical_bloodlines.domain import ReignPeriod, SourcePersonKey


@dataclass(frozen=True, slots=True)
class RawGenealogyRowDTO:
    row_number: int
    source_sheet: str
    person_name: str
    title_raw: str | None
    reign_start_raw: int | str | None
    reign_end_raw: int | str | None
    children_raw: str | None
    spouses_raw: str | None


@dataclass(frozen=True, slots=True)
class GenealogySheetDTO:
    name: str
    display_title: str
    rows: tuple[RawGenealogyRowDTO, ...]


@dataclass(frozen=True, slots=True)
class PersonReferenceDTO:
    name: str
    order: int | None = None
    raw_value: str | None = None
    qualifier: str | None = None


@dataclass(frozen=True, slots=True)
class ParsedGenealogyRowDTO:
    source_key: SourcePersonKey
    name: str
    dynasty: str
    titles: tuple[str, ...]
    reign_periods: tuple[ReignPeriod, ...]
    children: tuple[PersonReferenceDTO, ...]
    spouses: tuple[PersonReferenceDTO, ...]
