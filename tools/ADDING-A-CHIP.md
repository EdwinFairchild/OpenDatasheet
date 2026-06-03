# Adding a new chip, from scratch

This walks you from "I have a part I want to encode" to a deployed, queryable
OpenDatasheet part document, using the same pipeline that produced `STM32G474RE`.

It assumes nothing about the part except that it has a CMSIS-SVD and a reference
manual. Read `../README.md` (the project) and `README.md` (this `tools/` folder)
first if you haven't.

---

## How a chip is structured

The tooling is natively multi-chip. A chip is **one module** plus two data files:

```
tools/
├── build.py                 generic builder (never holds chip data)
├── svd2od.py                generic SVD reader
├── make_sections.py         RM TOC -> sections map (run once per chip)
├── rm_inspect.py            verify access/enums against the RM PDF
└── chips/
    ├── stm32g474.py         <- a chip: identity + curated specs + access fixes + Tier-2
    ├── stm32g474.svd        <- its CMSIS-SVD
    └── stm32g474.sections.json   <- its register -> RM-section map
```

`build.py stm32g474` imports `chips/stm32g474.py`, reads the SVD + sections it
names, and writes the part to the `OUT` path it declares. **Adding a chip = adding
a `chips/<id>.py` (+ its `.svd` and `.sections.json`).** You never touch `build.py`
or `svd2od.py`.

---

## What you're producing, and the three fidelity tiers

One JSON file (`data/<mpn>.json`) with a `register-map` profile and, optionally,
Tier-2 electrical/limits. Every value carries a `provenance` citation. Most of the
chip lands in tiers 1-2 automatically:

| Tier | How | Access | Enums | Provenance |
|---|---|---|---|---|
| **Auto** | `build.py <id>` reads the SVD for every peripheral | SVD's (W1C **not** expressed) | SVD's (sparse) | register-precise where the section map resolves, else chapter-level |
| **Access-fixed** | `ACCESS_FIX` + the `*ICR/SCR` rule (in your chip module) | **RM-verified** W1C/w0c/rc on status/clear regs | n/a | n/a |
| **Curated** | a hand-written spec in `PERIPHERALS` (your chip module) | RM-verified everywhere | RM enums added | register-precise |

You decide how far up the tiers each peripheral goes. A useful target: whole chip
auto + access-fixed, then curate the handful of peripherals people actually program
against (clocks, GPIO, the serial/timer blocks).

---

## Inputs to gather

1. **CMSIS-SVD** for the exact part: structure (offsets, sizes, resets, fields,
   bit positions, some enums). From the vendor, `cmsis-svd`, or `stm32-rs` (the
   stm32-rs patched SVDs are higher quality, they *do* encode some W1C).
2. **Reference manual PDF**: source of truth for provenance sections, verified
   access (W1C/rc), and the enum meanings the SVD omits.
3. **Datasheet PDF** (optional, for Tier 2): electrical limits, currents, clock
   specs. *Not* auto-extracted (vendor tables don't generalize); hand-curated.

You need `pdftotext` (poppler-utils), Python 3, and Node (for the server).

---

## Step by step

Throughout, `<id>` is your chip's short id (e.g. `stm32h563`).

### 1. Create the chip module + drop in the SVD

Copy the worked example and replace its data as you go:

```sh
cp tools/chips/stm32g474.py tools/chips/<id>.py
cp /path/to/MYCHIP.svd      tools/chips/<id>.svd
```

Sanity-check the SVD parses and see one peripheral's raw skeleton (no overlay):

```sh
python3 tools/svd2od.py tools/chips/<id>.svd RCC | head -40
```

### 2. Generate the provenance section map

```sh
python3 tools/make_sections.py /path/to/reference-manual.pdf tools/chips/<id>.sections.json
# -> "[make_sections] 523 registers -> tools/chips/<id>.sections.json"
```

If the RM's TOC is longer than ~72 pages, pass `--toc-pages 90`. Spot-check it:

```sh
python3 -c "import json;d=json.load(open('tools/chips/<id>.sections.json'));print([k for k in d if 'RCC' in k][:8])"
```

### 3. Set the descriptor + identity in `chips/<id>.py`

The top of the module:

```python
ID = "<id>"
SVD_FILE = "<id>.svd"                 # in tools/chips/
SECTIONS_FILE = "<id>.sections.json"  # in tools/chips/
OUT = "data/<mpn>.json"               # relative to project root
EMIT_ALL = True                       # emit every SVD peripheral (auto-mode)

DOC_RM = "RM0xxx"; RM_REV = "N"
PART = {"mpn": "...", "manufacturer": "...", "family": "...", "revision": "...",
        "lifecycle": "active", "packages": ["..."]}
DOCUMENTS = [{"id": "RM0xxx", "kind": "reference-manual", "rev": "N", "url": "..."}, ...]
```

Every `provenance.doc` must match a `DOCUMENTS[].id`. Then strip the curated
`PERIPHERALS`/`ACCESS_FIX`/`ELECTRICAL` down to `[]`/`{}` to start clean, or keep
the STM32 ones if your part is STM32 and reuse what fits.

### 4. First full build, and read the coverage report

```sh
python3 tools/build.py <id>
```

stderr prints the report you'll iterate against:

```
[<id>] 83 peripherals, 1475 registers.
[<id>] provenance: 1215 register-precise, 260 chapter-level, 0 TBD.
[<id>] chapter-level only: HRTIM, FMC, USB, ...
```

You now have a complete, structurally-correct file at `OUT`. The rest is raising
fidelity. (`--stdout` prints instead of writing; `--curated-only` skips auto-mode.)

### 5. Close provenance gaps (drive `TBD` → 0)

For each peripheral reported **TBD** or **chapter-level**, the generic resolver
couldn't find its RM section key. Fixes, cheapest first (all in your chip module):

- **`AUTO_PREFIX_OVERRIDE`**: when the RM uses an index placeholder different from
  the SVD name. Default base is "strip trailing digits" (`SPI1`→`SPI`); add an entry
  when the RM key differs, e.g. `"GPIO": "GPIOx"`, `"SPI": "SPIx"`.
- **`CHAPTER_FALLBACK`**: for peripherals whose per-register subsections aren't in
  the TOC at all. Maps a name prefix to a chapter number so every register still
  gets an honest (coarse) citation: `{"HRTIM": "27", "FMC": "19"}`.
- **A curated spec with `section_map`**: when one generic TOC key collides across
  chapters (classic case: timers, `TIMx_CR1` appears in the advanced, GP, and basic
  timer chapters). The `TIM_ADV`/`TIM_GP`/`TIM_BASIC` specs pin registers to explicit
  `28.6.x` / `29.5.x` / `31.4.x` sections.

Rebuild and watch the report shrink.

### 6. Verify and fix access on status/clear registers (the important one)

The SVD **cannot express W1C/w0c/rc**, so it mis-types every clear/status register
(it'll call `EXTI_PR1` read-write when writing 1 clears it, a silent, bad bug). Use
`rm_inspect.py` to read the RM's own access row:

```sh
python3 tools/rm_inspect.py /path/to/reference-manual.pdf ADC_ISR
#  access tokens: ['rc_w1']  -> schema access: ['w1c']  -> UNIFORM: set every field to 'w1c'
```

Token → schema: `rw`=read-write, `r`=read-only, `w`=write-only, `rc_w1`→**w1c**,
`rc_w0`→**w0c**, `rc_r`→**rc**, `rs`→**rs**. Two conventions:
- A clear register (`*ICR`, `SCR`, `IFCR`) shows `w` in the RM but means
  *write-1-to-clear* → encode as **w1c**. The `CLEAR_SUFFIX`/`CLEAR_NAMES` rule does
  this automatically for auto peripherals.
- If a peripheral has a *separate* clear register (`ICR`), its status register
  (`ISR`) is **read-only**; if not, the status register is the clear register
  (`rc_w1` → w1c).

Encode the verified results in your chip module:
- The `*ICR/SCR/IFCR → w1c` pattern is automatic for auto peripherals.
- For in-place clear flag registers and read-only status regs the pattern misses,
  add to **`ACCESS_FIX`** (keyed by family = peripheral name minus trailing digits):
  ```python
  ACCESS_FIX = {
      "ADC": {"ISR": "w1c"}, "EXTI": {"PR1": "w1c", "PR2": "w1c"},
      "WWDG": {"SR": "w0c"}, "I2C": {"ISR": "read-only"},
  }
  ```
- For a register the RM shows as **MIXED** (e.g. `r` + `rc_w1`): don't blanket it;
  leave the SVD's per-field access, or curate the peripheral and set access per field.

### 7. Curate a "hero" peripheral (verified access + RM enums)

For the peripherals people program, write a spec and add it to `PERIPHERALS`:

```python
RCC = {
    "svd_name": "RCC",                       # which SVD peripheral to read
    "description": "Reset and clock control",
    "rename": strip_prefix("RCC"),           # SVD "RCC_CR" -> register name "CR"  (optional)
    "section_keyfn": lambda b: f"RCC_{b}",   # register name -> sections key   (optional)
    # "section_map": {"CR1": "28.6.1", ...}, # explicit per-register sections (wins over keyfn)
    "registers": {                           # per-register overrides (optional)
        "ICR": {"access": "w1c", "field_access": "w1c", "description": "..."},
    },
    "fields": {                              # per-field enums/access/descriptions (optional)
        "CFGR": {
            "SW": {"enum": [{"value": 1, "name": "HSI16", "description": "..."}, ...],
                   "description": "System clock switch"},
            "SWS": {"access": "read-only"},
        },
    },
    "emit": [{"name": "RCC"}],               # one entry per instance; base/IRQ auto-filled from SVD
}
```

`emit` entry options: `name` (required) + optional `base_address`, `interrupts`,
`description`, `reset_overrides` (per-instance reset values, see `GPIO`), `note`.
Spec options also include `drop` (skip register names) and `only` (whitelist).

Find enum values with `rm_inspect.py <RM> RCC_CFGR --text`: it dumps the page,
including the `00: ... 01: ...` bit descriptions. Verify, then encode. The curated
`GPIO`, `RCC`, `USART`, `TIM_*` specs in `chips/stm32g474.py` are worked examples.

### 8. Add Tier 2 electrical/limits (optional)

Hand-curate the datasheet into `LIMITS` and `ELECTRICAL`. Every electrical value
needs a `conditions` object (`{}` if unconditional) and `provenance` citing the
datasheet; use `null` for a min/typ/max the datasheet doesn't state (surfaces as
N/A, never guessed). Set `TIERS = [1, 2]`.

### 9. Validate

```sh
python3 tools/build.py <id>     # aim for 0 TBD
npx tsc --noEmit                # types still compile (after step 10)
```

Quick conformance check (every leaf cited, access values legal):

```sh
node -e '
const d=require("./data/<mpn>.json"), A=new Set(["read-write","read-only","write-only","read-writeOnce","writeOnce","w1c","w0c","rs","rc"]);
const ids=new Set(d.part.documents.map(x=>x.id)); let e=0;
for(const p of d.profiles["register-map"].peripherals)for(const r of p.registers){
  if(!r.provenance||!ids.has(r.provenance.doc)||!A.has(r.access))e++;
  for(const f of r.fields)if(!f.provenance||!A.has(f.access))e++;}
console.log("conformance errors:",e);'
```

### 10. Register in the server, rebuild-on-deploy, and ship

```ts
// src/lib.ts
import mychip from "../data/<mpn>.json";
const PARTS = { /* ... */, "MYCHIP-MPN": mychip as Part };
```

Append your chip to the `build:data` script in `package.json` so the predeploy hook
rebuilds it too:

```json
"build:data": "python3 tools/build.py stm32g474 <id>",
```

Then:

```sh
npm run deploy     # rebuilds every chip, then ships
```

---

## Reference: chip-module contract

`build.py` reads these names from `chips/<id>.py`:

| Name | Type | Purpose |
|---|---|---|
| `ID` | str | chip id (matches the filename) |
| `SVD_FILE`, `SECTIONS_FILE` | str | filenames in `tools/chips/` |
| `OUT` | str | output path, relative to project root |
| `EMIT_ALL` | bool | auto-emit every SVD peripheral (else curated only) |
| `DOC_RM`, `RM_REV` | str | reference-manual id + revision for `provenance` |
| `PART`, `DOCUMENTS` | dict/list | identity + declared documents |
| `PERIPHERALS` | list | curated peripheral specs |
| `EXTRA_PERIPHERALS` | list | hand-authored peripherals not in the SVD (e.g. ARM core) |
| `ELECTRICAL`, `LIMITS`, `TIERS` | list/dict/list | Tier-2 core blocks |
| `AUTO_PREFIX_OVERRIDE`, `CHAPTER_FALLBACK` | dict | auto-mode provenance helpers |
| `ACCESS_FIX`, `CLEAR_SUFFIX`, `CLEAR_NAMES` | dict/str/set | auto-mode access fixes |

If your part is STM32, you can `from chips.stm32g474 import EN_MODER, strip_prefix, ...`
to reuse the enum vocabularies and helpers instead of re-typing them.

---

## Checklist

- [ ] `chips/<id>.py`, `chips/<id>.svd` created; SVD parses (`svd2od.py`)
- [ ] `chips/<id>.sections.json` generated (`make_sections.py`)
- [ ] descriptor + `PART`/`DOCUMENTS`/`DOC_RM`/`RM_REV` set in `chips/<id>.py`
- [ ] `build.py <id>` runs; coverage report read
- [ ] `TBD` driven to 0 (prefix overrides / chapter fallback / section_map)
- [ ] status/clear access verified with `rm_inspect.py`, encoded in `ACCESS_FIX`
- [ ] hero peripherals curated (verified access + enums)
- [ ] Tier 2 added (optional), `TIERS` set
- [ ] conformance check clean, `tsc` passes
- [ ] registered in `src/lib.ts`, added to `build:data`, deployed
