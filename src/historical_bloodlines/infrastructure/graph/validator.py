from __future__ import annotations

import networkx as nx

from historical_bloodlines.domain import Genealogy


class NetworkXGenealogyValidator:
    """Validate genealogy invariants that are naturally expressed as graphs."""

    def validate(self, genealogy: Genealogy) -> None:
        graph = nx.DiGraph()
        graph.add_nodes_from(genealogy.persons)
        graph.add_edges_from(
            (relation.parent_id, relation.child_id)
            for relation in genealogy.parent_child_relations
        )

        if nx.is_directed_acyclic_graph(graph):
            return

        cycle = nx.find_cycle(graph)
        readable_cycle = [
            (
                genealogy.persons[parent_id].name,
                genealogy.persons[child_id].name,
            )
            for parent_id, child_id in cycle
        ]
        raise ValueError(
            f"Parent-child graph contains a cycle: {readable_cycle!r}"
        )
