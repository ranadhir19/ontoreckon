"""The triple audit: stamp every triple against the ontology.

Stamps: CONFORMANT / VIOLATING / UNVERIFIABLE. A triple gets exactly
one stamp and one primary reason code — the first failing check in
the documented precedence order below. VIOLATING is reserved for
positive contradiction of a declared constraint; missing evidence is
UNVERIFIABLE, never conformant-by-default and never violating.

Precedence for a non-typing triple (s, p, o):

1. ``UNDECLARED_PROPERTY`` (VIOLATING) — p is not in the profile.
2. ``UNTYPED_ENTITY`` (UNVERIFIABLE) — s has no type triple, or o is
   an entity with no type triple.
3. ``UNKNOWN_CLASS`` (UNVERIFIABLE) — a type of s or o is not a
   declared class, so membership cannot be decided.
4. ``DOMAIN_VIOLATION`` (VIOLATING) — p declares a domain and no type
   of s is a subclass-or-self of it.
5. ``RANGE_VIOLATION`` (VIOLATING) — p declares a range and (o is a
   literal, or no type of o is a subclass-or-self of the range).
6. ``CARDINALITY_BREACH`` (VIOLATING) — p declares max_cardinality k
   and this triple is beyond the k-th distinct object for (s, p)
   (objects ordered by name, deterministically).

Typing triples (s, type, C):

- C undeclared -> UNVERIFIABLE / ``UNKNOWN_CLASS``.
- s is typed into both sides of a disjoint pair (via closure) ->
  VIOLATING / ``DISJOINT_CLASS`` (every typing triple of a conflicted
  entity carries the stamp: the conflict is a property of the
  entity's typing as a whole).
- otherwise -> CONFORMANT / ``OK``.

Violation rate is published over decidable triples:
VIOLATING / (CONFORMANT + VIOLATING). UNVERIFIABLE triples are
excluded from the rate and reported as their own count — a graph that
is mostly untyped has a small decidable base, and the report says so.
"""

from __future__ import annotations

from collections import Counter, defaultdict

from . import __version__
from .model import Ontology, Triple

CONFORMANT = "CONFORMANT"
VIOLATING = "VIOLATING"
UNVERIFIABLE = "UNVERIFIABLE"


def entity_types(triples: list[Triple]) -> dict[str, set[str]]:
    types: dict[str, set[str]] = defaultdict(set)
    for t in triples:
        if t.is_typing and not t.object_is_literal:
            types[t.subject].add(t.object)
    return types


def _stamp(triple: Triple, stamp: str, code: str, detail: str) -> dict:
    return {
        "subject": triple.subject,
        "predicate": triple.predicate,
        "object": triple.object,
        "stamp": stamp,
        "code": code,
        "detail": detail,
    }


def audit_triples(onto: Ontology, triples: list[Triple]) -> list[dict]:
    types = entity_types(triples)

    # Entities whose typing hits both sides of a disjoint pair.
    conflicted: dict[str, list[tuple[str, str]]] = {}
    for entity, tset in types.items():
        closure: set[str] = set()
        for t in tset:
            if t in onto.classes:
                closure |= onto.self_and_ancestors(t)
        pairs = onto.disjoint_pairs_among(closure)
        if pairs:
            conflicted[entity] = pairs

    # Cardinality: group non-typing triples by (subject, predicate);
    # beyond max_cardinality distinct objects (name order), the
    # excess triples breach.
    cardinality_breach: set[int] = set()
    groups: dict[tuple[str, str], list[int]] = defaultdict(list)
    for idx, t in enumerate(triples):
        if not t.is_typing and t.predicate in onto.properties:
            if onto.properties[t.predicate].max_cardinality is not None:
                groups[(t.subject, t.predicate)].append(idx)
    for (subj, pred), idxs in groups.items():
        limit = onto.properties[pred].max_cardinality
        by_object: dict[str, list[int]] = defaultdict(list)
        for idx in idxs:
            by_object[triples[idx].object].append(idx)
        for rank, obj in enumerate(sorted(by_object)):
            if rank >= limit:
                cardinality_breach.update(by_object[obj])

    results = [None] * len(triples)
    for idx, t in enumerate(triples):
        results[idx] = _stamp_one(onto, t, types, conflicted, idx in cardinality_breach)
    return results


def _stamp_one(onto: Ontology, t: Triple, types, conflicted, is_breach: bool) -> dict:
    if t.is_typing:
        if t.object not in onto.classes:
            return _stamp(t, UNVERIFIABLE, "UNKNOWN_CLASS",
                          f"class {t.object} is not declared in the ontology")
        if t.subject in conflicted:
            a, b = conflicted[t.subject][0]
            return _stamp(t, VIOLATING, "DISJOINT_CLASS",
                          f"{t.subject} is typed under both {a} and {b}, declared disjoint")
        return _stamp(t, CONFORMANT, "OK", "declared class, no disjoint conflict")

    prop = onto.properties.get(t.predicate)
    if prop is None:
        return _stamp(t, VIOLATING, "UNDECLARED_PROPERTY",
                      f"property {t.predicate} is not declared in the ontology")

    s_types = types.get(t.subject, set())
    if not s_types:
        return _stamp(t, UNVERIFIABLE, "UNTYPED_ENTITY",
                      f"subject {t.subject} has no type triple")
    unknown_s = sorted(c for c in s_types if c not in onto.classes)
    if unknown_s:
        return _stamp(t, UNVERIFIABLE, "UNKNOWN_CLASS",
                      f"subject {t.subject} typed with undeclared class {unknown_s[0]}")

    o_types: set[str] = set()
    if not t.object_is_literal:
        o_types = types.get(t.object, set())
        if not o_types:
            return _stamp(t, UNVERIFIABLE, "UNTYPED_ENTITY",
                          f"object {t.object} has no type triple")
        unknown_o = sorted(c for c in o_types if c not in onto.classes)
        if unknown_o:
            return _stamp(t, UNVERIFIABLE, "UNKNOWN_CLASS",
                          f"object {t.object} typed with undeclared class {unknown_o[0]}")

    if prop.domain is not None:
        if not any(onto.is_subclass(c, prop.domain) for c in s_types):
            return _stamp(t, VIOLATING, "DOMAIN_VIOLATION",
                          f"subject type(s) {sorted(s_types)} not within domain {prop.domain}")
    if prop.range is not None:
        if t.object_is_literal:
            return _stamp(t, VIOLATING, "RANGE_VIOLATION",
                          f"literal object where range class {prop.range} is declared")
        if not any(onto.is_subclass(c, prop.range) for c in o_types):
            return _stamp(t, VIOLATING, "RANGE_VIOLATION",
                          f"object type(s) {sorted(o_types)} not within range {prop.range}")
    if is_breach:
        return _stamp(t, VIOLATING, "CARDINALITY_BREACH",
                      f"more than {prop.max_cardinality} distinct object(s) for "
                      f"({t.subject}, {t.predicate})")
    return _stamp(t, CONFORMANT, "OK", "all declared constraints satisfied")


def summarise(stamped: list[dict]) -> dict:
    counts = Counter(s["stamp"] for s in stamped)
    per_code = Counter(s["code"] for s in stamped if s["stamp"] != CONFORMANT)
    per_relation: dict[str, Counter] = defaultdict(Counter)
    for s in stamped:
        per_relation[s["predicate"]][s["stamp"]] += 1
    decidable = counts[CONFORMANT] + counts[VIOLATING]
    return {
        "total": len(stamped),
        "conformant": counts[CONFORMANT],
        "violating": counts[VIOLATING],
        "unverifiable": counts[UNVERIFIABLE],
        "decidable": decidable,
        "violation_rate_decidable": (counts[VIOLATING] / decidable) if decidable else None,
        "per_code": dict(sorted(per_code.items())),
        "per_relation": {p: dict(sorted(c.items())) for p, c in sorted(per_relation.items())},
    }


def build_report(onto: Ontology, triples: list[Triple], pre: dict,
                 graph_source: str, parse_unsupported: list) -> dict:
    stamped = audit_triples(onto, triples)
    return {
        "tool": "ontoreckon",
        "version": __version__,
        "profile_reading": (
            "closed-world: declared domain/range/cardinality/disjointness are read as "
            "constraints, not as OWL open-world inference axioms (see README)"
        ),
        "ontology": {"name": onto.name, "source": onto.source,
                     "classes": len(onto.classes), "properties": len(onto.properties)},
        "preflight": pre,
        "graph": {"source": graph_source, "triples": len(triples),
                  "parse_unsupported": parse_unsupported},
        "summary": summarise(stamped),
        "triples": stamped,
    }
