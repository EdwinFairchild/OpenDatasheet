# OpenDatasheet MCP server

A reference implementation of an **MCP server that serves machine-readable embedded-part documentation** — the queryable alternative to a PDF datasheet, for AI agents. It runs on Cloudflare Workers, has no database, and is free to host.

It speaks the Model Context Protocol over the Streamable HTTP transport (JSON-RPC 2.0), stateless and no-auth, like a public read-only API.

## Quick start

See **[HOW-TO-CLOUDFLARE.md](./HOW-TO-CLOUDFLARE.md)** for the full beginner walkthrough (install → run locally → deploy → connect to Claude). The short version:

```bash
npm install
npm run dev      # runs locally at http://localhost:8787
npx wrangler login
npm run deploy   # gives you a public https://…workers.dev URL
```

## What it exposes

Eleven tools, organized as a drill-down so an agent can discover what's queryable at runtime:

- **Discovery:** `list_parts`, `describe_part` (returns a capability index of every queryable name)
- **Registers (register-map profile):** `get_peripheral`, `get_register`
- **Sensors (sensor profile):** `get_measurands`, `get_conversion`
- **Cross-cutting:** `query_electrical`, `get_timing`, `get_pin_functions`, `get_errata`, `check_constraints`

Highlights worth seeing in action:

- **Errata are applied at query time, with the original preserved and cited.** Ask for the IMU's max sample rate and you get the corrected 4000 Hz, not the datasheet's 8000.
- **Cross-profile links resolve.** `get_conversion` tells you the accelerometer sensitivity for a range *and* the exact register field that selects it.
- **`check_constraints`** validates a proposed configuration against absolute-max / recommended-operating limits and errata constraints, returning cited violations.

## The data

Part documents are plain JSON in `data/`. Adding a part = drop a JSON file, import it in `src/lib.ts`, redeploy. The two included ACME parts are **fictional** examples that exercise every feature.

The data model (the common core + composable capability profiles, extensions, authority levels) and the MCP interface design are specified in the OpenDatasheet doc set — see `03-SCHEMA.md` and `04-MCP-INTERFACE.md`.

## Layout

| Path | What it is |
|---|---|
| `src/index.ts` | The Worker: CORS, routing, MCP JSON-RPC dispatch |
| `src/tools.ts` | The tool definitions and their logic |
| `src/lib.ts` | Data registry + errata/path resolvers |
| `data/*.json` | Part documents and errata overlays |
| `wrangler.toml` | Cloudflare Worker config |

## Cost

Cloudflare Workers free tier: 100,000 requests/day, indefinitely, no egress fees. See HOW-TO-CLOUDFLARE.md for details.
