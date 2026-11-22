# IP / legal compliance record — ontoreckon

- **Original name:** "ontoreckon" was coined for this project.
  Collision-checked against GitHub, PyPI, and npm on 2026-11-21 in
  the landscape scan and re-verified the same day at build time
  (GitHub repository search: 0 results; PyPI: 404; npm: 404). Full
  record in [NAME_CHECK.md](NAME_CHECK.md). (The scan's runner-up
  candidate `ontoproof` was rejected: the name is already a GitHub
  repository.)
- **Original code and copy:** all code and documentation in this
  repository were written for this project. The motivating idea —
  that a knowledge graph should be checked against its declared
  ontology, and its answer paths for composability, before an agent
  reasons over it — came from a landscape analysis of GraphRAG and
  semantic-layer tools; no third-party code, text, or documentation
  was copied from any of them.
- **No entrant code reused, no entrant dependency:** v1 imports
  nothing outside the Python standard library. In particular:
  - **RDFLib (BSD-3-Clause) and pySHACL (Apache-2.0):** not used,
    not imported, not vendored. The scan records that a future
    version *could* build on them without license friction; v1 does
    not, both to keep the offline/stdlib guarantee and because the
    verdict model (a declared closed-world profile reading) is this
    tool's own design, not SHACL's.
  - **owlready2 (LGPL-3.0-or-later):** not used; nothing LGPL is
    embedded in this permissively licensed deliverable. Its Java
    reasoner runtime (HermiT/Pellet) is likewise absent by design.
  - **FalkorDB (SSPL), Neo4j Community (GPLv3), Stardog / GraphDB
    (proprietary):** no code used, no dependency; their documented
    behaviour informed the landscape scan only.
  - **GraphRAG / LightRAG / Cognee / Graphiti / TrustGraph
    (MIT / Apache-2.0):** no code used; ontoreckon audits graphs
    such tools produce, from their exported data, and depends on
    none of them.
- **Original design decision, recorded as such:** the closed-world
  reinterpretation of declared domain/range/cardinality/disjointness
  as constraints (documented in the README) is ontoreckon's own
  stated design choice, not a representation of OWL semantics.
- **License:** this project is released under the MIT License
  ([LICENSE](LICENSE)).
- **Third-party dependencies:** none. The implementation uses only
  the Python standard library, so there are no third-party licenses
  to comply with and nothing bundled to attribute.
- **Asset provenance:** no images, fonts, data files, or other
  assets are bundled. The fixtures under `fixtures/` were written by
  hand for this project; their planted defects are labelled as such.
- **Secrets scan:** the tree contains no credentials or key material
  of any kind.
