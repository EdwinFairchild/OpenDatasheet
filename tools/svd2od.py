#!/usr/bin/env python3
"""
svd2od  --  CMSIS-SVD -> OpenDatasheet `register-map` profile skeleton.

This is the cheap on-ramp the roadmap (05) calls `svd2opendatasheet`. It maps
SVD <peripheral>/<register>/<field>/<enumeratedValue> 1:1 into the register-map
profile (schema 03, section 4.1).

What it CAN do faithfully from the SVD:
  - peripherals (base_address, interrupts), registers (offset, size, reset_value),
    fields (bit_offset, bit_width), and any enumeratedValues present.
  - resolve `derivedFrom` so e.g. GPIOD inherits GPIOC's registers.

What it CANNOT get from the ST SVD (must come from RM0440, supplied via overlay):
  - correct field-level ACCESS for status/clear registers (W1C/rc/rs/read-only).
    The ST SVD has no <modifiedWriteValues>/<readAction>, so a status flag looks
    like plain read-write -- exactly the silent-error class the mission warns about.
  - per-bit ENUM semantics for most fields (the SVD is sparse here).
  - provenance section numbers.

So the pipeline is: this script emits a structural skeleton; `overlay.py`
(curated from the RM) supplies access, enums, and provenance; `build.py` merges
them and stamps provenance on every leaf. No fact ships without a citation.
"""
import re
import xml.etree.ElementTree as ET

SVD_ACCESS = {
    "read-write": "read-write",
    "read-only": "read-only",
    "write-only": "write-only",
    "writeOnce": "writeOnce",
    "read-writeOnce": "read-writeOnce",
}


def clean(s):
    """SVD descriptions carry line-wrap runs of whitespace; collapse them."""
    if s is None:
        return None
    return re.sub(r"\s+", " ", s).strip()


def hexstr(node, tag, width=None):
    v = node.findtext(tag)
    if v is None:
        return None
    v = v.strip()
    n = int(v, 0)
    if width:
        return "0x" + format(n, "0{}X".format(width))
    return "0x" + format(n, "X")


class Svd:
    """Loads an SVD and resolves derivedFrom at the peripheral level."""

    def __init__(self, path):
        self.root = ET.parse(path).getroot()
        self.by_name = {p.findtext("name"): p for p in self.root.iter("peripheral")}

    def registers_el(self, pname):
        """Return the <registers> element for a peripheral, following derivedFrom."""
        p = self.by_name[pname]
        seen = set()
        while p is not None:
            regs = p.find("registers")
            if regs is not None:
                return regs
            df = p.get("derivedFrom")
            if not df or df in seen:
                return None
            seen.add(df)
            p = self.by_name.get(df)
        return None

    def base_address(self, pname):
        return hexstr(self.by_name[pname], "baseAddress")

    def interrupts(self, pname):
        out = []
        for it in self.by_name[pname].findall("interrupt"):
            out.append({"name": it.findtext("name"), "value": int(it.findtext("value"))})
        return out

    def field_dicts(self, reg_el):
        out = []
        fields_el = reg_el.find("fields")
        if fields_el is None:
            return out
        for f in fields_el.findall("field"):
            name = f.findtext("name")
            bit_off = f.findtext("bitOffset")
            bit_w = f.findtext("bitWidth")
            if bit_off is None:
                # bitRange form: [hi:lo]
                br = f.findtext("bitRange")
                if br:
                    hi, lo = re.findall(r"\d+", br)
                    bit_off, bit_w = int(lo), int(hi) - int(lo) + 1
            d = {
                "name": name,
                "description": clean(f.findtext("description")),
                "bit_offset": int(bit_off),
                "bit_width": int(bit_w),
            }
            acc = f.findtext("access")
            if acc in SVD_ACCESS:
                d["access"] = SVD_ACCESS[acc]
            enums = []
            ev = f.find("enumeratedValues")
            if ev is not None:
                for e in ev.findall("enumeratedValue"):
                    val = e.findtext("value")
                    if val is None:
                        continue
                    enums.append({
                        "value": int(val, 0),
                        "name": e.findtext("name"),
                        "description": clean(e.findtext("description")),
                    })
            if enums:
                d["enum"] = enums
            out.append(d)
        # SVD orders high->low; present low->high for readability
        out.sort(key=lambda x: x["bit_offset"])
        return out

    def register_dicts(self, pname):
        regs_el = self.registers_el(pname)
        if regs_el is None:
            return []
        out = []
        for r in regs_el.findall("register"):
            size = r.findtext("size")
            size_bits = int(size, 0) if size else 32
            d = {
                "name": r.findtext("name"),
                "description": clean(r.findtext("description")),
                "offset": hexstr(r, "addressOffset"),
                "size": size_bits,
                "reset_value": hexstr(r, "resetValue", width=size_bits // 4),
                "access": SVD_ACCESS.get(r.findtext("access"), "read-write"),
                "fields": self.field_dicts(r),
            }
            out.append(d)
        return out


if __name__ == "__main__":
    import json
    import sys
    svd = Svd(sys.argv[1])
    pname = sys.argv[2] if len(sys.argv) > 2 else "GPIOA"
    print(json.dumps({
        "name": pname,
        "base_address": svd.base_address(pname),
        "interrupts": svd.interrupts(pname),
        "registers": svd.register_dicts(pname),
    }, indent=2))
