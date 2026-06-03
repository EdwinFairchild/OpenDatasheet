# 01: The Problem

## Statement

The authoritative documentation for embedded parts, datasheets, reference manuals, errata, application notes, is published as PDF. PDF is a format for *rendering glyphs at coordinates for a human reader*. It is not a format for delivering structured data to a program. The exact, structured information a tool or agent needs is therefore locked inside a print artifact, and every consumer must extract it back out, lossily and redundantly.

This is true for **every class of embedded part**, not just microcontrollers. A sensor datasheet buries its conversion formula and full-scale ranges in prose and tables; a power IC datasheet buries its efficiency curves in figures; an interface chip buries its timing in diagrams. Same disease, different organ.

## To be precise about PDFs and agents

An agent *can* read a PDF. That is not the issue. The issue is that **pulling precise values out of a PDF is error-prone and lossy**, and PDF is simply not the optimal way to hand structured data to an agent. Three concrete consequences:

1. **You are forced to choose between two bad options.** Either stuff a multi-hundred-page manual into context (expensive, and the needle is still buried), or run retrieval over the unstructured PDF, where multi-column layouts interleave into nonsense, tables lose their row/column structure, and the chunk containing the register map gets split down the middle. Neither path returns a *fact*; both return a probability distribution over what the fact might have been.
2. **The errors are the expensive kind.** A wrong reset value, a flipped bit-field, a mis-read access type (`W1C` parsed as `RW`), a dropped condition on an electrical limit, none of these produce an error message. They produce firmware that compiles, runs, and quietly does the wrong thing to physical hardware. The entire value of a datasheet is that its numbers are *exact*. PDF extraction launders that exactness into a guess.
3. **Humans fumble through it too.** This is not only an AI problem. Engineers lose hours cross-referencing a timing number on page 612 against a diagram, checking the errata for a contradiction, and decoding a mux table. Making the data machine-readable helps the human as much as the agent.

## Why this matters more now

- Agents that write firmware and select parts are no longer demos. Engineers genuinely ask an LLM "which part should I use for X," then "now configure it." Whatever the agent can use *correctly*, it recommends. Whatever it fumbles, it routes around.
- The volume and pace of designs has outrun the human ability to read manuals cover-to-cover. The tooling ecosystem is already reacting, vendors and EDA tool makers are shipping private "datasheet extractors" because parsing hundreds of pages under deadline has become impractical. Every one of those extractors is a duplicated, lossy attempt to recover the database the vendor already had.

## The data is already structured underneath

Vendors generated those tables from internal databases. Publishing structured data is therefore mostly a **publishing-pipeline change, not a new authoring burden**. The marginal cost is low; the source of truth already exists.

## Prior art, and the gap

The islands exist. None covers the whole problem across device classes:

- **CMSIS-SVD**: an XML format describing peripherals, registers, fields, and enumerated values. Real and useful, but **Arm Cortex-M only**, **registers only** (no electrical, timing, pinout, sensor data), and uneven in quality.
- **IP-XACT (IEEE 1685)** and **SystemRDL**, register/memory-map description in the EDA world. Import sources, not consumer-facing part documentation.
- **WaveDrom**: represents waveforms as JSON that renders to SVG. The right pattern for timing diagrams; we adopt it.
- **Parametric / catalog APIs**: distributors and some vendors expose searchable parameters (price, stock, a few headline specs). Shallow by design.
- **Vendor MCP servers**: at least one major vendor (Microchip, launched November 2025) now serves an MCP endpoint returning product specifications, inventory, pricing, lead times, and compliance data as JSON, with datasheets exposed as **download links**. This validates the direction and kills the "vendors won't adopt MCP" objection, but it is the **catalog/sourcing/compliance layer**. The datasheet still comes back as a PDF link. The deep structured documentation, registers, bit-fields, electrical and timing parameters with their conditions, sensor conversions, is **not** exposed as queryable data.

**The gap:** a vendor-neutral, machine-readable format for the *deep* documentation layer, covering *any* embedded device class, with a query interface agents can discover and trust. That is unclaimed. That is the mission.

## References

- Microchip MCP Server launch (Nov 6, 2025): https://www.microchip.com/en-us/about/news-releases/products/microchip-technology-unveils-model-context-protocol-mcp-server
- Microchip MCP Server resource page: https://www.microchip.com/en-us/resources/model-context-protocol-server
- On the practical pain of datasheet extraction for driver development (Altium, 2026): https://resources.altium.com/p/building-local-llm-datasheet-extractor-ic-driver-development
- CMSIS-SVD, IP-XACT (IEEE 1685), SystemRDL, WaveDrom, named standards; search for current specs.
