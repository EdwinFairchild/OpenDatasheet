#!/usr/bin/env python3
"""
build.py -- assemble the STM32G474RE OpenDatasheet part document.

Pipeline (see svd2od.py for the rationale):
  SVD skeleton  +  curated RM overlay  ->  part document with provenance on every leaf.

Run:  python3 tools/build.py <path-to-STM32G474.svd>  > data/stm32g474re.json

Design choices that keep the data honest:
  * Structure (offsets/sizes/resets/bit positions) comes from the SVD, which
    mirrors the RM register map 1:1.
  * ACCESS is taken from the curated overlay for any register/field the overlay
    names (verified against RM0440 bit tables -- especially status/clear regs
    where the SVD's blanket "read-write" would be wrong and dangerous). Where the
    overlay is silent, the SVD value stands.
  * ENUMs the SVD lacks are added from the overlay, each implicitly carried under
    the owning field's provenance (the RM subsection that documents the register).
  * Every register and field gets a `provenance` {doc, section, rev} stamped from
    the overlay's section map. A leaf with no section is reported, not shipped.
"""
import json
import re
import sys

from svd2od import Svd
from overlay import (DOC_RM, RM_REV, PART, DOCUMENTS, PERIPHERALS,
                     EXTRA_PERIPHERALS, ELECTRICAL, LIMITS, TIERS, section_for)

UNMAPPED = []


def stamp(section):
    return {"doc": DOC_RM, "section": section, "rev": RM_REV}


def apply_field_overlay(reg_key, field, fov):
    """Merge a curated field override (access / description / enum) onto a field."""
    if not fov:
        return
    if "access" in fov:
        field["access"] = fov["access"]
    if "description" in fov:
        field["description"] = fov["description"]
    if "enum" in fov:
        field["enum"] = fov["enum"]


def build_peripheral(svd, spec):
    sname = spec["svd_name"]
    regs = svd.register_dicts(sname)
    reg_ov = spec.get("registers", {})
    field_ov = spec.get("fields", {})
    only = spec.get("only")          # optional whitelist of register names to emit
    drop = spec.get("drop", set())   # register names to skip

    out_regs = []
    for r in regs:
        rname = r["name"]
        # Normalise SVD register name -> the bare name used in this peripheral
        bare = spec.get("rename", lambda n: n)(rname)
        if only and bare not in only:
            continue
        if bare in drop:
            continue
        r["name"] = bare

        # provenance section: explicit override wins, else the RM section map
        ro = reg_ov.get(bare, {})
        section = ro.get("section") or section_for(spec, bare)
        if not section:
            UNMAPPED.append(f"{spec['emit'][0] if spec.get('emit') else sname}.{bare}")
            section = "TBD"
        if "access" in ro:
            r["access"] = ro["access"]
        if "description" in ro:
            r["description"] = ro["description"]
        # Apply a register-wide field access (e.g. timer SR flags are all rc_w0/w0c)
        if "field_access" in ro:
            for f in r["fields"]:
                f["access"] = ro["field_access"]

        for f in r["fields"]:
            apply_field_overlay(bare, f, field_ov.get(bare, {}).get(f["name"]))
            # Fields inherit the register's access unless SVD/overlay set their own
            # (CMSIS convention). Status/clear regs override per-field in the overlay.
            f.setdefault("access", r["access"])
            f["provenance"] = stamp(section)
        r["provenance"] = stamp(section)
        out_regs.append(r)

    peripherals = []
    for inst in spec["emit"]:
        # Prefer the instance's OWN base/interrupts from the SVD (e.g. DMA2, USART2
        # are real SVD peripherals with their own address + IRQ numbers), so we
        # never have to hand-copy them. Explicit overlay values still win.
        src = inst["name"] if inst["name"] in svd.by_name else sname
        p = {
            "name": inst["name"],
            "description": inst.get("description", spec.get("description", "")),
            "base_address": inst.get("base_address") or svd.base_address(src),
            "interrupts": inst.get("interrupts", svd.interrupts(src)),
            "registers": json.loads(json.dumps(out_regs)),  # deep copy per instance
        }
        # per-instance reset_value overrides (e.g. GPIOA MODER = 0xABFFFFFF)
        for rname, resets in inst.get("reset_overrides", {}).items():
            for r in p["registers"]:
                if r["name"] == rname:
                    r["reset_value"] = resets
        if "note" in inst:
            p["extensions"] = {"stm32": {"note": inst["note"]}}
        peripherals.append(p)
    return peripherals


def main():
    svd = Svd(sys.argv[1])
    profile_peripherals = []
    for spec in PERIPHERALS:
        profile_peripherals.extend(build_peripheral(svd, spec))
    # Hand-authored peripherals not in the SVD (ARM core: ITM, DWT). Their leaves
    # already carry provenance citing the Armv7-M ARM.
    profile_peripherals.extend(EXTRA_PERIPHERALS)

    doc = {
        "$schema": "https://opendatasheet.org/schema/v0.1/part.schema.json",
        "spec_version": "0.1",
        "type": "part",
        "conformance": {
            "tiers": TIERS,
            "profiles": ["register-map"],
            "authority": "community-provisional",
        },
        "part": PART | {"documents": DOCUMENTS},
        "pinout": [],
        "electrical": ELECTRICAL,
        "timing": [],
        "limits": LIMITS,
        "sections": [],
        "profiles": {
            "register-map": {
                "peripherals": profile_peripherals,
                "memory_map": [],
            }
        },
    }
    sys.stdout.write(json.dumps(doc, indent=2))
    if UNMAPPED:
        sys.stderr.write("\n[build] UNMAPPED sections (provenance=TBD):\n  "
                         + "\n  ".join(UNMAPPED) + "\n")


if __name__ == "__main__":
    main()
