# svd2opendatasheet: STM32G474RE build

Reproducible pipeline that turns the CMSIS-SVD + RM0440 into the OpenDatasheet
`register-map` profile in `../data/stm32g474re.json`. This is the roadmap's
`svd2opendatasheet` on-ramp (`docs/05-ROADMAP.md`, Phase 2).

Each **chip is a module** in `tools/chips/` (`chips/<id>.py` + `chips/<id>.svd` +
`chips/<id>.sections.json`). `build.py` is generic, it never holds chip data, so
adding a chip is adding a `chips/<id>.py`. STM32G474RE (`chips/stm32g474.py`) is the
worked example. To add your own, see **[ADDING-A-CHIP.md](./ADDING-A-CHIP.md)**.

## Build

```sh
python3 tools/build.py stm32g474                 # build to its OUT (data/stm32g474re.json)
python3 tools/build.py stm32g474 --curated-only  # only the ~30 hand-verified peripherals (skip auto-mode)
python3 tools/build.py stm32g474 --stdout        # write to stdout instead of OUT
python3 tools/build.py stm32g474 stm32h5         # build several chips at once
```

`stm32g474` resolves to `chips/stm32g474.py`; with no chip id, the usage message
lists what's available. The build prints a coverage report to stderr
(register-precise / chapter-level / TBD). The shipped `data/stm32g474re.json` is
wired into the MCP server (`src/lib.ts`, key `STM32G474RE`).

## Deploy (Cloudflare Workers)

Data is embedded in the Worker bundle at deploy time, so it's rebuilt before each
deploy via npm lifecycle hooks (`package.json`):

```
build:data : python3 tools/build.py stm32g474   # rebuild every registered chip
predeploy  : npm run build:data                 # npm runs this automatically before deploy
deploy     : wrangler deploy
```

So the whole flow is just `npm run deploy`: it regenerates the data, then deploys,
so the live data can never drift from source. **When you add a chip**, append it to
the `build:data` script (`... && python3 tools/build.py <id>`) so predeploy rebuilds
it too. Requirements: **Python 3** and a logged-in wrangler (`npx wrangler login`).

> Rebuild without deploying: `npm run build:data`. Deploy a prebuilt bundle without
> rebuilding: `npx wrangler deploy` (skips the predeploy hook).

## Files

| File | Role |
|---|---|
| `svd2od.py` | SVD → structural skeleton (offsets, sizes, resets, bit positions; resolves `derivedFrom`). Generic. |
| `build.py` | Generic builder: merges SVD + a chip module, stamps `provenance` on every leaf, writes the part document. Takes chip ids. |
| `chips/<id>.py` | A chip: identity, curated peripheral specs, access fixes, Tier-2 data, and a descriptor (SVD/sections/OUT). **Edit this to raise fidelity.** |
| `chips/<id>.svd` | That chip's CMSIS-SVD (structural source). |
| `chips/<id>.sections.json` | register-name → RM subsection (provenance backbone), from `make_sections.py`. |
| `make_sections.py` | Generates `chips/<id>.sections.json` from a reference-manual PDF's TOC. Run once per chip. |
| `rm_inspect.py` | Looks up a register in the RM PDF and prints its access-token row + page text: verify access/enums while curating. |

> **Encoding a different chip from scratch?** See **[ADDING-A-CHIP.md](./ADDING-A-CHIP.md)**;
> the full walkthrough: inputs to gather, which scripts to run, what to curate by
> hand, how to verify access/enums against the RM, and how to deploy.

## Why an overlay (not just the SVD)

The ST SVD has **no `modifiedWriteValues`/`readAction`**, so it cannot express
W1C/rc/rs semantics, and its enums are sparse. Shipping it raw would mark a
status flag as plain read-write, the silent, expensive error the mission warns
about. The overlay carries the RM-verified facts, e.g.:

- `USART_ICR.*` = **w1c** (write 1 to clear the matching ISR flag); ISR is read-only.
- `TIMx_SR.*` = **w0c** (rc_w0: cleared by writing 0).
- `DMA_IFCR`, `DMAMUX_CFR/RGCFR` = **w1c**.
- `RCC_CFGR.SWS` = read-only; clock-switch / prescaler / parity / stop-bit enums, etc.

## Coverage

**Tier 1: `register-map`** (`--all`): **83 peripherals, 1475 registers, 0 TBD.**
Provenance: ~1215 register-precise + 260 chapter-level (RM0440 Rev 8).
- **Curated** (verified access, RM enums, register-precise cites): all GPIO (A–G),
  RCC, USART1/2/3, UART4/5, LPUART1, DMA1/2, DMAMUX, DBGMCU, all timers
  (TIM1/8/20 adv, TIM2/3/4/5 GP, TIM15/16/17, TIM6/7 basic).
- **Auto** (SVD structure + access/enums as-is, generic provenance): ADC, DAC, SPI,
  I2C, FDCAN, RTC, SAI, QUADSPI, FMAC, CORDIC, CRC, RNG, PWR, FLASH, SYSCFG, EXTI,
  COMP, OPAMP, LPTIM, CRS, IWDG, WWDG, VREFBUF, TAMP, etc.
- **Chapter-level provenance only** (per-register RM subsections not in the parsed
  TOC): HRTIM (exotic register naming), FMC, USB, UCPD. Structurally complete; cited
  to the correct RM chapter. Add a `section_map` to `overlay.py` to make them precise.

**Tier 2: electrical/limits** (cited to DS12288 Rev 6, `stm32g474cb.pdf`): a focused
slice: absolute-max (VDD/VIN/currents/temps), recommended operating (VDD/VBAT/fHCLK/TA),
and electrical (max HCLK, IDD Run). Values the datasheet doesn't state are `null`
(surfaced as N/A, never guessed). Conditions are attached to every electrical value.

## Not yet covered

- **ITM / DWT** core-debug registers: not in the SVD or RM0440. Deferred to dedicated
  ARM-core JSONs once a citable source (PM0214 or the Armv7-M ARM) is on hand;
  `build.py` already supports them via `EXTRA_PERIPHERALS`. DBGMCU (RM0440-cited) is present.
- **Register-precise provenance for HRTIM/FMC/USB/UCPD**: currently chapter-level.
- **Verified W1C access on auto peripherals**: auto peripherals carry the SVD's
  access as-is (mostly correct, but status/clear W1C/rc bits aren't RM-verified the
  way the curated set is). Promote a peripheral by adding a curated spec.
- **Tier 2 breadth / timing**: only a hero slice so far; more electrical tables and
  WaveDrom timing diagrams can be added to `overlay.py` (`ELECTRICAL`/`LIMITS`).
