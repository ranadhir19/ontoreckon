"""Graph input: the N-Triples subset.

One triple per line::

    <subject> <predicate> <object> .

The object may be an IRI (``<...>``) or a string literal (``"..."``).
``#`` comment lines and blank lines are ignored. Classes, properties
and entities are identified by local name (see ``model.local_name``);
class membership is written with the ``rdf:type`` predicate, whose
local name is ``type``.

Any non-blank, non-comment line outside this grammar is returned in
the ``unsupported`` list with ``PARSE_UNSUPPORTED`` and its line
number — never silently dropped. Content on such a line takes no part
in any verdict, and the audit report counts it, so a graph the subset
cannot read says so instead of passing quietly.
"""

from __future__ import annotations

from .model import Triple
from .ontology import _parse_triple_lines


def load_graph(path: str):
    """Returns (triples, unsupported): list[Triple], list[dict]."""
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    raw, unsupported = _parse_triple_lines(text)
    triples = [
        Triple(subject=s, predicate=p, object=o, object_is_literal=is_lit)
        for (s, p, o, is_lit) in raw
    ]
    return triples, unsupported
