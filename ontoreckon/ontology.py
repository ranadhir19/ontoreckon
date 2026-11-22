"""Ontology loading (JSON profile + Turtle subset) and pre-flight.

Two input formats describe the same profile:

1. **JSON profile** — ontoreckon's own format::

       {
         "name": "org",
         "classes": [{"name": "Person", "parents": ["Agent"]}],
         "properties": [{"name": "worksFor", "domain": "Person",
                         "range": "Organization", "max_cardinality": 1}],
         "disjoint": [["Person", "Organization"]]
       }

   ``domain``, ``range`` and ``max_cardinality`` are optional per
   property; a property with no domain/range is declared but
   unconstrained on that side.

2. **Turtle subset** — one declaration per line, each an
   ``<s> <p> <o> .`` triple whose predicate is identified by local
   name. Recognised predicates:

   - ``type`` with object local name ``Class``: declares a class;
     with ``ObjectProperty`` / ``Property``: declares a property.
   - ``subClassOf``: subject class, object parent class.
   - ``domain`` / ``range``: subject property, object class.
   - ``disjointWith``: subject and object classes (symmetric).
   - ``maxCardinality``: subject property, object an integer literal
     (``"1"``). This is ontoreckon's documented profile extension: OWL
     expresses cardinality through restriction blank nodes, which the
     subset deliberately flattens to a direct declaration.

   Any other predicate in an ontology file is recorded as an
   unsupported declaration (``PARSE_UNSUPPORTED``) — never silently
   dropped, and the affected construct plays no part in any verdict.
"""

from __future__ import annotations

import json
import re

from .model import Ontology, Property, local_name

_LINE = re.compile(r"^<([^>]*)>\s+<([^>]*)>\s+(?:<([^>]*)>|\"([^\"]*)\")\s*\.\s*$")

_RECOGNISED = {"type", "subClassOf", "domain", "range", "disjointWith", "maxCardinality"}


def _parse_triple_lines(text: str):
    """Yield (subject, predicate, object, object_is_literal) per line.

    Returns (triples, unsupported) where unsupported is a list of
    {"line": n, "text": ...} for non-blank, non-comment lines outside
    the subset grammar.
    """
    triples, unsupported = [], []
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = _LINE.match(line)
        if not m:
            unsupported.append({"line": lineno, "text": raw, "code": "PARSE_UNSUPPORTED"})
            continue
        subj, pred, obj_iri, obj_lit = m.groups()
        triples.append(
            (local_name(subj), local_name(pred), local_name(obj_iri) if obj_iri is not None else obj_lit,
             obj_iri is None)
        )
    return triples, unsupported


def load_ontology_json(text: str, source: str | None = None) -> Ontology:
    data = json.loads(text)
    onto = Ontology(name=data.get("name", "unnamed"), source=source)
    for entry in data.get("classes", []):
        onto.classes[entry["name"]] = set(entry.get("parents", []))
    for entry in data.get("properties", []):
        prop = Property(
            name=entry["name"],
            domain=entry.get("domain"),
            range=entry.get("range"),
            max_cardinality=entry.get("max_cardinality"),
        )
        onto.properties[prop.name] = prop
    for pair in data.get("disjoint", []):
        a, b = pair
        onto.disjoint.append((a, b))
    return onto


def load_ontology_turtle(text: str, source: str | None = None):
    """Parse the Turtle subset. Returns (Ontology, unsupported list)."""
    onto = Ontology(source=source)
    triples, unsupported = _parse_triple_lines(text)
    declared_classes: set[str] = set()
    for subj, pred, obj, is_lit in triples:
        if pred not in _RECOGNISED:
            unsupported.append({"subject": subj, "predicate": pred, "object": obj,
                                "code": "PARSE_UNSUPPORTED"})
            continue
        if pred == "type" and obj == "Class":
            declared_classes.add(subj)
            onto.classes.setdefault(subj, set())
        elif pred == "type" and obj in ("ObjectProperty", "Property", "DatatypeProperty"):
            onto.properties.setdefault(subj, Property(name=subj))
        elif pred == "subClassOf":
            onto.classes.setdefault(subj, set()).add(obj)
            onto.classes.setdefault(obj, set())
        elif pred == "domain":
            onto.properties.setdefault(subj, Property(name=subj)).domain = obj
        elif pred == "range":
            onto.properties.setdefault(subj, Property(name=subj)).range = obj
        elif pred == "disjointWith":
            onto.classes.setdefault(subj, set())
            onto.classes.setdefault(obj, set())
            onto.disjoint.append((subj, obj))
        elif pred == "maxCardinality":
            try:
                value = int(obj)
            except (TypeError, ValueError):
                unsupported.append({"subject": subj, "predicate": pred, "object": obj,
                                    "code": "PARSE_UNSUPPORTED"})
                continue
            onto.properties.setdefault(subj, Property(name=subj)).max_cardinality = value
    return onto, unsupported


def load_ontology(path: str):
    """Load by extension: .json -> JSON profile, .ttl -> Turtle subset.

    Returns (Ontology, unsupported list).
    """
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    if path.endswith(".json"):
        return load_ontology_json(text, source=path), []
    if path.endswith(".ttl"):
        return load_ontology_turtle(text, source=path)
    raise ValueError(f"unsupported ontology format (want .json or .ttl): {path}")


# ---------------------------------------------------------------------
# Pre-flight: is the ontology itself fit to stamp against?
# ---------------------------------------------------------------------

def _find_cycles(onto: Ontology) -> list[list[str]]:
    """Subclass cycles, as lists of class names (DFS back-edge cycles)."""
    cycles: list[list[str]] = []
    WHITE, GREY, BLACK = 0, 1, 2
    colour = {c: WHITE for c in onto.classes}
    path: list[str] = []

    def visit(node: str) -> None:
        colour[node] = GREY
        path.append(node)
        for parent in sorted(onto.classes.get(node, ())):
            if parent not in colour:
                continue
            if colour[parent] == GREY:
                cycles.append(path[path.index(parent):] + [parent])
            elif colour[parent] == WHITE:
                visit(parent)
        path.pop()
        colour[node] = BLACK

    for cls in sorted(onto.classes):
        if colour[cls] == WHITE:
            visit(cls)
    return cycles


def preflight(onto: Ontology) -> dict:
    """Consistency screen over the profile fragment.

    Findings (any finding makes the verdict ONTOLOGY_INCONSISTENT):

    - UNSATISFIABLE_CLASS — a class whose self-and-ancestors set
      contains both members of a declared disjoint pair: nothing can
      be an instance of it under the profile.
    - DISJOINT_SELF — a class declared disjoint with itself (or with
      one of its own ancestors/descendants via the pair list).
    - SUBCLASS_CYCLE — a cycle in the subclass declarations.
    - DANGLING_REFERENCE — a domain, range, disjoint member or parent
      naming a class the profile does not declare. Under the
      closed-world reading the profile must be self-contained: a
      dangling reference makes the affected checks undecidable.
    """
    findings: list[dict] = []

    for cls in sorted(onto.classes):
        closure = onto.self_and_ancestors(cls)
        for a, b in onto.disjoint_pairs_among(closure):
            findings.append({
                "code": "UNSATISFIABLE_CLASS",
                "class": cls,
                "detail": f"{cls} is a subclass of both {a} and {b}, which are declared disjoint",
            })

    for a, b in onto.disjoint:
        if a == b:
            findings.append({"code": "DISJOINT_SELF", "class": a,
                             "detail": f"{a} is declared disjoint with itself"})

    for cycle in _find_cycles(onto):
        findings.append({"code": "SUBCLASS_CYCLE", "class": cycle[0],
                         "detail": "subclass cycle: " + " -> ".join(cycle)})

    declared = set(onto.classes)
    for prop in onto.properties.values():
        for side, ref in (("domain", prop.domain), ("range", prop.range)):
            if ref is not None and ref not in declared:
                findings.append({"code": "DANGLING_REFERENCE", "property": prop.name,
                                 "detail": f"{prop.name} {side} names undeclared class {ref}"})
    for a, b in onto.disjoint:
        for ref in (a, b):
            if ref not in declared:
                findings.append({"code": "DANGLING_REFERENCE", "class": ref,
                                 "detail": f"disjoint pair names undeclared class {ref}"})
    for cls, parents in onto.classes.items():
        for parent in parents:
            if parent not in declared:
                findings.append({"code": "DANGLING_REFERENCE", "class": cls,
                                 "detail": f"{cls} has undeclared parent class {parent}"})

    return {
        "status": "ONTOLOGY_INCONSISTENT" if findings else "CONSISTENT",
        "findings": findings,
        "classes": len(onto.classes),
        "properties": len(onto.properties),
        "disjoint_pairs": len(onto.disjoint),
    }
