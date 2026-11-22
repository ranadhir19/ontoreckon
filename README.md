# ontoreckon

**The ontology conformance and path auditor for knowledge graphs.**

AI systems now reason over knowledge graphs that other tools built —
GraphRAG, LightRAG, Cognee, Graphiti and their peers extract entities
and relations from text and present the result as a graph an agent
may traverse. Almost nothing checks whether the graph obeys the
meaning its builders declared for it. The dominant builders accept
no ontology input at all; where enforcement exists it is bound
inside one platform and reports no verdicts; and no tool audits the
multi-hop answer paths agents actually traverse — a chain can be
plausible hop by hop and semantically invalid at the join, and it
will still be answered.

ontoreckon audits a graph somebody else's tool built. Given the
graph (N-Triples subset) and its declared ontology (a small JSON
profile, or the same profile in a documented Turtle subset), it
stamps every triple:

- **CONFORMANT** — every declared constraint the evidence can check
  is satisfied.
- **VIOLATING** — the triple positively contradicts a declared
  constraint, with a machine-readable reason code
  (`DOMAIN_VIOLATION`, `RANGE_VIOLATION`, `DISJOINT_CLASS`,
  `CARDINALITY_BREACH`, `UNDECLARED_PROPERTY`).
- **UNVERIFIABLE** — the evidence needed to decide is missing
  (an untyped entity, an undeclared class). Missing evidence is
  never conformant-by-default.

It publishes the graph's **violation rate** over decidable triples,
checks the ontology itself first (**pre-flight**: unsatisfiable
classes, disjointness contradictions, subclass cycles, dangling
references), and audits **multi-hop answer paths** hop by hop: a
path is answered only if every hop exists, every hop stamps
CONFORMANT, and every join **composes** — the range of each relation
shares a class with the domain of the next under the subclass
hierarchy. Failing paths are refused with the failing hop or join
and its reason code named.

Pure Python standard library. Offline. No model calls.

## The closed-world reading (a deliberate, documented choice)

In OWL, `domain` and `range` are *inference axioms* under open-world
semantics: stating that `worksFor` has domain `Person` does not make
`Acme worksFor Alice` an error — it makes Acme a Person. Nothing is
ever *violated*; things are only ever *inferred*. That is why "the
graph has an ontology" so often means nothing was checked.

ontoreckon deliberately re-interprets the declared domain, range,
cardinality and disjointness declarations of its profile as
**constraints**, under a closed-world reading, and says so in the
header of every report. This is a design decision, made openly: it
is the reading under which a declared ontology can stamp verdicts at
all, it matches what builders and buyers uniformly believe their
declarations mean, and its known cost — a declaration written for
inference may stamp VIOLATING where an OWL reasoner would infer —
is the user's to accept when they point the tool at a profile. The
fixture's known-good arm exists to keep the reading honest: it must
produce zero false VIOLATING stamps, and `validate.py` enforces it.

## Quick start

```bash
# 0. Check the ontology itself before trusting it as a yardstick
python3 -m ontoreckon preflight --ontology ontology.json

# 1. Audit a graph against its declared ontology
python3 -m ontoreckon audit --ontology ontology.json \
    --graph graph.nt --out report.json

# 2. Audit a multi-hop answer path before an agent traverses it
python3 -m ontoreckon path --ontology ontology.json --graph graph.nt \
    --path Alice,worksFor,Acme,locatedIn,Jacksonville
python3 -m ontoreckon path --ontology ontology.json --graph graph.nt \
    --from Alice --relations worksFor,locatedIn
```

`path` exits 0 only when the path is PATH_VALID; `preflight` exits
0 only when the ontology is CONSISTENT.

## Reading an audit report

```
triples audited: 22
  CONFORMANT:   11
  VIOLATING:     6
  UNVERIFIABLE:  5
violation rate (decidable triples): 0.353 over 17 decidable
```

- **Violation rate** = VIOLATING / (CONFORMANT + VIOLATING) — over
  the triples the evidence could actually decide. UNVERIFIABLE
  triples are excluded from the rate and counted separately: a
  graph that is mostly untyped has a small decidable base, and the
  report says so rather than laundering absence into a clean rate.
- **Per-relation breakdowns** in the JSON report show which of the
  builder's relations carry the violations.

Reason codes: for triples — `DOMAIN_VIOLATION`, `RANGE_VIOLATION`,
`DISJOINT_CLASS`, `CARDINALITY_BREACH`, `UNDECLARED_PROPERTY`,
`UNKNOWN_CLASS`, `UNTYPED_ENTITY`, `OK`; for paths —
`EDGE_NOT_IN_GRAPH`, `NON_COMPOSABLE_JOIN`, `JOIN_UNCONSTRAINED`,
`HOP_VIOLATING`, `HOP_UNVERIFIABLE`; for pre-flight —
`UNSATISFIABLE_CLASS`, `DISJOINT_SELF`, `SUBCLASS_CYCLE`,
`DANGLING_REFERENCE`; for input outside the documented subsets —
`PARSE_UNSUPPORTED` (listed with line numbers, never dropped).

## Input formats

**Ontology — JSON profile** (ontoreckon's own format):

```json
{
  "name": "org",
  "classes": [{"name": "Person", "parents": ["Agent"]}],
  "properties": [{"name": "worksFor", "domain": "Person",
                  "range": "Organization", "max_cardinality": 1}],
  "disjoint": [["Person", "Organization"]]
}
```

**Ontology — Turtle subset:** one declaration per line as an
`<s> <p> <o> .` triple; recognised predicates by local name:
`type` (object `Class` / `ObjectProperty`), `subClassOf`, `domain`,
`range`, `disjointWith`, and `maxCardinality` (object an integer
literal — a documented profile extension: OWL expresses cardinality
through restriction blank nodes, which the subset flattens to a
direct declaration). Anything else is `PARSE_UNSUPPORTED`.

**Graph — N-Triples subset:** one `<s> <p> <o> .` triple per line;
the object may be a string literal; class membership uses the
`rdf:type` predicate. Classes, properties and entities are
identified by local name (text after the last `:`, `#` or `/`).

## The fixture

[`fixtures/`](fixtures/) holds a small org ontology (in both input
formats — they must parse to the identical profile) and a 22-triple
graph with planted hazards whose correct verdicts are known in
advance: a domain violation, a range violation, a disjoint-class
membership, a cardinality breach, an undeclared property, an
untyped entity, an entity typed with an undeclared class, a valid
multi-hop path that must pass, and a non-composable path
(Alice -owns-> Rex -eats-> Bone: range(owns) is Vehicle,
domain(eats) is Animal, no class sits under both) that must be
refused. A second ontology fixture plants an unsatisfiable class
(`PersonOrg`, subclass of two disjoint classes) for the pre-flight.
Shipped audit of the fixture graph: **11 CONFORMANT, 6 VIOLATING,
5 UNVERIFIABLE, violation rate 0.353** over 17 decidable triples.

## Trust model (read this before trusting it)

- **The verdicts are only as good as the profile.** ontoreckon
  checks a graph against the ontology it is *given*. A wrong or
  thin ontology yields stamps that are mechanically correct and
  substantively meaningless; the pre-flight screens the profile's
  internal consistency, not its fidelity to the world.
- **Closed-world is a stance, not a fact.** See "The closed-world
  reading" above. Profiles authored for OWL inference may stamp
  violations an OWL user would call inferences.
- **UNVERIFIABLE is a first-class outcome.** Most real builder
  exports are type-poor; if most triples come back UNVERIFIABLE,
  that *is* the audit result — the graph cannot be checked as
  shipped — and the honest next step is the measurement, not a
  forced verdict.
- **Composability is schema-level.** A join is composable when the
  declared range and the next declared domain share a subclass —
  a property of the path pattern, decidable from the profile alone.
  ontoreckon does not invent composition semantics the ontology
  does not declare; ontology-declared property-chain axioms are
  not in the v1 profile format (see the coverage statement in
  `validate.py`).
- **What v1 does not do:** GraphRAG/LightRAG JSON export ingestion
  (v1 graph input is the N-Triples subset); OWL reasoning of any
  kind; min/qualified cardinality. The coverage statement in
  `validate.py` lists exactly what v1 implements.

## Development

```bash
python3 validate.py   # full test suite + CLI fixture checks; exit 0 = green
```

## License

MIT. See [LICENSE](LICENSE). Name-collision record:
[NAME_CHECK.md](NAME_CHECK.md). Compliance record:
[COMPLIANCE.md](COMPLIANCE.md).
