"""Tests for ontoreckon against the planted-hazard fixtures.

Every planted item in fixtures/ has a known-correct verdict; these
tests assert the auditor produces exactly it. The known-good arm
(11 conformant triples) must produce zero VIOLATING stamps — the
scan's pre-registered kill criterion (ii) is a >5% false-violation
rate on that arm; the suite enforces 0%.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ontoreckon import audit as audit_mod
from ontoreckon import graphload, ontology as ontology_mod, pathaudit
from ontoreckon.model import Triple

FIXTURES = os.path.join(os.path.dirname(__file__), "..", "fixtures")


def load(name):
    return os.path.join(FIXTURES, name)


class FixtureBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.onto, _ = ontology_mod.load_ontology(load("org_ontology.json"))
        cls.triples, cls.unsupported = graphload.load_graph(load("org_graph.nt"))
        cls.stamped = audit_mod.audit_triples(cls.onto, cls.triples)
        cls.by_triple = {(s["subject"], s["predicate"], s["object"]): s for s in cls.stamped}

    def stamp(self, s, p, o):
        return self.by_triple[(s, p, o)]


class TestFixtureAudit(FixtureBase):
    def test_graph_parsed_fully(self):
        self.assertEqual(len(self.triples), 22)
        self.assertEqual(self.unsupported, [])

    def test_headline_counts(self):
        summary = audit_mod.summarise(self.stamped)
        self.assertEqual(summary["total"], 22)
        self.assertEqual(summary["conformant"], 11)
        self.assertEqual(summary["violating"], 6)
        self.assertEqual(summary["unverifiable"], 5)
        self.assertEqual(summary["decidable"], 17)
        self.assertAlmostEqual(summary["violation_rate_decidable"], 6 / 17, places=9)

    def test_known_good_arm_has_no_false_violations(self):
        good = [
            ("Alice", "type", "Employee"), ("Bob", "type", "Person"),
            ("Carol", "type", "Employee"), ("Dave", "type", "Person"),
            ("Erin", "type", "Person"), ("Acme", "type", "Organization"),
            ("Jacksonville", "type", "City"),
            ("Alice", "worksFor", "Acme"), ("Acme", "locatedIn", "Jacksonville"),
            ("Bob", "mentors", "Alice"), ("Carol", "hasManager", "Dave"),
        ]
        for key in good:
            entry = self.stamp(*key)
            self.assertEqual(entry["stamp"], "CONFORMANT", f"{key}: {entry}")

    def test_domain_violation(self):
        entry = self.stamp("Acme", "worksFor", "Alice")
        self.assertEqual((entry["stamp"], entry["code"]), ("VIOLATING", "DOMAIN_VIOLATION"))

    def test_range_violation(self):
        entry = self.stamp("Bob", "worksFor", "Jacksonville")
        self.assertEqual((entry["stamp"], entry["code"]), ("VIOLATING", "RANGE_VIOLATION"))

    def test_disjoint_class(self):
        for obj in ("Person", "Organization"):
            entry = self.stamp("Pat", "type", obj)
            self.assertEqual((entry["stamp"], entry["code"]), ("VIOLATING", "DISJOINT_CLASS"))

    def test_cardinality_breach(self):
        entry = self.stamp("Carol", "hasManager", "Erin")
        self.assertEqual((entry["stamp"], entry["code"]), ("VIOLATING", "CARDINALITY_BREACH"))

    def test_undeclared_property(self):
        entry = self.stamp("Alice", "likes", "Bob")
        self.assertEqual((entry["stamp"], entry["code"]), ("VIOLATING", "UNDECLARED_PROPERTY"))

    def test_untyped_entity(self):
        entry = self.stamp("Ghost", "mentors", "Alice")
        self.assertEqual((entry["stamp"], entry["code"]), ("UNVERIFIABLE", "UNTYPED_ENTITY"))
        entry = self.stamp("Alice", "owns", "Rex")
        self.assertEqual((entry["stamp"], entry["code"]), ("UNVERIFIABLE", "UNTYPED_ENTITY"))

    def test_unknown_class(self):
        entry = self.stamp("Zed", "type", "Wizard")
        self.assertEqual((entry["stamp"], entry["code"]), ("UNVERIFIABLE", "UNKNOWN_CLASS"))
        entry = self.stamp("Zed", "mentors", "Alice")
        self.assertEqual((entry["stamp"], entry["code"]), ("UNVERIFIABLE", "UNKNOWN_CLASS"))


class TestPreflight(unittest.TestCase):
    def test_fixture_ontology_consistent(self):
        onto, _ = ontology_mod.load_ontology(load("org_ontology.json"))
        pre = ontology_mod.preflight(onto)
        self.assertEqual(pre["status"], "CONSISTENT")
        self.assertEqual(pre["findings"], [])

    def test_planted_unsatisfiable_class(self):
        onto, _ = ontology_mod.load_ontology(load("broken_ontology.json"))
        pre = ontology_mod.preflight(onto)
        self.assertEqual(pre["status"], "ONTOLOGY_INCONSISTENT")
        unsat = [f for f in pre["findings"] if f["code"] == "UNSATISFIABLE_CLASS"]
        self.assertEqual(len(unsat), 1)
        self.assertEqual(unsat[0]["class"], "PersonOrg")


class TestFormatsAgree(unittest.TestCase):
    def test_turtle_parses_to_same_profile_as_json(self):
        onto_json, _ = ontology_mod.load_ontology(load("org_ontology.json"))
        onto_ttl, unsupported = ontology_mod.load_ontology(load("org_ontology.ttl"))
        self.assertEqual(unsupported, [])
        self.assertEqual(onto_ttl.classes, onto_json.classes)
        self.assertEqual(set(onto_ttl.disjoint), set(onto_json.disjoint))
        for name, prop in onto_json.properties.items():
            other = onto_ttl.properties[name]
            self.assertEqual((other.domain, other.range, other.max_cardinality),
                             (prop.domain, prop.range, prop.max_cardinality), name)
        pre = ontology_mod.preflight(onto_ttl)
        self.assertEqual(pre["status"], "CONSISTENT")


class TestPaths(FixtureBase):
    def test_valid_path(self):
        path = [Triple("Alice", "worksFor", "Acme"), Triple("Acme", "locatedIn", "Jacksonville")]
        result = pathaudit.audit_path(self.onto, self.triples, path)
        self.assertEqual(result["verdict"], "PATH_VALID")
        self.assertEqual(result["joins"][0]["status"], "COMPOSABLE")

    def test_non_composable_path_refused(self):
        path = [Triple("Alice", "owns", "Rex"), Triple("Rex", "eats", "Bone")]
        result = pathaudit.audit_path(self.onto, self.triples, path)
        self.assertEqual(result["verdict"], "PATH_REFUSED")
        self.assertEqual(result["refusal"]["code"], "NON_COMPOSABLE_JOIN")
        self.assertEqual(result["refusal"]["hop"], 2)

    def test_missing_edge_refused(self):
        path = [Triple("Alice", "worksFor", "Jacksonville")]
        result = pathaudit.audit_path(self.onto, self.triples, path)
        self.assertEqual(result["verdict"], "PATH_REFUSED")
        self.assertEqual(result["refusal"]["code"], "EDGE_NOT_IN_GRAPH")

    def test_violating_hop_refused(self):
        path = [Triple("Bob", "worksFor", "Jacksonville")]
        result = pathaudit.audit_path(self.onto, self.triples, path)
        self.assertEqual(result["verdict"], "PATH_REFUSED")
        self.assertEqual(result["refusal"]["code"], "HOP_VIOLATING")

    def test_enumerate_mode(self):
        results = pathaudit.enumerate_paths(self.onto, self.triples, "Alice",
                                            ["worksFor", "locatedIn"])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["verdict"], "PATH_VALID")
        results = pathaudit.enumerate_paths(self.onto, self.triples, "Alice", ["owns", "eats"])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["verdict"], "PATH_REFUSED")
        self.assertEqual(results[0]["refusal"]["code"], "NON_COMPOSABLE_JOIN")


class TestParseUnsupported(unittest.TestCase):
    def test_out_of_subset_line_is_reported_not_dropped(self):
        from ontoreckon.ontology import _parse_triple_lines
        text = '<ex:A> <ex:p> <ex:B> .\nthis is not a triple\n<ex:A> <rdf:type> <ex:C> .\n'
        raw, unsupported = _parse_triple_lines(text)
        self.assertEqual(len(raw), 2)
        self.assertEqual(len(unsupported), 1)
        self.assertEqual(unsupported[0]["code"], "PARSE_UNSUPPORTED")
        self.assertEqual(unsupported[0]["line"], 2)


if __name__ == "__main__":
    unittest.main()
