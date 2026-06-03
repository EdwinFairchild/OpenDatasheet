# OpenDatasheet

*Machine-readable documentation for embedded parts, and a query layer agents can actually use.*

> **The opendatasheet name is a placeholder.** We can tweak it after the schema stabilizes unless the comminuty iss fine with it. "Part" throughout means *any* embedded component, MCU, MPU, sensor, power IC, interface chip, module, not just microcontrollers.

This folder is a foundational doc set. It defines the mission, the problem, the principles, the JSON schema, the MCP query interface, and the roadmap. It is written to be read by **either a human or an AI agent**: drop the folder into a repo, point your agent at it (or paste the files in order into its context), and it will understand what we are building and why.

## Read in this order

| File | What it gives you |
|---|---|
| `00-MISSION.md` | The north star. What we are building, scope, what success looks like, non-goals. Start here. |
| `01-PROBLEM.md` | Why this needs to exist. The specific failure modes of PDFs-as-agent-input, what already exists, and the gap. |
| `02-PRINCIPLES.md` | The design rules everything else must obey. Read before touching the schema. |
| `03-SCHEMA.md` | The JSON format: common core + composable capability **profiles** + an open extension mechanism. The heart of the spec. |
| `04-MCP-INTERFACE.md` | How agents query the data and **discover what they can ask** over MCP. Answers "how does the agent know what fields/queries exist." |
| `05-ROADMAP.md` | The plan, the MVP, success metrics, and open questions. |

## Status

`spec_version: 0.1`, Draft / Request for Comments. This is a starting point, not a finished standard. The fastest way to improve it is to encode a real part you actually use and record where the schema fought you.

## For an agent picking this up

Your prime directive: **make any factual claim about a part exact and traceable, or do not make it.** Every value in this format carries provenance (source document, section, revision). When you answer a question about a part, cite it. When you cannot find a value in structured form, say so, do not infer it from a PDF and present it as fact.
