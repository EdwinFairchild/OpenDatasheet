#!/usr/bin/env python3
"""
rm_inspect.py -- look up a register in the reference manual to VERIFY its access
types and enum values before you hand-curate them in overlay.py.

This is the workhorse for the manual-curation steps. The SVD gives you structure
but lies about access (it can't express W1C/w0c/rc) and is thin on enums; the RM
is the source of truth. This tool jumps straight to a register's RM page so you
don't scroll a 2000-page PDF.

    # Show a register's page, its access-token row(s), and the bit-table text:
    python3 tools/rm_inspect.py <RM.pdf> USART_CR1
    python3 tools/rm_inspect.py <RM.pdf> USART_CR1 --text     # full page text (enums, bit descriptions)

The register name is the RM-TOC key (what make_sections.py produced), e.g.
USART_ICR, RCC_CFGR, GPIOx_MODER, TIMx_SR, ADC_ISR.

Reading the output:
  access tokens  rw=read-write  r=read-only  w=write-only  rc_w1=>w1c  rc_w0=>w0c
                 rc_r=>rc  rs=>rs   (these map to the schema's `access` enum)
  A *uniform* token set (e.g. all rc_w1) -> set that access on every field.
  A *mixed* set (e.g. r + rc_w1) -> set access per field; read the bit descriptions
  (`--text`) to see which bit is which.

Needs `pdftotext`. The printed RM page number equals the PDF page number for the
STM32 RMs (no front-matter offset); adjust `--offset` if your RM differs.
"""
import json
import os
import re
import subprocess
import sys

ACCESS_TOKENS = {"rw", "r", "w", "rc_w1", "rc_w0", "rc_r", "rs", "rt_w1", "rt_w0", "t", "res"}
SCHEMA = {"rw": "read-write", "r": "read-only", "w": "write-only",
          "rc_w1": "w1c", "rc_w0": "w0c", "rc_r": "rc", "rs": "rs"}


def page_map(pdf, toc_pages=72):
    """register-name -> printed page, from the TOC."""
    raw = subprocess.run(["pdftotext", "-layout", "-f", "1", "-l", str(toc_pages), pdf, "-"],
                         capture_output=True, text=True, errors="replace").stdout
    pages = {}
    for ln in raw.splitlines():
        s = re.sub(r"\s+", " ", ln).strip()
        pg = re.search(r"(\d+)\s*$", s)                 # page = last integer on the line
        reg = re.search(r"\(([A-Za-z][A-Za-z0-9_]*)\)", s)  # first "(REGNAME)" token
        if pg and reg and "_" in reg.group(1):          # require an underscore: it's a register
            pages.setdefault(reg.group(1), int(pg.group(1)))
    return pages


def page_text(pdf, page):
    return subprocess.run(["pdftotext", "-layout", "-f", str(page), "-l", str(page + 1), pdf, "-"],
                          capture_output=True, text=True, errors="replace").stdout


def access_rows(text):
    rows = []
    for ln in text.splitlines():
        toks = [t.strip(".").lower() for t in ln.split() if t.strip(".")]
        if toks and all(t in ACCESS_TOKENS for t in toks) and any(t != "res" for t in toks):
            rows.append([t for t in toks if t != "res"])
    return rows


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    pdf, reg = args[0], args[1]
    offset = 0
    for a in sys.argv:
        if a.startswith("--offset"):
            offset = int(a.split("=")[1])
    pages = page_map(pdf)
    pg = pages.get(reg)
    if not pg:
        print(f"'{reg}' not found in TOC. Try the RM-TOC key form (e.g. USART_CR1, ADC_ISR).")
        sys.exit(1)
    pg += offset
    text = page_text(pdf, pg)
    print(f"# {reg}  (RM printed page {pg})")
    rows = access_rows(text)
    flat = sorted({t for row in rows for t in row})
    print(f"access tokens: {flat or '(none found on page)'}")
    print(f"  -> schema access: {[SCHEMA.get(t, t) for t in flat]}")
    if len(flat) == 1:
        print(f"  -> UNIFORM: set every field to '{SCHEMA.get(flat[0], flat[0])}'")
    elif flat:
        print("  -> MIXED: set access per field (use --text to see which bit is which)")
    if "--text" in sys.argv:
        print("\n" + "=" * 70)
        print(text)
