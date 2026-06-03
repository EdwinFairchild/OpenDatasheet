# 02: Principles

These are the rules every other artifact must obey. The key words MUST, SHOULD, MAY are used per RFC 2119.

## 1. Schema and vocabulary, not a wire protocol

We define *what the data looks like* and *what it means*. We do **not** define how bytes move. Transport is MCP, plain HTTP, or a file on disk. **We MUST NOT invent a new wire protocol**, that path ends in [xkcd 927](https://xkcd.com/927/) ("now there are 15 standards"). We are the schema-and-vocabulary layer on top of existing pipes.

## 2. A part is a core plus composable profiles: not a monolithic type

This is the extensibility principle, and it is structural, not aspirational.

> A part is a **common core** that carries one or more capability **profiles**. To support a new class of device, you add a profile, you do not rewrite the schema.

- The **core** holds what nearly every embedded part has: identity, lifecycle, documents, packages, pinout, electrical characteristics, timing, limits, and prose sections.
- **Profiles** hold device-class-specific structure: `register-map` (MCUs, MPUs, and any part with a programmable register interface), `sensor` (measurands, ranges, conversions), `power` (regulators/converters), and so on.
- Profiles **compose**. A digital IMU carries `register-map` *and* `sensor`. A part declares its profiles in `conformance.profiles`, so a consumer (and the discovery layer) knows which queries make sense.
- Profiles MAY **link** to each other (e.g., a sensor's sensitivity references a `register-map` field that selects full-scale range). This is the difference between "two formats glued together" and one coherent model.

Adding a device class MUST be a new profile spec plus a JSON Schema fragment, never a breaking change to the core.

## 3. Open, namespaced extensions with a promotion path

A vendor or contributor MUST be able to add a field the spec does not yet define, without forking. Every object MAY carry an `extensions` object keyed by namespace (e.g., `"extensions": { "acme": { ... } }`). Unknown keys MUST be ignored by consumers, never rejected. Popular extensions SHOULD be promoted into a profile or the core through a documented registry process. This keeps the format alive and prevents the spec from being the bottleneck.

## 4. Every fact is cited

Provenance is mandatory at the leaf level. Every value (a reset value, an electrical limit, a conversion factor) MUST carry a `provenance` object naming the source `doc`, `section`, and `rev`. A value you cannot trace is not conformant. This is what makes the format auditable and safe for hardware, and it is what lets an agent answer with a citation instead of a guess.

## 5. Conditions are part of the value

An electrical or timing number is meaningless without its conditions. A `max` of 50 MHz means nothing without "at 3.3 V, −40 to 85 °C, 30 pF load." Every electrical/timing value MUST carry a `conditions` object (explicitly `{}` if truly unconditional). Naked numbers are invalid.

## 6. Tiered conformance: ship what you can

Perfection is unshippable; that is why the all-encompassing standard never landed while the narrow SVD did. A part declares the tiers it satisfies (`conformance.tiers`). Tools advertise the tiers they consume. A part MAY declare just its primary structured profile and climb later. Tooling MUST degrade gracefully when a tier or profile is absent. Tiers are defined in `03-SCHEMA.md`.

## 7. Umbrella over existing standards, not a replacement

CMSIS-SVD, IP-XACT, SystemRDL, and WaveDrom are **import sources**. A conformant toolchain SHOULD provide an SVD importer (it is the cheapest possible on-ramp for any Arm vendor). We adopt WaveDrom wholesale for waveforms. We never ask anyone to throw away an existing standard to adopt this one.

## 8. Self-describing and discoverable

A consumer MUST be able to discover what is queryable at runtime, not by reading a PDF. A part document declares its `profiles`; the query layer exposes enumerating/drill-down tools (list parts → list a part's profiles and queryable entities → list a peripheral's registers, etc.). See `04-MCP-INTERFACE.md`. Discovery is a first-class feature, not an afterthought.

## 9. JSON, Git-friendly, human-readable

The format is JSON because every AI and web toolchain speaks it, it diffs cleanly in version control, and a human can read it in a pinch. Documents SHOULD be stable under reordering and minimally noisy in diffs.

## 10. Errata are first-class overlays

A datasheet stops being true the moment an erratum corrects it. Errata MUST be expressible as a separate overlay document that overrides the part document by path, with its own provenance, and diffs cleanly across silicon revisions. Resolvers MUST expose both the original value and the override so an agent can explain a discrepancy.

## 11. Authority is explicit

Every document MUST declare `conformance.authority` as either `manufacturer-certified` or `community-provisional`. This single field lets a corpus safely mix authoritative vendor data with bootstrapped, AI-extracted data; agents can be told to trust one and flag the other.

## 12. Stable identifiers

MPNs, document IDs, section IDs, peripheral/register/field names, parameter symbols, and measurand IDs MUST be stable, so cross-references resolve and tool calls remain valid across revisions. Renames are versioned events, not silent edits.
