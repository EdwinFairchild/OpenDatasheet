#!/usr/bin/env python3
"""
build.py -- assemble OpenDatasheet part document(s) from chip modules.

Pipeline (see svd2od.py for the rationale):
  SVD skeleton  +  curated RM overlay  ->  part document with provenance on every leaf.

Each chip is a module in tools/chips/ (e.g. chips/stm32g474.py) that carries the
chip's identity, curated peripheral specs, access fixes, and Tier-2 data, plus a
descriptor (SVD_FILE, SECTIONS_FILE, OUT). This file is generic -- it never holds
chip data. Adding a chip = adding a chips/<id>.py (see tools/ADDING-A-CHIP.md).

Run:
  python3 tools/build.py stm32g474                 # build one chip to its OUT
  python3 tools/build.py stm32g474 stm32h5         # build several
  python3 tools/build.py stm32g474 --curated-only  # skip auto-mode (curated specs only)
  python3 tools/build.py stm32g474 --stdout        # write to stdout instead of OUT

Design choices that keep the data honest:
  * Structure (offsets/sizes/resets/bit positions) comes from the SVD.
  * ACCESS comes from the chip's curated overlay where it names a register/field
    (RM-verified -- especially status/clear regs the SVD mis-types); else the SVD's.
  * ENUMs the SVD lacks are added from the overlay.
  * Every register and field gets a `provenance` {doc, section, rev}. No leaf ships
    without a citation; unresolved ones are reported (chapter-level or TBD).
"""
import importlib
import json
import os
import re
import sys

from svd2od import Svd

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
CHIPS_DIR = os.path.join(THIS_DIR, "chips")
PROJECT_ROOT = os.path.dirname(THIS_DIR)


def section_for(sections, spec, bare):
    """Resolve the RM subsection for a register.

    Order: explicit `spec['section_map'][bare]` (needed where a generic TOC key
    like 'TIMx_' collides across chapters), then `spec['section_keyfn']` (turns
    'MODER' -> 'GPIOx_MODER'; may return one key or a list of candidates), then the
    bare name in the TOC map.
    """
    explicit = spec.get("section_map", {}).get(bare)
    if explicit:
        return explicit
    keyfn = spec.get("section_keyfn")
    cand = []
    if keyfn:
        r = keyfn(bare)
        cand += r if isinstance(r, list) else [r]
    cand.append(bare)
    for key in cand:
        if key in sections:
            return sections[key]["section"]
    return None


class ChipBuild:
    """Builds one chip module into a part document."""

    def __init__(self, chip):
        self.chip = chip
        self.svd = Svd(os.path.join(CHIPS_DIR, chip.SVD_FILE))
        self.sections = json.load(open(os.path.join(CHIPS_DIR, chip.SECTIONS_FILE)))
        self.unmapped = []        # registers with no citation (provenance=TBD)
        self.chapter_only = []    # registers cited only at chapter granularity

    # -- provenance --------------------------------------------------------------
    def stamp(self, section):
        return {"doc": self.chip.DOC_RM, "section": section, "rev": self.chip.RM_REV}

    # -- auto-mode helpers (peripherals with no curated spec) --------------------
    def auto_keyfn(self, per):
        """Generic register-name -> RM-section-key candidate generator. Base prefix
        is the peripheral name with trailing digits stripped (SPI1 -> SPI), unless
        overridden (GPIO -> GPIOx)."""
        base = next((v for k, v in self.chip.AUTO_PREFIX_OVERRIDE.items()
                     if per.startswith(k)), None)
        if base is None and per.endswith("_Common"):
            base = re.match(r"\D+", per).group(0) + "x"   # ADC12_Common -> ADCx
        base = base or re.sub(r"\d+$", "", per)

        def fn(bare):
            cand = [bare, f"{base}_{bare}"]
            for ph in ("x", "y"):                 # RM uses both x and y placeholders
                tail = re.sub(r"\d+$", ph, bare)  # CCR1 -> CCRx
                allp = re.sub(r"\d+", ph, bare)   # OPAMP1_TCMR -> OPAMPx_TCMR
                cand += [f"{base}_{tail}", f"{base}_{allp}", tail, allp]
            return cand
        return fn

    def auto_spec(self, per):
        """Synthetic spec for an uncurated peripheral: SVD structure + generic
        provenance. Access is the SVD's, except RM-verified status/clear fixes
        (ACCESS_FIX + the *ICR/SCR pattern)."""
        fam = re.sub(r"\d+$", "", per)   # ADC1 -> ADC
        reg_fix = {r: {"access": a, "field_access": a}
                   for r, a in self.chip.ACCESS_FIX.get(fam, {}).items()}
        return {
            "svd_name": per,
            "description": self.svd.description(per) or per,
            "rename": (lambda n: n[len(per) + 1:] if n.startswith(per + "_") else n),
            "drop": set(),
            "section_keyfn": self.auto_keyfn(per),
            "registers": reg_fix,
            "_auto_drop_alt": True,   # drop *_Alternate views (duplicate offsets)
            "_clear_pattern": True,   # *ICR/SCR/IFCR -> w1c
            "emit": [{"name": per}],
        }

    # -- the core builder --------------------------------------------------------
    def build_peripheral(self, spec):
        chip = self.chip
        sname = spec["svd_name"]
        regs = self.svd.register_dicts(sname)
        reg_ov = spec.get("registers", {})
        field_ov = spec.get("fields", {})
        only = spec.get("only")
        drop = spec.get("drop", set())

        out_regs = []
        for r in regs:
            bare = spec.get("rename", lambda n: n)(r["name"])
            if only and bare not in only:
                continue
            if bare in drop:
                continue
            if spec.get("_auto_drop_alt") and bare.endswith("_Alternate"):
                continue
            r["name"] = bare

            ro = reg_ov.get(bare, {})
            # Clear-register pattern (auto peripherals): *ICR/SCR/IFCR are
            # write-1-to-clear (RM-verified). Explicit ACCESS_FIX in reg_ov wins.
            if spec.get("_clear_pattern") and not ro and (
                    bare.endswith(chip.CLEAR_SUFFIX) or bare in chip.CLEAR_NAMES):
                ro = {"access": "w1c", "field_access": "w1c"}
            label = spec["emit"][0]["name"] if spec.get("emit") else sname
            section = ro.get("section") or section_for(self.sections, spec, bare)
            if not section:
                # Chapter-level fallback (true, just coarse) before TBD.
                chap = next((c for k, c in chip.CHAPTER_FALLBACK.items()
                             if label.startswith(k)), None)
                if chap:
                    section = chap
                    self.chapter_only.append(f"{label}.{bare}")
                else:
                    self.unmapped.append(f"{label}.{bare}")
                    section = "TBD"
            if "access" in ro:
                r["access"] = ro["access"]
            if "description" in ro:
                r["description"] = ro["description"]
            if "field_access" in ro:        # e.g. timer SR flags all rc_w0/w0c
                for f in r["fields"]:
                    f["access"] = ro["field_access"]

            for f in r["fields"]:
                fov = field_ov.get(bare, {}).get(f["name"])
                if fov:
                    if "access" in fov:
                        f["access"] = fov["access"]
                    if "description" in fov:
                        f["description"] = fov["description"]
                    if "enum" in fov:
                        f["enum"] = fov["enum"]
                f.setdefault("access", r["access"])   # inherit register access (CMSIS)
                f["provenance"] = self.stamp(section)
            r["provenance"] = self.stamp(section)
            out_regs.append(r)

        peripherals = []
        for inst in spec["emit"]:
            # Prefer the instance's OWN base/interrupts from the SVD (DMA2, USART2
            # are real SVD peripherals). Explicit overlay values still win.
            src = inst["name"] if inst["name"] in self.svd.by_name else sname
            p = {
                "name": inst["name"],
                "description": inst.get("description", spec.get("description", "")),
                "base_address": inst.get("base_address") or self.svd.base_address(src),
                "interrupts": inst.get("interrupts", self.svd.interrupts(src)),
                "registers": json.loads(json.dumps(out_regs)),  # deep copy per instance
            }
            for rname, resets in inst.get("reset_overrides", {}).items():
                for r in p["registers"]:
                    if r["name"] == rname:
                        r["reset_value"] = resets
            if "note" in inst:
                p["extensions"] = {"stm32": {"note": inst["note"]}}
            peripherals.append(p)
        return peripherals

    def build(self, emit_all):
        chip = self.chip
        profile_peripherals = []
        covered = set()
        for spec in chip.PERIPHERALS:
            profile_peripherals.extend(self.build_peripheral(spec))
            covered.add(spec["svd_name"])
            covered.update(inst["name"] for inst in spec["emit"])

        if emit_all:
            for per in self.svd.peripheral_names():
                if per in covered or self.svd.registers_el(per) is None:
                    continue
                covered.add(per)
                profile_peripherals.extend(self.build_peripheral(self.auto_spec(per)))

        profile_peripherals.extend(chip.EXTRA_PERIPHERALS)

        return {
            "$schema": "https://opendatasheet.org/schema/v0.1/part.schema.json",
            "spec_version": "0.1",
            "type": "part",
            "conformance": {
                "tiers": chip.TIERS,
                "profiles": ["register-map"],
                "authority": "community-provisional",
            },
            "part": chip.PART | {"documents": chip.DOCUMENTS},
            "pinout": [],
            "electrical": chip.ELECTRICAL,
            "timing": [],
            "limits": chip.LIMITS,
            "sections": [],
            "profiles": {
                "register-map": {"peripherals": profile_peripherals, "memory_map": []}
            },
        }

    def report(self, doc):
        peris = doc["profiles"]["register-map"]["peripherals"]
        nreg = sum(len(p["registers"]) for p in peris)
        precise = nreg - len(self.chapter_only) - len(self.unmapped)
        w = sys.stderr.write
        w(f"[{self.chip.ID}] {len(peris)} peripherals, {nreg} registers.\n")
        w(f"[{self.chip.ID}] provenance: {precise} register-precise, "
          f"{len(self.chapter_only)} chapter-level, {len(self.unmapped)} TBD.\n")
        if self.chapter_only:
            w(f"[{self.chip.ID}] chapter-level only: "
              f"{', '.join(sorted({c.split('.')[0] for c in self.chapter_only}))}\n")
        if self.unmapped:
            by_per = {}
            for u in self.unmapped:
                by_per[u.split('.')[0]] = by_per.get(u.split('.')[0], 0) + 1
            w(f"[{self.chip.ID}] {len(self.unmapped)} registers TBD across "
              f"{len(by_per)} peripherals: "
              f"{', '.join(f'{p}({n})' for p, n in sorted(by_per.items(), key=lambda x: -x[1]))}\n")


def main():
    chip_ids = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    if not chip_ids:
        sys.exit("usage: build.py <chip-id> [<chip-id> ...] [--curated-only] [--stdout]\n"
                 f"available: {', '.join(_available_chips())}")

    for cid in chip_ids:
        try:
            chip = importlib.import_module(f"chips.{cid}")
        except ModuleNotFoundError:
            sys.exit(f"no chip module 'chips/{cid}.py'. available: {', '.join(_available_chips())}")
        b = ChipBuild(chip)
        emit_all = getattr(chip, "EMIT_ALL", True) and "--curated-only" not in flags
        doc = b.build(emit_all)
        if "--stdout" in flags:
            sys.stdout.write(json.dumps(doc, indent=2))
        else:
            out = os.path.join(PROJECT_ROOT, chip.OUT)
            with open(out, "w") as f:
                json.dump(doc, f, indent=2)
            sys.stderr.write(f"[{chip.ID}] -> {chip.OUT}\n")
        b.report(doc)


def _available_chips():
    return sorted(f[:-3] for f in os.listdir(CHIPS_DIR)
                  if f.endswith(".py") and not f.startswith("_"))


if __name__ == "__main__":
    main()
