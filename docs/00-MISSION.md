# 00: Mission

## The one-sentence mission

Make every fact in an embedded part's documentation **structured, queryable, and citable**, so that any tool or AI agent can retrieve an exact value, a register's reset state, a sensor's conversion formula, an electrical limit at a given supply, without parsing a PDF.

## The reframe everything follows from

**A datasheet is not a document. It is a database with a print rendering.**

No engineer typed those register tables, electrical tables, or pinout maps by hand. They were generated from an internal source of truth: the RTL register description, the characterization database, the CAD pinout. The PDF you download is the *lossy export*, optimized for human eyes and laser printers. Every party downstream, every firmware engineer, every code generator, every agent, then burns effort reverse-engineering a structured database back out of its own printout.

We are going to stop shipping the screenshot and start shipping the database.

## What we are building

Two layers, and the relationship between them is the design.

1. **A schema**: an open, versioned, JSON description of a part. Git-friendly, diffable, human-readable. This is what a build system consumes at code-generation time: offline, reproducible, reviewable in a pull request. Defined in `03-SCHEMA.md`.
2. **A query interface**: a standard set of MCP tools defined *over* the schema, so an agent in a harness never ingests a manual. It asks precise questions and gets exact, cited answers, and it can **discover** what is askable. Defined in `04-MCP-INTERFACE.md`.

The schema is transport-agnostic. MCP is the first binding, not the only one; the same data can be a file on disk, a static JSON over HTTP, or a server endpoint.

## Scope: all embedded parts, not just MCUs

This is the load-bearing scope decision. The format must describe a microcontroller's register map **and** a temperature sensor's conversion curve **and** a buck converter's efficiency points, and whatever comes next, without a schema rewrite for each.

We achieve this with **composable capability profiles** (see `02-PRINCIPLES.md` and `03-SCHEMA.md`):

> A part is not a *type*. A part is a common core that carries one or more capability **profiles**. To support a new class of device, you add a profile, you do not fork the schema.

A microcontroller carries the `register-map` profile. A digital sensor carries `sensor` **and** `register-map` (it has registers you read over I²C/SPI). A power IC carries `power`. New device class → new profile. This is what makes "easy to extend to anything embedded" a structural property rather than a promise.

## What success looks like

- An agent answers "what does `BR = 0b101` mean on this MCU's SPI?" or "what's the max sample rate of this IMU at ±8 g?" with an exact value **and a citation**, having queried structured data, not guessed from a PDF.
- A vendor publishes one flagship part at the register/parametric tier over an MCP endpoint, and measures fewer support tickets and higher agent success on their part.
- The community can encode a part, MCU or sensor or anything, by writing one JSON file against a stable schema, and extend the format to a new device class by adding a profile through a documented process.

## Non-goals

- **Not a new wire protocol.** Transport is MCP / HTTP / files. We define *what the data looks like*, never *how the bytes move*. (See the xkcd-927 warning in `02-PRINCIPLES.md`.)
- **Not a replacement for SVD, IP-XACT, SystemRDL, or WaveDrom.** Those are *import sources*. We are the umbrella, not a competitor.
- **Not a parametric-catalog clone.** Catalog/sourcing data (price, stock, compliance) is the shallow layer others already serve. We are after the deep layer: the structured documentation an agent needs to actually *use* the part.
- **Not boil-the-ocean.** Conformance is tiered. A vendor ships what they can and climbs.
