#!/usr/bin/env python3
"""Validation harness for ontoreckon.

Runs the full unit test suite (which audits the planted-hazard
fixtures, whose correct verdicts are known in advance), then
end-to-end CLI checks: preflight (consistent + broken ontology),
audit (JSON and Turtle ontology), and both path modes, asserting the
headline numbers in the JSON reports. Exit 0 only if everything
passes. Failures are fixed in the code, never by weakening these
checks.

The coverage statement at the end is part of the deliverable: it
states honestly which of the landscape scan's Position 1 claims
v0.1.0 implements, which are partial, and which are not in v1.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

COVERAGE_STATEMENT = """\
== coverage statement: scan Position 1 claims vs v1 ==
IMPLEMENTED (7):
  1. Triple audit: every triple stamped CONFORMANT / VIOLATING /
     UNVERIFIABLE with machine-readable reason codes
     (DOMAIN_VIOLATION, RANGE_VIOLATION, DISJOINT_CLASS,
     CARDINALITY_BREACH, UNDECLARED_PROPERTY, UNKNOWN_CLASS,
     UNTYPED_ENTITY); VIOLATING reserved for positive contradiction
     of a declared constraint, missing evidence is UNVERIFIABLE.
  2. Published violation rate over decidable triples, per-code and
     per-relation breakdowns, in a JSON report + human summary.
  3. Declared closed-world profile: domain/range/cardinality/
     disjointness read as constraints; the reading is stated in the
     README and in every report header (the scan's H5 discipline).
  4. Path audit: explicit paths and start+relation-sequence walks,
     checked for existence, schema-level domain/range composability
     at every join (subclass closure), and per-hop verdicts; verdict
     PATH_VALID / PATH_REFUSED with the failing hop or join and its
     reason code named. Only PATH_VALID paths are answered.
  5. Ontology pre-flight (Position 3 folded in): unsatisfiable
     classes (subclass of both members of a disjoint pair),
     disjoint-self, subclass cycles and dangling references, stamped
     CONSISTENT / ONTOLOGY_INCONSISTENT before the ontology is used.
  6. Two ontology formats for the same profile (JSON profile and a
     documented Turtle subset), one graph format (N-Triples subset);
     out-of-subset input is PARSE_UNSUPPORTED, never silently dropped.
  7. Planted-hazard fixtures: one of every defect class, a valid and
     a non-composable path, an unsatisfiable-class ontology variant;
     the fixture's known-good arm stamps with zero false violations
     (scan kill criterion (ii) enforced at 0%, stricter than its 5%).
PARTIAL (2):
  8. Declared composition rules for paths: v1 implements the
     composability rule that is derivable from the profile itself
     (domain/range chaining under subclass closure). Ontology-declared
     property-chain / composition axioms are not in the v1 profile
     format and are not checked.
  9. Cardinality: v1 supports a per-property maximum cardinality
     (flattened profile declaration). OWL min-cardinality and
     qualified cardinality are not expressible in the subset.
NOT IN V1 (2):
 10. GraphRAG / LightRAG JSON entity-relation export ingestion. v1
     graph input is the N-Triples subset only, per the build scope;
     a converter is future work, not a silent gap.
 11. Real-export kill-criterion (i) evaluation (the >50%-UNVERIFIABLE
     test across three real GraphRAG/LightRAG exports) and kill
     criterion (iii) re-check (competitor audit modes): both are
     publication-stage evaluations, not build-stage checks; the
     fixture arm of criterion (ii) IS enforced here (see 7).
"""


def run_cli(*argv):
    env = dict(os.environ, PYTHONPATH=ROOT)
    return subprocess.run([sys.executable, "-m", "ontoreckon", *argv],
                          capture_output=True, text=True, env=env, cwd=ROOT)


def cli_checks() -> list[str]:
    failures = []
    fx = os.path.join(ROOT, "fixtures")
    onto = os.path.join(fx, "org_ontology.json")
    onto_ttl = os.path.join(fx, "org_ontology.ttl")
    broken = os.path.join(fx, "broken_ontology.json")
    graph = os.path.join(fx, "org_graph.nt")

    r = run_cli("preflight", "--ontology", onto)
    if r.returncode != 0 or "CONSISTENT" not in r.stdout:
        failures.append(f"preflight consistent ontology: rc={r.returncode} out={r.stdout!r}")

    r = run_cli("preflight", "--ontology", broken)
    if r.returncode != 1 or "ONTOLOGY_INCONSISTENT" not in r.stdout or "PersonOrg" not in r.stdout:
        failures.append(f"preflight broken ontology: rc={r.returncode} out={r.stdout!r}")

    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "report.json")
        r = run_cli("audit", "--ontology", onto, "--graph", graph, "--out", out)
        if r.returncode != 0:
            failures.append(f"audit CLI: rc={r.returncode} err={r.stderr!r}")
        else:
            report = json.load(open(out))
            s = report["summary"]
            expect = {"total": 22, "conformant": 11, "violating": 6, "unverifiable": 5,
                      "decidable": 17}
            for key, want in expect.items():
                if s[key] != want:
                    failures.append(f"audit summary {key}: got {s[key]}, want {want}")
            if abs(s["violation_rate_decidable"] - 6 / 17) > 1e-9:
                failures.append(f"violation rate: got {s['violation_rate_decidable']}")
            if report["preflight"]["status"] != "CONSISTENT":
                failures.append("audit report preflight not CONSISTENT")

        out_ttl = os.path.join(tmp, "report_ttl.json")
        r = run_cli("audit", "--ontology", onto_ttl, "--graph", graph, "--out", out_ttl)
        if r.returncode != 0:
            failures.append(f"audit CLI (Turtle ontology): rc={r.returncode} err={r.stderr!r}")
        else:
            s = json.load(open(out_ttl))["summary"]
            if (s["total"], s["conformant"], s["violating"], s["unverifiable"]) != (22, 11, 6, 5):
                failures.append(f"audit (Turtle) counts differ: {s}")

        r = run_cli("path", "--ontology", onto, "--graph", graph,
                    "--path", "Alice,worksFor,Acme,locatedIn,Jacksonville")
        if r.returncode != 0 or "PATH_VALID" not in r.stdout:
            failures.append(f"path valid: rc={r.returncode} out={r.stdout!r}")

        r = run_cli("path", "--ontology", onto, "--graph", graph,
                    "--path", "Alice,owns,Rex,eats,Bone")
        if r.returncode != 1 or "NON_COMPOSABLE_JOIN" not in r.stdout:
            failures.append(f"path non-composable: rc={r.returncode} out={r.stdout!r}")

        r = run_cli("path", "--ontology", onto, "--graph", graph,
                    "--from", "Alice", "--relations", "worksFor,locatedIn")
        if r.returncode != 0 or "PATH_VALID" not in r.stdout:
            failures.append(f"path enumerate: rc={r.returncode} out={r.stdout!r}")
    return failures


def main() -> int:
    suite = unittest.defaultTestLoader.discover(os.path.join(ROOT, "tests"))
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    if not result.wasSuccessful():
        print("VALIDATION FAILED: unit tests")
        return 1
    failures = cli_checks()
    if failures:
        for f in failures:
            print(f"CLI CHECK FAILED: {f}")
        print("VALIDATION FAILED: CLI checks")
        return 1
    print("CLI checks: 7/7 passed")
    print(COVERAGE_STATEMENT)
    print("VALIDATION PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
