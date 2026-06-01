# svd2opendatasheet — STM32G474RE build

Reproducible pipeline that turns the CMSIS-SVD + RM0440 into the OpenDatasheet
`register-map` profile in `../data/stm32g474re.json`. This is the roadmap's
`svd2opendatasheet` on-ramp (`docs/05-ROADMAP.md`, Phase 2).

## Build

```sh
python3 tools/build.py /path/to/STM32G474.svd > data/stm32g474re.json
```

Then it's already wired into the MCP server (`src/lib.ts`, key `STM32G474RE`).

## Files

| File | Role |
|---|---|
| `svd2od.py` | SVD → structural skeleton (offsets, sizes, resets, bit positions; resolves `derivedFrom`). |
| `overlay.py` | Curated **RM0440 Rev 8** data: verified field access, enums the SVD omits, register→section map. **Edit this to raise fidelity.** |
| `build.py` | Merges the two, stamps `provenance` on every leaf, assembles the part document. |
| `rm_sections.json` | register-name → RM subsection, parsed from the RM table of contents (provenance backbone). |

## Why an overlay (not just the SVD)

The ST SVD has **no `modifiedWriteValues`/`readAction`**, so it cannot express
W1C/rc/rs semantics, and its enums are sparse. Shipping it raw would mark a
status flag as plain read-write — the silent, expensive error the mission warns
about. The overlay carries the RM-verified facts, e.g.:

- `USART_ICR.*` = **w1c** (write 1 to clear the matching ISR flag) — ISR is read-only.
- `TIMx_SR.*` = **w0c** (rc_w0: cleared by writing 0).
- `DMA_IFCR`, `DMAMUX_CFR/RGCFR` = **w1c**.
- `RCC_CFGR.SWS` = read-only; clock-switch / prescaler / parity / stop-bit enums, etc.

## Coverage

**Tier 1 — `register-map`** (cited to RM0440 Rev 8): 17 peripherals, 288 registers.
GPIOA/B/C (A,B carry real boot/SWD resets; C represents C–G), RCC, USART1/2/3,
UART4/5, LPUART1, DMA1/2, DMAMUX, DBGMCU, TIM1 (adv), TIM2 (GP), TIM6 (basic).
Identical-layout siblings (GPIOD–G, TIM3/4/5/7/8/20) are noted, not duplicated.

**Tier 2 — electrical/limits** (cited to DS12288 Rev 6, `stm32g474cb.pdf`): a focused
slice — absolute-max (VDD/VIN/currents/temps), recommended operating (VDD/VBAT/fHCLK/TA),
and electrical (max HCLK, IDD Run). Values the datasheet doesn't state are `null`
(surfaced as N/A, never guessed). Conditions are attached to every electrical value.

## Not yet covered

- **ITM / DWT** core-debug registers: not in the SVD or RM0440. Deferred to dedicated
  ARM-core JSONs once a citable source (PM0214 or the Armv7-M ARM) is on hand;
  `build.py` already supports them via `EXTRA_PERIPHERALS`. DBGMCU (RM0440-cited) is present.
- **Tier 2 breadth / timing**: only a hero slice so far; more electrical tables and
  WaveDrom timing diagrams can be added to `overlay.py` (`ELECTRICAL`/`LIMITS`).
