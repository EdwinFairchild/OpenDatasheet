# OpenDatasheet

**The queryable datasheet for AI agents: the structured data a part vendor already owns, made machine-readable.**

AI agents can write firmware now. They just can't reliably read a datasheet. Hand one an 1,800-page reference manual and it will confidently invent a register value. The data it actually needs (registers, bitfields, timing, electrical limits) is exact and structured, but it ships as a PDF: perfect for humans and laser printers, useless as structured input.

A datasheet is not a document. It is a database with a print rendering. No engineer typed those register and timing tables by hand; they were generated from a structured internal source. The PDF is the lossy export. OpenDatasheet is a format for shipping the database instead of the screenshot, plus a query interface an agent can discover and trust.

> New here? Read [`docs/00-MISSION.md`](./docs/00-MISSION.md) for the one-page why, or the essay [`docs/datasheets-are-databases.md`](./docs/datasheets-are-databases.md) for the long form.

## What's in this repo

1. **The spec** ([`docs/`](./docs)): an open, versioned JSON format (a common core plus composable capability *profiles*) and the MCP query interface defined over it.
2. **A reference MCP server** (`src/`): a tiny, stateless, no-auth Cloudflare Worker that serves part documents over MCP (Streamable HTTP) and as static JSON.
3. **An authoring toolchain** (`tools/`): a Python pipeline that builds part JSON from CMSIS-SVD + a reference manual, used to encode a real **STM32G474RE**.

## Try it live

A reference server is deployed with a real STM32G474RE encoded (plus two fictional demo parts that exercise every feature):

```
https://opendatasheet-mcp.opendatasheet.workers.dev
```

```bash
# list the parts it knows
curl -s https://opendatasheet-mcp.opendatasheet.workers.dev \
  -H 'content-type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"list_parts","arguments":{}}}'

# a real query: the STM32G474 SPI1 CR1 register, fields, reset, access, all cited
curl -s https://opendatasheet-mcp.opendatasheet.workers.dev \
  -H 'content-type: application/json' \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"get_register","arguments":{"mpn":"STM32G474RE","peripheral":"SPI1","register":"CR1"}}}'
```

Or point any MCP client (Claude Desktop, Cursor, MCP Inspector) at that URL and ask in plain English. There is also a non-MCP static route: `GET /parts/index.json` lists the catalog, `GET /parts/<MPN>.json` returns a whole document.

## What the server exposes

Eleven tools, organized as a drill-down so an agent can discover what's queryable at runtime:

- **Discovery:** `list_parts`, `describe_part` (returns a capability index of every queryable name)
- **Registers** (register-map profile): `get_peripheral`, `get_register`
- **Sensors** (sensor profile): `get_measurands`, `get_conversion`
- **Cross-cutting:** `query_electrical`, `get_timing`, `get_pin_functions`, `get_errata`, `check_constraints`

What makes it more than a JSON dump:

- **Errata applied at query time, original preserved and cited.** Ask the demo IMU for its max sample rate and you get the corrected 4000 Hz, not the datasheet's 8000, with both shown.
- **Cross-profile links resolve.** `get_conversion` gives the accelerometer sensitivity for a range *and* the exact register field that selects it.
- **`check_constraints`** validates a proposed configuration against absolute-max / recommended-operating limits and errata, returning cited violations.

## The spec

The format and interface are specified in [`docs/`](./docs), written to be read by a human or an agent:

| Doc | What it covers |
|---|---|
| [`00-MISSION.md`](./docs/00-MISSION.md) | The one-page why and what success looks like |
| [`01-PROBLEM.md`](./docs/01-PROBLEM.md) | Why PDFs fail as agent input, and the gap nobody fills |
| [`02-PRINCIPLES.md`](./docs/02-PRINCIPLES.md) | The design rules everything else obeys |
| [`03-SCHEMA.md`](./docs/03-SCHEMA.md) | The JSON format: core + composable profiles + extensions |
| [`04-MCP-INTERFACE.md`](./docs/04-MCP-INTERFACE.md) | The MCP tools and how an agent discovers what it can ask |
| [`05-ROADMAP.md`](./docs/05-ROADMAP.md) | Phases, MVP, success metrics, open questions |

Status: `spec_version 0.1`, a draft / request for comments. Tell me where it breaks.

## Run your own

See **[DEV.md](./DEV.md)** for the full walkthrough: install, run locally, deploy to Cloudflare's free tier, and connect it to Claude, assuming no prior Node/Cloudflare/MCP experience. The short version:

```bash
npm install
npm run dev      # runs locally at http://localhost:8787
npx wrangler login
npm run deploy   # rebuilds the STM32 data, then deploys to a public workers.dev URL
```

`npm run deploy` runs a `predeploy` hook that regenerates part data from its CMSIS-SVD + reference manual via a Python pipeline, so the deployed data can't drift from source (needs Python 3). To ship the committed JSON without rebuilding, use `npx wrangler deploy`. The pipeline is multi-chip; see [`tools/README.md`](./tools/README.md) and [`tools/ADDING-A-CHIP.md`](./tools/ADDING-A-CHIP.md).

## Adding a part

Part documents are plain JSON in `data/`. Adding one is: drop a JSON file (following [`docs/03-SCHEMA.md`](./docs/03-SCHEMA.md), or generate it with the `tools/` pipeline), import it in `src/lib.ts`, redeploy. Every value carries provenance (source doc, section, revision) and an authority level (`manufacturer-certified` or `community-provisional`), so a corpus can safely mix vendor data with community extractions.

## Cost

Cloudflare Workers free tier: 100,000 requests/day, indefinitely, no egress fees. The server has no database and nothing to keep warm. See [DEV.md](./DEV.md) for details.
