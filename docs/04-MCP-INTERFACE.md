# 04: MCP Interface & Discovery

The schema (`03`) is transport-agnostic. This document defines the **MCP binding**: the tools an OpenDatasheet server exposes, plus the part people ask about most: **how an agent discovers what it can query**.

---

## Discovery: the two layers

This is the answer to "how does the agent know what fields or queries it can do."

### Layer 1: Tool discovery (MCP gives you this)

When a client connects to an MCP server, it can request the tool list (`tools/list`). The server returns each tool with:

- a **`name`** (e.g., `get_register`),
- a human-readable **`description`** (what it does, which profile it pertains to), and
- an **`inputSchema`**, a JSON Schema describing the arguments.

The host application feeds these definitions to the model. **That is how the agent knows which tools exist and exactly what arguments to pass.** The same mechanism exists for `resources/list` and `prompts/list`, and a server can emit a `list_changed` notification if its tool set changes. (Recent MCP revisions also let a tool declare an output schema / return structured content; even without it, document the return shape in the description and/or expose it via the `describe_part` tool below.)

So Layer 1 answers: *what verbs exist, and what arguments does each take.*

### Layer 2: Data discovery (you design this into the tools)

Tool discovery does **not** tell the agent which *values* are valid. Nothing in the `inputSchema` for `get_register` says that `CONFIG` is a real peripheral on this part, or that `accel` is a queryable measurand. That is a data-level question, and it is the part you own.

The fix is **enumerating / drill-down tools** so the agent discovers the *nouns* at runtime:

```
list_parts            → which parts exist
  └ describe_part      → this part's profiles + an index of what is queryable
      └ get_peripheral  → this peripheral's registers      (register-map profile)
      └ get_measurands  → this part's measurands           (sensor profile)
          └ get_register / get_conversion / query_electrical → the leaf facts
```

`describe_part` is the keystone: it returns the part's `conformance.profiles` plus a capability index (peripheral names, measurand IDs, parameter symbols, diagram IDs). With that, the agent knows it may ask register questions *and* sensor questions on this part, and which specific names are valid, before making a single leaf query. This is also how extensibility surfaces to the agent: a new profile shows up in `profiles`, and the agent adapts without any client change.

Layer 1 + Layer 2 together = the agent can self-orient completely without ever opening a PDF.

---

## Tool surface

Tools are grouped: **core** (always available) and **profile-scoped** (meaningful only when the part declares that profile). A profile-scoped tool SHOULD error cleanly (`profile_not_present`) if called on a part lacking it; the agent learns the profile set from `describe_part` first and avoids that.

### Core tools

| Tool | Input | Returns |
|---|---|---|
| `list_parts` | `{ query?, manufacturer?, family? }` | `[{ mpn, family, lifecycle, profiles, tiers }]` |
| `describe_part` | `{ mpn }` | identity, packages, documents, `profiles`, `tiers`, authority, **capability index** |
| `get_pin_functions` | `{ mpn, package, pin }` | pin type + alternate-function mux |
| `query_electrical` | `{ mpn, parameter, conditions? }` | the conditional value row(s) matching `conditions`, with provenance |
| `get_timing` | `{ mpn, diagram_id }` | timing parameters + WaveDrom waveform |
| `resolve_xref` *(planned)* | `{ mpn, doc, section }` | the structured section/content at that anchor |
| `get_errata` | `{ mpn, revision? }` | the override list for that silicon revision |
| `check_constraints` | `{ mpn, config }` | validates a proposed configuration against `limits` + errata; returns violations |

> *(planned)* `resolve_xref` is specified here but **not yet implemented** in the
> reference server (which ships the eleven tools below it). It depends on the
> Tier-3 `sections[].xrefs` data; once parts carry resolved cross-references it
> turns a "see §8.4" pointer into the structured target. Tracked in `05-ROADMAP.md`.

### `register-map` profile tools

| Tool | Input | Returns |
|---|---|---|
| `get_peripheral` | `{ mpn, peripheral }` | peripheral + its register list (names + offsets) |
| `get_register` | `{ mpn, peripheral, register }` | full field/enum/access/reset breakdown, **errata applied**, with provenance |

### `sensor` profile tools

| Tool | Input | Returns |
|---|---|---|
| `get_measurands` | `{ mpn }` | measurand IDs, quantities, units, ranges |
| `get_conversion` | `{ mpn, measurand, range? }` | the conversion formula + the resolved sensitivity for the selected range, with the controlling register field |

New profile → a small set of profile-scoped tools, advertised through `describe_part`. The core tools never change.

---

## Contract rules

1. **Every returned value carries its `provenance`.** The agent can cite "[ACME-DS-IMU6 rev 3, §8.4]" and a human can verify it. This is non-negotiable; it is what makes the data trustworthy for hardware.
2. **`get_*` returns errata-resolved values by default**, with an `original` field preserved when an override applied, so the agent can explain *why* a value differs from the reference manual rather than silently contradicting it.
3. **Profile-scoped tools fail gracefully** with a typed error when the profile is absent.

---

## What `tools/list` actually returns (concrete)

So you can see what the agent receives, here is one tool as returned by discovery:

```json
{
  "name": "get_register",
  "description": "Return the full field/bit/enum/access/reset breakdown for one register, with errata applied and a source citation. Requires the 'register-map' profile (check describe_part first).",
  "inputSchema": {
    "type": "object",
    "required": ["mpn", "peripheral", "register"],
    "properties": {
      "mpn":        { "type": "string", "description": "Manufacturer part number, e.g. ACME-IMU6" },
      "peripheral": { "type": "string", "description": "Peripheral name from describe_part, e.g. CONFIG" },
      "register":   { "type": "string", "description": "Register name from get_peripheral, e.g. ACCEL_CFG" }
    }
  }
}
```

The model reads that and knows it can call `get_register`, that it needs three strings, and where to get valid values for them.

---

## A sample interaction trace

Agent question: *"What accelerometer sensitivity do I get on the ACME-IMU6 if I set ±8 g, and which register sets that?"*

1. `describe_part({ mpn: "ACME-IMU6" })` → profiles `["register-map","sensor"]`; capability index lists measurand `accel` and peripheral `CONFIG`.
2. `get_conversion({ mpn: "ACME-IMU6", measurand: "accel", range: "FS_8G" })` → sensitivity `4096 LSB/g`, formula `value_g = raw / sensitivity`, controlling field `CONFIG.ACCEL_CFG.FS_SEL = FS_8G (value 2)`, with provenance.
3. (optional) `get_register({ mpn: "ACME-IMU6", peripheral: "CONFIG", register: "ACCEL_CFG" })` → confirms `FS_SEL` is bits [4:3], enum value `2 = ±8 g`.

The agent answers with the exact sensitivity, the exact register write, **and citations**, none of it parsed from a PDF.

---

## Resources (alternative discovery path)

A server MAY also expose each part document as an MCP **resource** (listed via `resources/list`, read by URI). This lets a client pull the whole structured document when that is more useful than tool-by-tool queries, for example, to generate a complete HAL offline. Tools are for targeted facts; resources are for the whole artifact.

---

## Transport notes

- Bind over MCP **streamable HTTP** for a hosted server, or **stdio** for a local one. (Microchip's public server uses streamable HTTP; following suit keeps clients interoperable.)
- The server is a thin layer over a directory of part documents: load the JSON, apply errata overlays, resolve cross-profile links and `selected_by` references, and answer. No database required for an MVP.
