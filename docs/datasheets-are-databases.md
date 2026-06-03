# Datasheets Are Databases. We Just Keep Shipping the Screenshot.

*A proposal, and a starter spec, for machine-readable hardware documentation in the age of AI agents.*

---

Every embedded engineer knows this dance. You need to bring up a sensor or an MCU. There's an 1,800-page reference manual, a separate datasheet, an errata sheet, and three application notes. You `Ctrl-F`. You squint at a register table that got mangled the instant you copied it out of the PDF. You cross-check a timing number against a diagram on page 612. You write the driver. You hope.

Now we're handing that same pile of PDFs to AI agents and acting surprised when they confidently invent a reset value.

Here is the thing nobody says out loud: **a datasheet is not a document. It is a database with a print rendering.** No human typed those register tables by hand. They were generated from an internal source of truth, the RTL register description, the characterization database, the CAD pinout. The PDF you download is the *lossy export*, optimized for human eyeballs and laser printers. And then every single party downstream, every firmware engineer, every code generator, every agent, burns effort reverse-engineering a structured database back out of its own printout.

That's the bug. And it's worth fixing at the source, not patching forever downstream.

## The cost has changed

For decades this was merely annoying. A human could absorb the ambiguity, flip to the errata, and use judgment. The cost of the lossy PDF was paid in engineer-hours and the occasional bad bring-up.

Agents change the economics in three specific ways.

**You're forced to choose between two bad options.** Either you stuff a multi-hundred-page manual into context (expensive, and the model still has to find the needle) or you do retrieval over unstructured PDF, which means a multi-column layout gets interleaved into nonsense, tables lose their structure, and the chunk that contained the register map gets split down the middle. Neither path gives the agent a *fact*. Both give it a probability distribution over what the fact might have been.

**The errors are the expensive kind.** A wrong reset value, a flipped bit-field, a mis-parsed access type (`W1C` read as `RW`) doesn't produce a syntax error. It produces firmware that compiles, runs, and quietly does the wrong thing to physical hardware. The whole point of a datasheet is that these values are *exact*. PDF extraction launders that exactness into a guess.

**Errata silently contradict the main document.** A datasheet stops being true the moment an erratum corrects it. Today nothing machine-readable links the two. A human knows to check the errata; an agent reading the reference manual has no idea the value in front of it was superseded eighteen months ago.

This is not a hypothetical pain. The broader ecosystem is already routing around it, the EDA tooling world is publishing guides on building local-LLM "datasheet extractors" precisely because [parsing hundreds of pages of datasheets under tight timelines has become nearly impossible](https://resources.altium.com/p/building-local-llm-datasheet-extractor-ic-driver-development) for the engineers expected to ship drivers. Every one of those extractors is a private, lossy, duplicated attempt to recover the database the vendor already had.

## Why now

Two things make this the moment.

First, agents that write firmware are no longer a demo. Engineers genuinely ask LLMs "which MCU should I use for X," then "now configure its SPI peripheral." Whatever the agent can use *correctly*, it recommends. Whatever it fumbles, it routes around.

Second, and this is the part that should make vendors pay attention, **the starting gun has already fired, but only the easy shot was taken.** In November 2025, Microchip [shipped a Model Context Protocol server](https://www.microchip.com/en-us/about/news-releases/products/microchip-technology-unveils-model-context-protocol-mcp-server) that lets agents pull verified product specs, datasheets, inventory, pricing, and lead times as JSON. That's real, it's public, and it kills the objection that semiconductor vendors won't embrace this.

But look closely at *which layer* shipped: catalog and procurement data, with datasheets exposed as **download links**. It is a parametric-search-and-sourcing API wearing an MCP hat. It does not expose what an agent writing a driver actually needs, the register's bit-fields, the SPI max clock *at 3.3 V across temperature*, the I²C setup time tied to a specific edge of a specific waveform.

That shallow catalog layer is being claimed across the industry right now. **The deep semantic layer, the hard part, the valuable part, is wide open.** This proposal is about that layer.

## The proposal: OpenDatasheet

*(Yes, the name is a placeholder. Bikeshed it after we agree on the schema, not before.)*

OpenDatasheet is two complementary things, and the relationship between them is the whole design.

**A static open schema.** A versioned, machine-readable description of a part, expressed in JSON because every AI toolchain and every web toolchain already speaks it and it diffs cleanly in Git. This is the artifact your build system consumes at code-generation time: offline, reproducible, vendorable into a repo, reviewable in a pull request.

**An MCP-native query layer defined over that schema.** A standard set of MCP tools and resources so an agent inside a harness never ingests a manual at all. It asks precise questions and gets exact, *cited* answers:

- `get_register("ACX-32F4", "SPI1", "CR1")`
- `query_electrical("ACX-32F4", "f_SCK_max", { vdd_v: 3.3, temp_c: [-40, 85] })`
- `resolve_xref("ACX-32F4", "RM", "28.5.1")`

The crucial framing, and the reason this rides *with* the agent ecosystem instead of fighting it:

> **MCP gave us the pipes. OpenDatasheet defines what hardware documentation looks like flowing through them.**

MCP is deliberately generic. It specifies a transport and an abstraction, tools, resources, prompts, and says *nothing* about what a register or an electrical parameter should look like. That silence is exactly the gap. OpenDatasheet is not a competing protocol and is emphatically **not a new wire format**, going down that road just earns you the [xkcd 927](https://xkcd.com/927/) outcome where now there are fifteen standards. It is a *schema and a vocabulary*: the W3C-style layer on top, not another pipe underneath.

And it is explicitly an **umbrella, not a replacement.** The islands already exist:

- **CMSIS-SVD** already describes peripherals, registers, fields, and enumerated values, but only for Arm Cortex-M, only registers, with uneven quality. OpenDatasheet's register layer is a *superset* that imports SVD directly.
- **IP-XACT** (IEEE 1685) and **SystemRDL** describe register maps in the EDA world. Import paths, not competitors.
- **WaveDrom** already represents waveforms as JSON that renders to SVG. We adopt it wholesale for timing diagrams.

If you've already published an SVD file, you're partway to a conformant OpenDatasheet part for free.

## What's actually in it

The entity list is the boring part. The value is in the details most extraction tools quietly drop.

- **Identity & lifecycle**: MPN, family, package variants, silicon revision, lifecycle status, and *hard links to the errata that override this document*.
- **Pinout, per package**: each pin's number, electrical type, and the full alternate-function mux. The mux table is one of the worst things to recover from a PDF and one of the most needed.
- **Register / peripheral / memory map**: peripheral → register (offset) → field (bit position, access type, reset value) → **enumerated values**. The enums are the entire point: `00 = disabled, 01 = mode A, 10 = mode B`. An agent without the enums writes plausible, wrong code.
- **Electrical & timing characteristics**: and here is the detail that separates a real spec from a toy: every parameter carries its **conditions**. A `max` of 50 MHz means nothing without "at 3.3 V, −40 to 85 °C, 30 pF load." A number without its conditions is not data; it's a liability.
- **Structured figures**: timing diagrams and state machines as *data*, not PNGs. The agent can reason about the waveform; the human still gets a rendered picture. Same source, two renderings.
- **Absolute maximums & recommended operating conditions**: the safety envelope, machine-checkable.
- **Application data**: recommended decoupling, pull-ups, reference circuits, typical configurations.

Two cross-cutting fields do the heavy lifting, because they are what make this *trustworthy enough for hardware*:

**Provenance on every fact.** Each value links back to its source document, section, and revision. The agent can answer "max SCK = 50 MHz [DS rev 4, §6.3.2]." When hardware breaks, you need to know exactly which claim, from which revision, was wrong. This is also what makes the format auditable for safety-critical work.

**Errata as a first-class overlay.** A separate, layered document expresses "this field's behavior was amended by erratum X for revision Y," and diffs cleanly across silicon revisions. Get this right and you've solved a problem that bites every embedded team, human or agent, not just an AI nicety.

Here's a single concrete taste. One real-shaped register field, with enums and provenance:

```json
{
  "name": "CPHA",
  "description": "Clock phase",
  "bit_offset": 0,
  "bit_width": 1,
  "access": "read-write",
  "enum": [
    { "value": 0, "name": "FIRST_EDGE",  "description": "Data captured on the first clock transition" },
    { "value": 1, "name": "SECOND_EDGE", "description": "Data captured on the second clock transition" }
  ],
  "provenance": { "doc": "ACX-RM-001", "section": "28.5.1", "rev": "4" }
}
```

That object is unambiguous. It cannot be interleaved into nonsense, split across a chunk boundary, or guessed at. An agent reads it and writes correct code. The full schema, with electrical/timing examples, the errata overlay, the MCP tool surface, and a JSON Schema you can validate against, lives in the companion **OpenDatasheet Specification (v0.1, Draft / RFC)**.

## The thing that makes it adoptable: tiers, not boil-the-ocean

The reason a general "structure everything perfectly" standard has never landed, while the narrow SVD did, is that perfection is unshippable. So mirror SVD's lesson: let a vendor describe only the part they can, ship it in a sprint, and climb over quarters. Tooling degrades gracefully when a tier is absent.

- **Tier 0, Navigable PDF (near-zero effort).** Ship the existing PDF plus a sidecar manifest: stable section IDs, a real machine-readable table of contents with anchors, MPN/revision metadata, errata links, and resolved cross-references. No new content, just stop making the PDF opaque. Immediate win for anyone doing retrieval today.
- **Tier 1, The register layer.** Machine-readable registers, peripherals, and memory map (SVD-plus, not Arm-only). The single highest-ROI tier, because driver and HAL generation is the highest-value agent task and the one where mistakes cost the most.
- **Tier 2, The parametric layer.** Electrical, timing, and thermal parameters with full conditions. Unlocks design-rule checking and "can this part do X at 1.8 V" reasoning.
- **Tier 3, The semantic layer.** Functional prose chunked with entity tags (which registers and peripherals each section concerns) plus the structured figures. This is the only tier you can't fully structure, prose about how a DMA arbiter works stays prose, but making it *addressable and entity-linked* captures most of the benefit.

## Why a vendor actually says yes

A pitch that only argues "this helps AI developers" loses in the meeting. The vendor's two questions are "what's in it for me" and "why now." The answers here are unusually strong.

**The killer argument: design-in velocity is revenue.** The entire semiconductor business is the fight to get designed into products. When an agent can instantly and *correctly* configure your part, you get designed in faster. When your competitor's part is AI-legible and yours is an 1,800-page PDF the agent fumbles, the agent quietly recommends theirs. **AI-legibility is becoming a competitive axis in part selection, and most vendors haven't noticed yet.** That is the slide that makes a VP lean forward.

**Support deflection.** A large share of FAE tickets are some flavor of "how do I configure this register." Machine-readable docs plus agents deflect those before they're ever filed.

**The marginal cost is low.** Vendors already own the structured data, they generated the tables from it. This is a publishing-pipeline change, not a new authoring burden.

**Liability reduction.** Specs with explicit conditions and a machine-checkable safety envelope reduce out-of-spec misuse, by humans and agents alike.

And there's a competitive-pressure lever already on the table: one major vendor has shipped the catalog layer. Every other vendor now gets to decide whether to lead the *deep* layer or explain later why they didn't.

## How we get past the cold start

Vendors are slow, and you cannot wait for the big names to move first. So bootstrap the way OpenStreetMap and Wikidata did.

The wedge is an **AI-assisted extraction pipeline** that converts existing PDFs into Tier-1/Tier-2 data, clearly stamped `community-provisional`. That gives the ecosystem immediate coverage and creates the leverage: once agents are visibly succeeding against provisional data for a part, the manufacturer faces a choice, let the community define how their silicon is represented (and own the errors that creep in), or **claim and certify** the authoritative version. Authority becomes a field in the schema: `manufacturer-certified` versus `community-provisional`. Vendors will move to protect the narrative, exactly the way brands claim their map and knowledge-graph entries.

Then do what made MCP spread: open spec, reference tooling, dogfood it in a real harness, and win on one undeniable demo, *an agent bringing up a sensor or MCU driver in under a minute, zero PDF reading, every register value cited back to a spec section.* Standards win meetings on demos like that.

## The ask

**If you're a vendor:** publish one part at Tier 1. Pick your flagship MCU or your most-supported sensor, export its register map as an OpenDatasheet file (start from your SVD if you have one), and serve it over an MCP endpoint alongside the catalog data you may already expose. One part. Measure the support-ticket deflection and the agent success rate. Then decide.

**If you're in the community:** the minimum useful contribution is *one peripheral, for one part, at Tier 1, as a single JSON file* validated against the schema. Run it through an extraction pass, fix the enums by hand, mark it `community-provisional`, and open a pull request. A thousand of those is a usable corpus.

**If you build agents and harnesses:** stop writing a private extractor for every vendor's PDF quirks. Consume the schema, contribute the parts you depend on back upstream, and put the "facts, not guesses, with citations" demo in front of the vendors you wish would adopt it.

The PDF was the right artifact for a world of human readers and laser printers. That world is ending. The data was always structured underneath, we just kept shipping the screenshot.

Let's ship the database.

---

*The companion OpenDatasheet Specification (v0.1), full schema, JSON Schema validators, electrical/timing/errata examples, the MCP tool surface, and conformance tiers, is published alongside this post. Fork it, file issues, break it.*
