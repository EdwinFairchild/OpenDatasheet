#!/usr/bin/env python3
"""
make_sections.py -- build the register-name -> RM-subsection map from a reference
manual's table of contents.

This is the provenance backbone for a chip: it lets build.py stamp every register
with the exact RM section that documents it. Run it once per new chip.

    python3 tools/make_sections.py <REFERENCE-MANUAL.pdf> [out.json] [--toc-pages N]

Output (default tools/rm_sections.json):
    { "USART_CR1": {"section": "37.8.1", "title": "USART control register 1 ..."}, ... }

How it works: the RM's TOC lists every register at subsection level, e.g.
"37.8.1  USART control register 1 (USART_CR1) ...... 1659". We pull the section
number and the "(REGNAME)" token. Register names in the TOC use generic index
placeholders (GPIOx_MODER, TIMx_CR1, DMA_CCRx) -- build.py's section_keyfn maps a
peripheral's concrete register names onto these keys.

Needs `pdftotext` (poppler-utils). Verify the result with the coverage report from
`build.py --all` (anything unresolved shows up as chapter-level or TBD).
"""
import json
import re
import subprocess
import sys


def build(pdf, toc_pages):
    raw = subprocess.run(
        ["pdftotext", "-layout", "-f", "1", "-l", str(toc_pages), pdf, "-"],
        capture_output=True, text=True, errors="replace").stdout

    # Normalise: drop dot-leaders + trailing page numbers, collapse whitespace.
    lines = []
    for ln in raw.splitlines():
        s = re.sub(r"\.{2,}.*$", "", ln.replace("\xa0", " "))
        s = re.sub(r"\s{2,}", " ", s).strip()
        if s:
            lines.append(s)
    text = "\n".join(lines)

    # An entry is "x.y[.z] <title...>" running until the next section number.
    entry_re = re.compile(
        r"(?m)^(\d+\.\d+(?:\.\d+)?)\s+(.*?)(?=\n\d+\.\d+(?:\.\d+)?\s|\n\d+\s+[A-Z]|\Z)", re.S)
    # A register token: an all-caps name with an underscore, or the GPIOx_/TIMx_ forms.
    reg_re = re.compile(r"\(([A-Z][A-Za-z0-9_]*?_[A-Za-z0-9_x]+|GPIOx_[A-Z]+|TIMx_[A-Z0-9]+)\)")

    out = {}
    for m in entry_re.finditer(text):
        sec = m.group(1)
        body = re.sub(r"\s+", " ", m.group(2)).strip()
        for rm in reg_re.finditer(body):
            out.setdefault(rm.group(1), {"section": sec, "title": body[:90]})
    return out


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    pdf = args[0]
    out_path = args[1] if len(args) > 1 else "tools/rm_sections.json"
    toc = 72
    for a in sys.argv:
        if a.startswith("--toc-pages"):
            toc = int(a.split("=")[1]) if "=" in a else int(sys.argv[sys.argv.index(a) + 1])
    sections = build(pdf, toc)
    json.dump(sections, open(out_path, "w"), indent=1, sort_keys=True)
    print(f"[make_sections] {len(sections)} registers -> {out_path}", file=sys.stderr)
