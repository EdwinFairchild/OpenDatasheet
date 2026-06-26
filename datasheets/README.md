# `datasheets/` — source inputs for chip encoding

This folder holds the **raw source documents** the `encode-datasheet` workflow
consumes to produce an OpenDatasheet part JSON. One subfolder per chip, named by
its lowercase chip id (matching `tools/chips/<id>.py`):

```
datasheets/
  <id>/
    chip.json          # manifest: MPN, family, docs, revisions, toc_pages, out path
    <CHIP>.svd         # CMSIS-SVD (structure) — from the vendor / STM32CubeCLT / stm32-rs
    <RM>.pdf           # reference manual (register sections + verified access)
    <DS>.pdf           # datasheet (Tier 2 electrical / limits)  [optional]
```

`chip.json` is the single source of truth the workflow reads — it tells the
agents the MPN, document ids/revisions, the SVD filename, the `--toc-pages` value
for `make_sections.py`, and where the built part JSON should land (`out`).

## Adding a chip

1. `mkdir datasheets/<id>` and drop in the SVD + reference-manual PDF (+ datasheet
   PDF for Tier 2).
2. Write `chip.json` (copy `stm32u575/chip.json` and edit the fields). Find the
   right `toc_pages` by checking how far the RM's "Contents" runs.
3. Run the workflow: `va workflow run encode-datasheet --var chip=<id>` from the
   repo root (see `workflows/encode-datasheet.json`).

## Current inputs

- **`stm32u575/`** — STM32U575ZI (Cortex-M33). SVD from STM32CubeCLT, RM0456
  Rev 6, DS13737 Rev 10. The first end-to-end target of the workflow.

> The source SVD + PDFs are large and **git-ignored** (see `.gitignore`) — they're
> local build inputs, not committed artifacts. Re-copy the SVD from STM32CubeCLT /
> the vendor and re-download the PDFs from ST if missing (URLs are in each
> `chip.json`). Only `chip.json` + this README are committed here; the build's
> working SVD copy is committed at `tools/chips/<id>.svd`.
