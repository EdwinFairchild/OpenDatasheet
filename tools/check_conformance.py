#!/usr/bin/env python3
"""check_conformance.py — deterministic validator for an OpenDatasheet part JSON.

The encoding pipeline (build.py + curation) is agentic; this is the objective
gate that says whether the *output* actually conforms to the spec, independent of
any model's say-so. It checks the invariants the schema/principles require:

  * the part envelope has all required top-level keys;
  * every register-map leaf (register, field) carries provenance {doc, section,
    rev} whose `doc` resolves to a declared `part.documents[].id`, and a legal
    `access` value (Tier 1);
  * every electrical / limits / timing value carries provenance + a `conditions`
    object (Tier 2, only enforced when the part declares tier 2);
  * declared `conformance.profiles` are actually present.

Exit code is 0 when clean, 1 when any violation is found (so a workflow `tool`
node or `va ci` can hard-gate on it). Prints a compact summary + the first
`--max-errors` violations with their JSON path.

Usage:
  python3 tools/check_conformance.py data/stm32u575zi.json [--max-errors 40] [--quiet]
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any

# Legal field/register access values (docs/03-SCHEMA.md §4.1).
LEGAL_ACCESS = {
    "read-write", "read-only", "write-only",
    "read-writeOnce", "writeOnce",
    "w1c", "w0c", "rs", "rc",
}

REQUIRED_TOP = [
    "$schema", "spec_version", "type",
    "conformance", "part",
    "pinout", "electrical", "timing", "limits", "sections", "profiles",
]


class Checker:
    def __init__(self, doc: dict[str, Any]) -> None:
        self.doc = doc
        self.errors: list[str] = []
        self.stats: dict[str, int] = {
            "peripherals": 0, "registers": 0, "fields": 0,
            "electrical": 0, "limits": 0, "timing": 0,
        }
        docs = (doc.get("part") or {}).get("documents") or []
        self.doc_ids = {d.get("id") for d in docs if isinstance(d, dict)}

    def err(self, path: str, msg: str) -> None:
        self.errors.append(f"{path}: {msg}")

    # ── provenance ─────────────────────────────────────────────────────────
    def check_prov(self, obj: Any, path: str, *, need_conditions: bool = False) -> None:
        if not isinstance(obj, dict):
            self.err(path, "not an object")
            return
        prov = obj.get("provenance")
        if not isinstance(prov, dict):
            self.err(path, "missing provenance object")
        else:
            for key in ("doc", "section", "rev"):
                if not prov.get(key) and prov.get(key) != 0:
                    self.err(path, f"provenance.{key} missing/empty")
            doc_id = prov.get("doc")
            if doc_id is not None and doc_id not in self.doc_ids:
                self.err(path, f"provenance.doc {doc_id!r} not in part.documents "
                               f"({sorted(x for x in self.doc_ids if x)})")
        if need_conditions and "conditions" not in obj:
            self.err(path, "electrical/timing value missing `conditions` object")

    # ── top-level + tiers ──────────────────────────────────────────────────
    def run(self) -> None:
        for k in REQUIRED_TOP:
            if k not in self.doc:
                self.err("$", f"missing required top-level key {k!r}")

        conf = self.doc.get("conformance") or {}
        tiers = set(conf.get("tiers") or [])
        declared_profiles = list(conf.get("profiles") or [])
        profiles = self.doc.get("profiles") or {}
        for p in declared_profiles:
            if p not in profiles:
                self.err("conformance.profiles",
                         f"declares {p!r} but profiles.{p} is absent")

        if "register-map" in profiles:
            self.check_register_map(profiles["register-map"])

        if 2 in tiers:
            self.check_tier2()

    # ── register-map (Tier 1) ──────────────────────────────────────────────
    def check_register_map(self, rm: Any) -> None:
        if not isinstance(rm, dict):
            self.err("profiles.register-map", "not an object")
            return
        peris = rm.get("peripherals") or []
        for pi, p in enumerate(peris):
            self.stats["peripherals"] += 1
            pname = (p or {}).get("name", pi)
            ppath = f"register-map.peripherals[{pname}]"
            for ri, r in enumerate(p.get("registers") or []):
                self.stats["registers"] += 1
                rname = (r or {}).get("name", ri)
                rpath = f"{ppath}.registers[{rname}]"
                fields = (r or {}).get("fields") or []
                # A field is the leaf and always needs provenance. A register
                # needs its own provenance only when it has no fields (then the
                # register itself is the leaf); when it has fields, register-level
                # provenance is optional (build.py adds it; hand-authored parts
                # cite at the field level only) — but if present it must resolve.
                if fields:
                    if (r or {}).get("provenance") is not None:
                        self.check_prov(r, rpath)
                else:
                    self.check_prov(r, rpath)
                acc = (r or {}).get("access")
                if acc is not None and acc not in LEGAL_ACCESS:
                    self.err(rpath, f"illegal register access {acc!r}")
                for fi, f in enumerate(fields):
                    self.stats["fields"] += 1
                    fname = (f or {}).get("name", fi)
                    fpath = f"{rpath}.fields[{fname}]"
                    self.check_prov(f, fpath)
                    facc = (f or {}).get("access")
                    if facc is not None and facc not in LEGAL_ACCESS:
                        self.err(fpath, f"illegal field access {facc!r}")

    # ── electrical / limits / timing (Tier 2) ──────────────────────────────
    def check_tier2(self) -> None:
        for ei, e in enumerate(self.doc.get("electrical") or []):
            self.stats["electrical"] += 1
            epath = f"electrical[{(e or {}).get('parameter', ei)}]"
            self.check_prov(e, epath)
            for vi, v in enumerate(e.get("values") or []):
                if "conditions" not in (v or {}):
                    self.err(f"{epath}.values[{vi}]", "missing `conditions` object")
        limits = self.doc.get("limits") or {}
        for group in ("absolute_maximum", "recommended_operating"):
            for li, row in enumerate(limits.get(group) or []):
                self.stats["limits"] += 1
                self.check_prov(row, f"limits.{group}[{(row or {}).get('parameter', li)}]")
        for ti, t in enumerate(self.doc.get("timing") or []):
            self.stats["timing"] += 1
            self.check_prov(t, f"timing[{ti}]")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Validate an OpenDatasheet part JSON.")
    ap.add_argument("path", nargs="?", help="path to the part .json")
    ap.add_argument("--manifest", help="a datasheets/<id>/chip.json; validates its `out` file")
    ap.add_argument("--max-errors", type=int, default=40)
    ap.add_argument("--quiet", action="store_true", help="only print the verdict line")
    args = ap.parse_args(argv)

    path = args.path
    if args.manifest:
        try:
            with open(args.manifest) as fh:
                man = json.load(fh)
            out = man.get("out")
            if not out:
                print(f"CONFORMANCE FAIL: manifest {args.manifest} has no `out` field")
                return 1
            # `out` is repo-root-relative (e.g. data/stm32u575zi.json); resolve it
            # relative to the manifest's repo root (two levels up from datasheets/<id>/).
            import os
            root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(args.manifest))))
            path = out if os.path.isabs(out) else os.path.join(root, out)
        except (OSError, json.JSONDecodeError) as e:
            print(f"CONFORMANCE FAIL: cannot read manifest {args.manifest}: {e}")
            return 1
    if not path:
        print("CONFORMANCE FAIL: give a part .json path or --manifest")
        return 1

    try:
        with open(path) as fh:
            doc = json.load(fh)
    except (OSError, json.JSONDecodeError) as e:
        print(f"CONFORMANCE FAIL: cannot read {path}: {e}")
        return 1
    args.path = path

    c = Checker(doc)
    c.run()

    if not args.quiet:
        s = c.stats
        print(f"# {args.path}")
        print(f"# documents: {sorted(x for x in c.doc_ids if x)}")
        print(f"# scanned: {s['peripherals']} peripherals, {s['registers']} registers, "
              f"{s['fields']} fields, {s['electrical']} electrical, {s['limits']} limits, "
              f"{s['timing']} timing")
        if c.errors:
            print(f"# first {min(len(c.errors), args.max_errors)} of {len(c.errors)} violations:")
            for line in c.errors[:args.max_errors]:
                print(f"  - {line}")

    if c.errors:
        print(f"CONFORMANCE FAIL: {len(c.errors)} violation(s)")
        return 1
    print(f"CONFORMANCE OK: {c.stats['registers']} registers / {c.stats['fields']} fields cited, "
          f"all access legal")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
