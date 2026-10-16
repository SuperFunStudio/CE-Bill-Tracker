"""Pure-function guards for the jurisdiction tree seed (app/geo/jurisdictions.py) and bloc expansion.

Regression coverage for 2026-10-16: nine EU members (BE BG HR CY GR HU MT PT RO) had no node, so
expand_place_ids silently dropped them from every "European Union" question. No DB needed — the tree
is built from the seed data the backfill writes.
"""
from collections import namedtuple

from app.api.research_facets import _BLOC_MEMBERS, expand_place_ids
from app.geo.jurisdictions import US_MUNICIPALITIES, jurisdiction_code, seed_nodes

Node = namedtuple("Node", "id name path aliases code level")


def _tree() -> list[Node]:
    return [Node(i, n["name"], n["path"], [a.lower() for a in n["aliases"]], n["code"], n["level"])
            for i, n in enumerate(seed_nodes())]


def test_every_eu_member_has_a_node():
    codes = {n.code for n in _tree()}
    assert _BLOC_MEMBERS["EU"] - codes == set()


def test_eu_expands_to_all_27_members():
    nodes = _tree()
    eu = next(n for n in nodes if n.code == "EU")
    ids, expanded = expand_place_ids(nodes, {eu.path})
    by_id = {n.id: n for n in nodes}
    assert expanded == ["European Union"]
    assert _BLOC_MEMBERS["EU"] <= {by_id[i].code for i in ids}


def test_members_stay_country_nodes_not_children_of_the_bloc():
    # research.py reads the 2nd path segment as "the country"; nesting members under EU would collapse
    # all 27 into "eu" in every country rollup.
    fr = next(n for n in _tree() if n.code == "FR")
    assert fr.path == "world.fr" and fr.level == "country"


def test_new_members_resolve_by_name_only():
    # Bare codes collide: MT is Montana's alias, HR a House Resolution prefix, "be" a word.
    for n in _tree():
        if n.code in {"BE", "BG", "HR", "CY", "GR", "HU", "MT", "PT", "RO"}:
            assert all(len(a) >= 4 for a in n.aliases), (n.code, n.aliases)


def test_city_nodes_hang_under_their_state():
    nodes = {n.code: n for n in _tree()}
    for sub in US_MUNICIPALITIES:
        code = jurisdiction_code("US", sub)  # "OR-PORTLAND" -> "US-OR-PORTLAND"
        city, state = nodes[code], nodes[f"US-{sub.split('-', 1)[0]}"]
        assert city.level == "municipality"
        assert city.path.startswith(state.path + ".")
