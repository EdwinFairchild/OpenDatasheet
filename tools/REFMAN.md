# Adding a reference manual to the refman service

Repeat these steps per PDF. Worker code never changes for a new doc — data goes
to D1, so **no deploy is needed** (deploy only when `src/` changes).

**Scope:** this is only the prose side (`refman` search/read/toc). It needs no
SVD and no chip JSON. A brand-new *chip* additionally needs its part document
(SVD + RM → `data/<mpn>.json` + deploy) — see `tools/ADDING-A-CHIP.md`. The two
pipelines are linked only by the doc id (`RM0456`) that the part's `documents[]`
and provenance cite.

In practice: onboarding a new *family* = both pipelines (part JSON + this RM
ingest). Every further chip of the same family = part JSON only — the RM is
per-family and is already in D1.

Prereqs (once per machine): `pip3 install pypdf`, `sudo apt install poppler-utils`,
wrangler logged in. One-time infra (already done): `wrangler d1 create refman`,
binding in `wrangler.toml`, `schema/refman.sql` applied `--local` and `--remote`.

## Steps

**1. Get the PDF.** Download from the vendor, drop it under `datasheets/<family>/`
(PDFs there are git-ignored). Note the doc id and revision from the cover page
(e.g. `RM0440`, rev 8) — use the same id the part JSONs cite in `documents[]`.

**2. Allowlist it** (licensing gate — the CLI refuses unlisted docs). Add to
`tools/refman_allowlist.json`:

```json
"RM0440": { "vendor_pdf_url": "https://www.st.com/...pdf", "note": "STM32G4 RM" }
```

**3. Ingest** (offline, ~5–10 min for a 3000-page RM; one line, paste-safe):

```bash
python3 tools/refman_ingest.py datasheets/stm32g4/RM0440.pdf --doc RM0440 --rev 8 --title "STM32G4 series advanced Arm-based 32-bit MCUs reference manual"
```

Outputs land in `build/refman/` (git-ignored). Sanity: it prints the section
count — expect thousands; a warning under 500 means the PDF outline is broken.

**4. Import + smoke-test locally.** Don't run the import while a dev server is
up — they share the local DB; import first, then test. The smoke script starts
(and stops) its own `wrangler dev`:

```bash
npx wrangler d1 execute refman --file build/refman/RM0440.import.sql --local
python3 tools/refman_smoke.py RM0440 --q RCC_CR
```

`--q` is any register/peripheral token from that manual; its register section
should come back as the top hit. Omit `--q` for a generic content check.

**5. Import to production** (takes seconds; server-side ingest):

```bash
npx wrangler d1 execute refman --file build/refman/RM0440.import.sql --remote -y
```

**6. Verify prod** (same script, pointed at the worker):

```bash
python3 tools/refman_smoke.py RM0440 --q RCC_CR --origin https://opendatasheet-mcp.opendatasheet.workers.dev
```

That's it. The harness `refman` tool discovers the doc automatically (doc ids
are data), and `datasheet` provenance citations `{doc, section}` for it resolve
immediately.

## Updating a doc to a new revision

Same steps with the new PDF and `--rev`. The import starts with per-doc
`DELETE`s, so re-importing replaces the old revision cleanly. Harness caches key
by `{doc}@{rev}`, so clients pick up the new revision on their next index hit.
