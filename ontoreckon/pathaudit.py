"""The path audit: may an agent traverse this chain?

A multi-hop answer path is a sequence of triples
``(e0, p1, e1), (e1, p2, e2), ...``. ontoreckon answers a path only
if it is valid on three independent grounds, checked in this order:

1. **Existence** — every hop triple is present in the graph
   (else refusal code ``EDGE_NOT_IN_GRAPH``).
2. **Composability** — at every join, the two relations compose
   under the ontology: the range class of the incoming property and
   the domain class of the outgoing property share at least one
   class in their subclass closures (some class is a
   subclass-or-self of both). This is a schema-level property of the
   path pattern, derived only from declared domain/range and the
   subclass hierarchy — no semantics are invented: if the declared
   range and the next declared domain admit no common class, no
   typing of the join entity could ever make both hops conformant,
   so the path is refused outright (``NON_COMPOSABLE_JOIN``), naming
   the join. If either side declares no domain/range, composability
   cannot be decided and the join is UNVERIFIABLE
   (``JOIN_UNCONSTRAINED``) — which also refuses the path, because
   ontoreckon answers only verified paths.
3. **Hop verdicts** — every hop triple stamps CONFORMANT in the
   triple audit. A VIOLATING hop refuses with that hop's own code
   (``HOP_VIOLATING``); an UNVERIFIABLE hop refuses with
   ``HOP_UNVERIFIABLE``.

Verdicts: ``PATH_VALID`` (all three grounds hold) or
``PATH_REFUSED`` with the failing hop/join and reason code named.
Refusal is the default for anything not positively valid — the
verified-or-refuse discipline applied to reasoning chains.
"""

from __future__ import annotations

from .audit import CONFORMANT, VIOLATING, audit_triples
from .model import Ontology, Triple

PATH_VALID = "PATH_VALID"
PATH_REFUSED = "PATH_REFUSED"


def composability(onto: Ontology, pred_in: str, pred_out: str) -> tuple[str, str]:
    """(status, detail) for the join pred_in -> pred_out.

    status: COMPOSABLE / NON_COMPOSABLE / UNCONSTRAINED.
    """
    p_in = onto.properties.get(pred_in)
    p_out = onto.properties.get(pred_out)
    if p_in is None or p_out is None:
        return "UNCONSTRAINED", "an undeclared property takes part in the join"
    if p_in.range is None or p_out.domain is None:
        return "UNCONSTRAINED", (
            f"range({pred_in})={p_in.range} or domain({pred_out})={p_out.domain} undeclared")
    common = onto.subclasses(p_in.range) & onto.subclasses(p_out.domain)
    if common:
        return "COMPOSABLE", f"common class(es) under range/domain: {sorted(common)}"
    return "NON_COMPOSABLE", (
        f"no class is a subclass of both range({pred_in})={p_in.range} "
        f"and domain({pred_out})={p_out.domain}")


def audit_path(onto: Ontology, triples: list[Triple], path: list[Triple]) -> dict:
    """Audit one explicit path (list of hop triples, chained)."""
    graph_index = {t.as_tuple(): t for t in triples}
    stamped = {s["subject"] + "\0" + s["predicate"] + "\0" + s["object"]: s
               for s in audit_triples(onto, triples)}

    hops = []
    refusal = None
    for i, hop in enumerate(path):
        key = hop.subject + "\0" + hop.predicate + "\0" + hop.object
        entry = {"hop": i + 1, "subject": hop.subject, "predicate": hop.predicate,
                 "object": hop.object, "present": hop.as_tuple() in graph_index}
        if not entry["present"]:
            entry["stamp"] = None
            if refusal is None:
                refusal = {"code": "EDGE_NOT_IN_GRAPH", "hop": i + 1,
                           "detail": f"hop {i + 1} triple is not in the graph"}
        else:
            entry["stamp"] = stamped[key]["stamp"]
            entry["code"] = stamped[key]["code"]
        hops.append(entry)

    joins = []
    if refusal is None:
        for i in range(len(path) - 1):
            status, detail = composability(onto, path[i].predicate, path[i + 1].predicate)
            joins.append({"join": i + 1, "between_hops": [i + 1, i + 2],
                          "at_entity": path[i].object, "status": status, "detail": detail})
            if status == "NON_COMPOSABLE" and refusal is None:
                refusal = {"code": "NON_COMPOSABLE_JOIN", "hop": i + 2, "detail": detail}
            elif status == "UNCONSTRAINED" and refusal is None:
                refusal = {"code": "JOIN_UNCONSTRAINED", "hop": i + 2, "detail": detail}

    if refusal is None:
        for entry in hops:
            if entry["stamp"] == VIOLATING:
                refusal = {"code": "HOP_VIOLATING", "hop": entry["hop"],
                           "detail": f"hop {entry['hop']} stamps VIOLATING ({entry['code']})"}
                break
            if entry["stamp"] != CONFORMANT:
                refusal = {"code": "HOP_UNVERIFIABLE", "hop": entry["hop"],
                           "detail": f"hop {entry['hop']} stamps {entry['stamp']} ({entry['code']})"}
                break

    return {
        "verdict": PATH_REFUSED if refusal else PATH_VALID,
        "refusal": refusal,
        "hops": hops,
        "joins": joins,
        "path": [list(h.as_tuple()) for h in path],
    }


def enumerate_paths(onto: Ontology, triples: list[Triple], start: str,
                    relations: list[str]) -> list[dict]:
    """All walks from ``start`` following the relation sequence.

    At each step, every graph triple with the current entity as
    subject and the next relation as predicate extends the walk.
    Each completed walk is audited with :func:`audit_path`. If no
    walk completes the sequence, a single PATH_REFUSED result with
    ``EDGE_NOT_IN_GRAPH`` at the first step that has no continuation
    is returned.
    """
    walks: list[list[Triple]] = [[]]
    current_entities: list[str] = [start]
    dead_at = None
    for step, rel in enumerate(relations):
        next_walks, next_entities = [], []
        for walk, entity in zip(walks, current_entities):
            for t in triples:
                if t.subject == entity and t.predicate == rel and not t.object_is_literal:
                    next_walks.append(walk + [t])
                    next_entities.append(t.object)
        if not next_walks:
            dead_at = step + 1
            break
        walks, current_entities = next_walks, next_entities
    if dead_at is not None:
        return [{"verdict": PATH_REFUSED,
                 "refusal": {"code": "EDGE_NOT_IN_GRAPH", "hop": dead_at,
                             "detail": f"no {relations[dead_at - 1]} edge continues the walk"},
                 "hops": [], "joins": [], "path": []}]
    return [audit_path(onto, triples, walk) for walk in walks]
