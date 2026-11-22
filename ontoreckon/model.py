"""Core model for ontoreckon: the ontology profile and graph triples.

The ontology is held in ontoreckon's own small profile format (loaded
from JSON or from the documented Turtle subset by ``ontology.py``):

- classes, each with zero or more declared parents (subClassOf),
- properties, each with an optional domain class, range class and
  maximum cardinality,
- disjoint class pairs.

All reasoning in v1 is set operations over the subclass closure of
this finite profile. No OWL reasoner is involved, and none is needed:
under ontoreckon's declared closed-world reading (see README), the
declarations are treated as constraints, and every check below is a
membership test against a precomputed closure.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# The typing predicate. In the N-Triples / Turtle subsets an entity's
# class membership is written with the rdf:type predicate; after local
# name extraction it is the bare name "type" in the rdf namespace.
TYPE_PREDICATE = "type"


def local_name(token: str) -> str:
    """Local name of an IRI-ish token: text after the last ':', '#' or '/'.

    ``<ex:worksFor>`` -> ``worksFor``; ``rdf:type`` -> ``type``. The
    subsets ontoreckon parses identify classes, properties and
    entities by local name; two IRIs with the same local name are the
    same symbol. That is a documented simplification of the subsets,
    not a claim about RDF.
    """
    token = token.strip().strip("<>")
    for sep in ("#", "/", ":"):
        if sep in token:
            token = token.rsplit(sep, 1)[1]
    return token


@dataclass
class Property:
    name: str
    domain: str | None = None
    range: str | None = None
    max_cardinality: int | None = None


@dataclass
class Ontology:
    name: str = "unnamed"
    classes: dict[str, set[str]] = field(default_factory=dict)  # class -> parents
    properties: dict[str, Property] = field(default_factory=dict)
    disjoint: list[tuple[str, str]] = field(default_factory=list)
    source: str | None = None

    # -- closure -----------------------------------------------------
    def ancestors(self, cls: str) -> set[str]:
        """All superclasses of ``cls`` (excluding ``cls`` itself).

        Cycle-safe: a subclass cycle yields the reachable set, and the
        cycle itself is a pre-flight finding, not a hang.
        """
        seen: set[str] = set()
        stack = list(self.classes.get(cls, ()))
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            stack.extend(self.classes.get(cur, ()))
        return seen

    def self_and_ancestors(self, cls: str) -> set[str]:
        return {cls} | self.ancestors(cls)

    def is_subclass(self, cls: str, of: str) -> bool:
        """True iff ``cls`` is ``of`` or a (transitive) subclass of it."""
        return of in self.self_and_ancestors(cls)

    def subclasses(self, cls: str) -> set[str]:
        """``cls`` plus every declared class below it in the hierarchy."""
        out = {cls}
        for other in self.classes:
            if cls in self.ancestors(other):
                out.add(other)
        return out

    def disjoint_pairs_among(self, classes: set[str]) -> list[tuple[str, str]]:
        """Declared disjoint pairs (A, B) such that some member of
        ``classes`` is a subclass-or-self of A and some (possibly the
        same or another) member is a subclass-or-self of B."""
        hits = []
        for a, b in self.disjoint:
            under_a = any(self.is_subclass(c, a) for c in classes)
            under_b = any(self.is_subclass(c, b) for c in classes)
            if under_a and under_b:
                hits.append((a, b))
        return hits


@dataclass(frozen=True)
class Triple:
    subject: str
    predicate: str
    object: str
    object_is_literal: bool = False

    @property
    def is_typing(self) -> bool:
        return self.predicate == TYPE_PREDICATE

    def as_tuple(self) -> tuple[str, str, str]:
        return (self.subject, self.predicate, self.object)
