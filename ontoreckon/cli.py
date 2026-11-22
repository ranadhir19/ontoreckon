"""Command-line interface.

    ontoreckon preflight --ontology ONTOLOGY.json|.ttl
    ontoreckon audit     --ontology ONTOLOGY --graph GRAPH.nt [--out report.json]
    ontoreckon path      --ontology ONTOLOGY --graph GRAPH.nt
                         --path E1,p1,E2,p2,E3
    ontoreckon path      --ontology ONTOLOGY --graph GRAPH.nt
                         --from E1 --relations p1,p2

``audit`` runs the ontology pre-flight first and embeds its verdict
in the report; the triple stamps are mechanical and are produced
either way, but a report whose pre-flight is ONTOLOGY_INCONSISTENT
says so in its header — stamps against a broken ontology are not
presented as trustworthy.
"""

from __future__ import annotations

import argparse
import json
import sys

from . import audit as audit_mod
from . import graphload, ontology as ontology_mod, pathaudit
from .model import Triple


def _load(path_ontology: str):
    onto, unsupported = ontology_mod.load_ontology(path_ontology)
    return onto, unsupported


def print_preflight(pre: dict) -> None:
    print(f"preflight: {pre['status']} "
          f"({pre['classes']} classes, {pre['properties']} properties, "
          f"{pre['disjoint_pairs']} disjoint pairs)")
    for f in pre["findings"]:
        print(f"  {f['code']}: {f['detail']}")


def cmd_preflight(args) -> int:
    onto, unsupported = _load(args.ontology)
    pre = ontology_mod.preflight(onto)
    print_preflight(pre)
    for u in unsupported:
        print(f"  PARSE_UNSUPPORTED: {u}")
    return 0 if pre["status"] == "CONSISTENT" else 1


def print_audit_summary(report: dict) -> None:
    s = report["summary"]
    print(f"ontology: {report['ontology']['name']} ({report['ontology']['source']})")
    print(f"preflight: {report['preflight']['status']}")
    print(f"graph: {report['graph']['source']}")
    print(f"triples audited: {s['total']}")
    print(f"  CONFORMANT:   {s['conformant']}")
    print(f"  VIOLATING:    {s['violating']}")
    print(f"  UNVERIFIABLE: {s['unverifiable']}")
    rate = s["violation_rate_decidable"]
    print(f"violation rate (decidable triples): {'n/a' if rate is None else format(rate, '.3f')} "
          f"over {s['decidable']} decidable")
    if s["per_code"]:
        print("per reason code:")
        for code, n in s["per_code"].items():
            print(f"  {code}: {n}")
    if report["graph"]["parse_unsupported"]:
        print(f"parse-unsupported lines: {len(report['graph']['parse_unsupported'])} "
              f"(listed in the report, never silently dropped)")


def cmd_audit(args) -> int:
    onto, unsupported_onto = _load(args.ontology)
    pre = ontology_mod.preflight(onto)
    triples, unsupported_graph = graphload.load_graph(args.graph)
    report = audit_mod.build_report(onto, triples, pre, args.graph, unsupported_graph)
    if unsupported_onto:
        report["ontology_parse_unsupported"] = unsupported_onto
    print_audit_summary(report)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2)
        print(f"report written: {args.out}")
    return 0


def _parse_path_spec(spec: str) -> list[Triple]:
    parts = [p.strip() for p in spec.split(",")]
    if len(parts) < 3 or len(parts) % 2 == 0:
        raise ValueError("path must be E1,p1,E2[,p2,E3...] (odd number of items, >= 3)")
    hops = []
    for i in range(0, len(parts) - 2, 2):
        hops.append(Triple(subject=parts[i], predicate=parts[i + 1], object=parts[i + 2]))
    return hops


def print_path_result(result: dict) -> None:
    pretty = " -> ".join(
        [result["path"][0][0]] + [f"-[{h[1]}]-> {h[2]}" for h in result["path"]]
    ) if result["path"] else "(no walk)"
    print(f"path: {pretty}")
    print(f"verdict: {result['verdict']}")
    if result["refusal"]:
        r = result["refusal"]
        print(f"  refused at hop {r['hop']}: {r['code']} — {r['detail']}")
    for j in result["joins"]:
        print(f"  join {j['join']} at {j['at_entity']}: {j['status']} — {j['detail']}")


def cmd_path(args) -> int:
    onto, _ = _load(args.ontology)
    triples, _ = graphload.load_graph(args.graph)
    if args.path:
        results = [pathaudit.audit_path(onto, triples, _parse_path_spec(args.path))]
    else:
        relations = [r.strip() for r in args.relations.split(",") if r.strip()]
        results = pathaudit.enumerate_paths(onto, triples, args.start, relations)
    for result in results:
        print_path_result(result)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(results, fh, indent=2)
        print(f"report written: {args.out}")
    return 0 if all(r["verdict"] == pathaudit.PATH_VALID for r in results) else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="ontoreckon", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("preflight", help="check the ontology itself for consistency defects")
    p.add_argument("--ontology", required=True)
    p.set_defaults(func=cmd_preflight)

    p = sub.add_parser("audit", help="stamp every graph triple against the ontology")
    p.add_argument("--ontology", required=True)
    p.add_argument("--graph", required=True)
    p.add_argument("--out")
    p.set_defaults(func=cmd_audit)

    p = sub.add_parser("path", help="audit a multi-hop answer path")
    p.add_argument("--ontology", required=True)
    p.add_argument("--graph", required=True)
    p.add_argument("--path", help="E1,p1,E2[,p2,E3...]")
    p.add_argument("--from", dest="start", help="start entity (with --relations)")
    p.add_argument("--relations", help="comma-separated relation sequence (with --from)")
    p.add_argument("--out")
    p.set_defaults(func=cmd_path)

    args = parser.parse_args(argv)
    if args.command == "path" and not args.path and not (args.start and args.relations):
        parser.error("path needs --path, or --from with --relations")
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
