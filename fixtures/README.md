# Fixtures

Hand-written fixtures whose correct verdicts are known in advance, so
the auditor is itself tested against ground truth.

- `org_ontology.json` / `org_ontology.ttl` — the same small "org"
  ontology in ontoreckon's two input formats (JSON profile and Turtle
  subset). Classes: Agent ⊒ Person ⊒ Employee; Organization; City;
  Vehicle ⊒ Car; Animal ⊒ Dog; Food. Person and Organization are
  disjoint. `hasManager` carries max_cardinality 1. The ontology is
  consistent: pre-flight must return CONSISTENT, and both formats
  must parse to the identical profile.
- `org_graph.nt` — a 22-triple graph in the N-Triples subset with
  planted hazards:
  - 11 conformant triples (the known-good arm — the closed-world
    reading must produce **zero** false VIOLATING stamps here),
  - a disjoint-class membership (`Pat` typed Person and
    Organization) → VIOLATING / DISJOINT_CLASS ×2,
  - a cardinality breach (Carol has two managers) → VIOLATING /
    CARDINALITY_BREACH,
  - a domain violation (Acme worksFor Alice) → DOMAIN_VIOLATION,
  - a range violation (Bob worksFor Jacksonville) → RANGE_VIOLATION,
  - an undeclared property (Alice likes Bob) → UNDECLARED_PROPERTY,
  - an untyped entity (Ghost) and an entity typed with an undeclared
    class (Zed/Wizard) → UNVERIFIABLE / UNTYPED_ENTITY and
    UNKNOWN_CLASS,
  - the two hops of a planted **non-composable path**
    (Alice -owns-> Rex -eats-> Bone: range(owns)=Vehicle and
    domain(eats)=Animal share no subclass) → the path audit must
    refuse it with NON_COMPOSABLE_JOIN,
  - and a planted **valid path** (Alice -worksFor-> Acme
    -locatedIn-> Jacksonville) → PATH_VALID.
  Expected audit totals: 22 triples — 11 CONFORMANT, 6 VIOLATING,
  5 UNVERIFIABLE; violation rate over the 17 decidable triples
  6/17 ≈ 0.353.
- `broken_ontology.json` — an ontology variant whose class
  `PersonOrg` is declared a subclass of both Person and
  Organization, which are disjoint: the planted unsatisfiable class.
  Pre-flight must return ONTOLOGY_INCONSISTENT naming PersonOrg.
