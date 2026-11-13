from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
import pytest

from historical_bloodlines.application.services import GenealogyAssembler, GenealogyRowParser
from historical_bloodlines.config.render import load_render_config
from historical_bloodlines.infrastructure.excel import ExcelGenealogyReader
from historical_bloodlines.infrastructure.graph import GraphvizGenealogyRenderer
from historical_bloodlines.infrastructure.graph.connector_routing import OrthogonalConnectorRouter


# Production Valois workbook: no generation/order columns. In particular,
# Francis appears before Claude although Claude's father appears first.
ROWS = [
    ("Карл V", "1364–1380", "Карл VI; Людовик I", None),
    ("Людовик I ", "герцог Орлеанский", "Карл I; Жан ", None),
    ("Карл VI", "1380-1422", "Карл VII", None),
    ("Карл VII", "1422-1461", "Людовик XI", None),
    ("Людовик XI ", "1461-1483", "Карл VIII", None),
    ("Карл VIII", "1483–1498", None, None),
    ("Карл I", "герцог Орлеанский", "Людовик XII", None),
    ("Жан", "граф Ангулемский", "Карл", None),
    ("Людовик XII", "1498–1515", "Клод Французская", None),
    ("Карл", "граф Ангулемский", "Франциск I; Маргарита Наваррская", None),
    ("Маргарита Наваррская", None, None, None),
    ("Франциск I", "1515–1547", "Генрих II", "Клод Французская"),
    ("Клод Французская", None, "Генрих II", "Франциск I"),
    ("Генрих II", "1547–1559", "Франциск II; Карл IX; Генрих III; Маргарита де Валуа", None),
    ("Франциск II", "1559–1560", None, None),
    ("Карл IX", "1560–1574", None, None),
    ("Генрих III", "1574–1589", None, None),
    ("Династия Бурбонов", None, "Антуан де Бурбон", None),
    ("Антуан де Бурбон", "король Наваррский, герцог де Вандом", "Генрих IV", None),
    ("Генрих IV", "1589–1610", "Людовик XIII", "Маргарита де Валуа; Мария Медичи"),
    ("Маргарита де Валуа", None, None, "Генрих IV"),
    ("Мария Медичи", None, "Людовик XIII", "Генрих IV"),
    ("Филипп III Габсбург", "король Испанский", "Анна Австрийская", None),
    ("Людовик XIII", "1610–1643", None, "Анна Австрийская"),
    ("Анна Австрийская", None, None, "Людовик XIII"),
    ("Людовик XIV", "1643–1715", None, None),
]


def _genealogy(tmp_path):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Tabelle1"
    sheet.append(["Название", "Француский королевский дом в XIV-XVII веках"])
    sheet.append(["№", "Имя", "Титул", "Начало правления", "Конец правления", "Дети", "Брак"])
    for index, (name, title, children, spouses) in enumerate(ROWS, 1):
        sheet.append([index, name, title, None, None, children, spouses])
    path = tmp_path / "valois.xlsx"
    workbook.save(path)
    source = ExcelGenealogyReader().read(path)[0]
    return GenealogyAssembler().assemble(GenealogyRowParser().parse(row) for row in source.rows)


@pytest.mark.parametrize("profile", ["default", "plus2", "plus3", "publisher-review"])
def test_automatic_valois_branches_render_without_crossings(tmp_path, monkeypatch, profile):
    # A wrong orientation must fail promptly, rather than spend minutes trying
    # thousands of routes for an impossible fixed ordering.
    monkeypatch.setattr(OrthogonalConnectorRouter, "MAX_GROUP_SEARCH_STATES", 100)
    genealogy = _genealogy(tmp_path)
    assert len(genealogy.persons) == 26
    assert not genealogy.warnings
    assert all(person.layout_hint.generation is None and person.layout_hint.order is None
               for person in genealogy.persons.values())

    renderer = GraphvizGenealogyRenderer(load_render_config(Path(f"config/render.{profile}.yaml")))
    output = tmp_path / "valois.svg"
    renderer.render(genealogy, output, title="Валуа")
    geometry = renderer.last_geometry
    assert geometry is not None
    assert geometry["issues"] == ()
    people = {person.name: person.id for person in genealogy.persons.values()}
    positions = geometry["positions"]
    assert positions[people["Людовик XII"]].center_x < positions[people["Карл"]].center_x
    assert positions[people["Клод Французская"]].center_x < positions[people["Франциск I"]].center_x

    rendered_relations = {
        (frozenset(route.family.parent_ids), child)
        for route in geometry["routes"] for child in route.family.child_ids
    }
    assert rendered_relations == {
        (relation.parent_ids, relation.child_id)
        for relation in genealogy.family_child_relations
    }
    assert (frozenset((people["Филипп III Габсбург"],)), people["Анна Австрийская"]) in rendered_relations
    assert (frozenset((people["Генрих IV"], people["Мария Медичи"])), people["Людовик XIII"]) in rendered_relations
    assert output.stat().st_size > 100


@pytest.mark.parametrize("parent_orders", [(None, None), (10, None), (10, 20)])
def test_automatic_spouse_orientation_preserves_explicit_hints(tmp_path, parent_orders):
    from historical_bloodlines.domain import PersonLayoutHint

    genealogy = _genealogy(tmp_path)
    people = {person.name: person for person in genealogy.persons.values()}
    for name, order in zip(("Людовик XII", "Карл"), parent_orders):
        people[name].layout_hint = PersonLayoutHint(order=order)
    layout = GraphvizGenealogyRenderer()._layout
    spouses = {people["Франциск I"].id, people["Клод Французская"].id}
    ordered = layout._order_partner_component(genealogy, spouses)
    # Parent source order is used only when neither branch has manual priority.
    expected = ("Клод Французская", "Франциск I") if parent_orders == (None, None) else ("Франциск I", "Клод Французская")
    assert tuple(genealogy.persons[person_id].name for person_id in ordered) == expected

    people["Франциск I"].layout_hint = PersonLayoutHint(order=10)
    people["Клод Французская"].layout_hint = PersonLayoutHint(order=20)
    ordered = layout._order_partner_component(genealogy, spouses)
    assert ordered == (people["Франциск I"].id, people["Клод Французская"].id)
