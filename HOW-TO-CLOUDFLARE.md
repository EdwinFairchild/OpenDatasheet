# OpenDatasheet MCP server — get it running, then live

This walks you from a fresh machine to a public MCP server that Claude (or any MCP client) can call — assuming you've **never used Node tooling, Cloudflare, wrangler, or MCP** before. Every command is copy-pasteable.

The whole thing takes about 20 minutes, and it costs **nothing**: Cloudflare Workers' free tier is 100,000 requests/day, forever, and this server has no database and no servers to keep warm.

---

## What you're about to do

1. Install the tools and the project's dependencies.
2. Run the server **on your own machine** and poke at it.
3. Push it to Cloudflare so it has a public `https://…workers.dev` URL.
4. Connect it to Claude Desktop and ask it questions.

You don't need to understand the code to do any of this. (If you want to, `src/index.ts` is ~150 readable lines and the comments explain the MCP bits.)

---

## Before you start: install Node.js

Wrangler (Cloudflare's deploy tool) runs on Node.js.

- Go to <https://nodejs.org> and install the **LTS** version (v20 or newer).
- Verify it worked. Open a terminal and run:

  ```bash
  node --version
  ```

  You should see something like `v20.x.x` or higher. If the command isn't found, close and reopen your terminal, or restart your computer, and try again.

> **Where's "a terminal"?** On macOS: open the **Terminal** app (Cmd-Space, type "Terminal"). On Windows: open **PowerShell** (Start menu, type "PowerShell"). On Linux: your usual terminal.

You'll also want a free Cloudflare account, but you don't have to create it now — the deploy step does it for you in the browser.

---

## Step 1 — Open a terminal in this folder

Unzip the project somewhere you'll remember (e.g. your Desktop). Then in your terminal, move into the folder:

```bash
cd path/to/opendatasheet-mcp
```

A shortcut: type `cd ` (with a trailing space), then drag the folder from your file explorer onto the terminal window — it pastes the path for you. Press Enter.

To confirm you're in the right place:

```bash
ls
```

You should see `package.json`, `wrangler.toml`, `src`, `data`, and this file.

---

## Step 2 — Install dependencies

```bash
npm install
```

This reads `package.json` and downloads wrangler + TypeScript into a local `node_modules` folder. It runs once (and again only if you change dependencies). It does **not** install anything system-wide.

---

## Step 3 — Run it locally

```bash
npm run dev
```

You'll see output ending with something like:

```
[wrangler:info] Ready on http://localhost:8787
```

That's your server, running on your machine. Leave this terminal open — it stays running until you press **Ctrl-C**.

Open <http://localhost:8787> in a browser. You should get a small JSON page listing the server name and its tools. That confirms the server is alive.

> A couple of `Unable to fetch the Request.cf object` warnings on startup are normal in local mode and harmless.

---

## Step 4 — Try it (the visual way: MCP Inspector)

The **MCP Inspector** is a free tool from the MCP project that gives you a UI to list a server's tools and call them. It's the easiest way to confirm everything works before you wire it into Claude.

Open a **second** terminal (leave `npm run dev` running in the first), and run:

```bash
npx @modelcontextprotocol/inspector
```

Say yes if it asks to install. It prints a URL (something like `http://localhost:6274`) and opens it in your browser. In the Inspector:

1. Set **Transport Type** to **Streamable HTTP**.
2. Set **URL** to `http://localhost:8787`.
3. Click **Connect**.
4. Click **List Tools**. You should see all 11 tools.
5. Pick a tool, fill in the arguments, and click **Run Tool**. Try these:

   | Tool | Arguments | What you should see |
   |---|---|---|
   | `list_parts` | *(none)* | Two parts: ACME-M0 and ACME-IMU6 |
   | `describe_part` | `mpn` = `ACME-IMU6` | Its profiles + a capability index of everything you can query |
   | `get_conversion` | `mpn` = `ACME-IMU6`, `measurand` = `accel`, `range` = `FS_8G` | Sensitivity 4096 LSB/g **and** the register field (`FS_SEL`) that selects it |
   | `get_measurands` | `mpn` = `ACME-IMU6` | Max sample rate shows **4000 Hz** — the errata-corrected value, with the original 8000 noted |
   | `check_constraints` | `mpn` = `ACME-M0`, `config` = `{"vdd_v":3.3,"temp_c":80,"mode":"master","fields":{"BR":"DIV2"}}` | A **violation**, because an erratum forbids BR=DIV2 above 70 °C |

> **Prefer the terminal?** You can skip the Inspector and hit the server with curl instead:
> ```bash
> curl -s http://localhost:8787 -H 'content-type: application/json' \
>   -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"list_parts","arguments":{}}}'
> ```

When you're satisfied, you can stop the local server (Ctrl-C in the first terminal). Time to put it online.

---

## Step 5 — Put it on the internet

### 5a. Log in to Cloudflare

```bash
npx wrangler login
```

This opens your browser. If you don't have a Cloudflare account, you can create one for free right there. Click **Allow** to let wrangler deploy on your behalf, then return to the terminal.

### 5b. Deploy

```bash
npm run deploy
```

The first time, wrangler may ask to register a free `workers.dev` subdomain (pick anything — it's the `YOUR-SUBDOMAIN` part of your URL). When it finishes you'll see your live URL:

```
https://opendatasheet-mcp.YOUR-SUBDOMAIN.workers.dev
```

**Copy that URL.** That's your public MCP server. Anyone — or any AI agent — can now reach it.

Confirm it's live by opening that URL in a browser; you should see the same info page as before.

> Re-deploying later is just `npm run deploy` again. Each deploy replaces the old version in a few seconds.

---

## Step 6 — Connect it to Claude Desktop

Claude Desktop talks to local (stdio) servers natively and to **remote** servers through a tiny bridge called `mcp-remote`. You point it at your URL in a config file.

1. Find (or create) Claude Desktop's config file:
   - **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
   - **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

   If the file doesn't exist, create it. (On macOS you can run `open -e ~/Library/Application\ Support/Claude/claude_desktop_config.json` — if it says the file doesn't exist, create it in that folder.)

2. Put this in it, replacing the URL with **your** deployed URL:

   ```json
   {
     "mcpServers": {
       "opendatasheet": {
         "command": "npx",
         "args": ["-y", "mcp-remote", "https://opendatasheet-mcp.YOUR-SUBDOMAIN.workers.dev"]
       }
     }
   }
   ```

   If the file already has an `mcpServers` block, just add the `"opendatasheet"` entry alongside your existing ones.

3. **Fully quit and reopen Claude Desktop** (not just close the window — quit the app).

4. In a new chat, you should see the OpenDatasheet tools available (look for the tools/connector indicator). Now ask it things — see the prompts below.

> **Other clients:** Cursor, Windsurf, VS Code, and others use the same `mcp-remote` pattern in their own MCP config. Some newer Claude builds also let you paste a remote MCP URL directly as a "custom connector" in settings, which skips the config file entirely — if your version has that, just paste the `workers.dev` URL there and pick the Streamable HTTP transport.

---

## Step 7 — Ask Claude these

Once connected, try (in plain English — Claude picks the right tool):

- *"What parts can you look up?"*
- *"Describe the ACME-IMU6 — what can I query about it?"*
- *"On the ACME-M0, what does the BR field in SPI1's CR1 register do?"*
- *"What's the max SPI clock on the ACME-M0 at 1.8 V versus 3.3 V?"* → 12 MHz vs 24 MHz, each with its conditions.
- *"For the ACME-IMU6 accelerometer at ±8 g, what's the sensitivity, and which register selects that range?"* → 4096 LSB/g, set by `FS_SEL = FS_8G`.
- *"What's the real maximum sample rate of the ACME-IMU6 accelerometer?"* → 4000 Hz (the datasheet says 8000; the erratum corrects it).
- *"Is it safe to run the ACME-M0 SPI at BR=DIV2 in master mode at 80 °C?"* → No — flagged by an erratum, with the citation.

That last pair is the whole point of the project: the server hands back the *corrected, cited* answer instead of whatever a PDF said on page 812.

---

## Make it yours

### Rename the server
Edit the `name` in `wrangler.toml` (this changes your URL) and `SERVER_INFO` in `src/index.ts`, then `npm run deploy`.

### Add your own part
The data is just JSON files in `data/`. To add a part:

1. Create `data/my-part.json` following the shape of `acme-m0.json`. (The full schema and what each profile means is in the OpenDatasheet doc set — `03-SCHEMA.md`.)
2. Open `src/lib.ts` and (a) import it at the top, (b) add it to the `PARTS` map:

   ```ts
   import myPart from "../data/my-part.json";
   // ...
   const PARTS: Record<string, Part> = {
     "ACME-M0": m0 as Part,
     "ACME-IMU6": imu6 as Part,
     "MY-PART": myPart as Part,   // <- add this
   };
   ```

3. If it has an errata overlay, add it to `ERRATA` the same way.
4. `npm run deploy`.

That's the entire workflow. No database, no migrations.

---

## Cost & limits (why this won't surprise you)

- **Free tier:** 100,000 requests/day, indefinitely — not a trial. A read-only datasheet server is unlikely to approach that.
- **No egress fees, ~0 ms cold start.** You're not paying for idle warm instances the way you would on most platforms, and a traffic spike doesn't create a bandwidth bill.
- **Watch usage:** Cloudflare dashboard → **Workers & Pages** → your worker → **Metrics**.
- **If you ever outgrow free:** the Workers Paid plan is about $5/month including millions of requests, then pennies per additional million. Even going viral is coffee money. Check the current numbers at <https://developers.cloudflare.com/workers/platform/pricing/>.
- **On the free plan you don't get a surprise invoice** — you get rate-limited, not billed into the ground.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `command not found: node` / `npm` | Node isn't installed or the terminal predates the install. Reinstall from nodejs.org, then open a fresh terminal. |
| `command not found: wrangler` | Run commands as `npm run dev` / `npm run deploy`, or prefix with `npx` (e.g. `npx wrangler login`). Don't install wrangler globally. |
| `npm run dev` errors about a port in use | Something's already on 8787. Stop it, or run `npx wrangler dev --port 8799` and use that port. |
| Inspector / Claude won't connect | Make sure the transport is **Streamable HTTP** (not SSE). Confirm the URL opens in a browser and shows the info page. |
| Claude doesn't show the tools | Did you **fully quit** and reopen the app? Check the JSON config is valid (no trailing commas) and the URL is exactly your deployed one. |
| Deploy says you're not logged in | Run `npx wrangler login` again and complete the browser step. |
| A tool returns an error like `Peripheral 'X' not found` | That's expected behavior — the message lists the valid names. Call `describe_part` first to see what's queryable. |
| Need to see what's happening on the live server | `npx wrangler tail` streams your deployed worker's live logs. |

---

## What's in this folder

```
opendatasheet-mcp/
├── HOW-TO-CLOUDFLARE.md   ← you are here
├── README.md              ← short project overview
├── package.json           ← dependencies + the dev/deploy scripts
├── tsconfig.json          ← TypeScript settings
├── wrangler.toml          ← Cloudflare Worker config (name, entry point)
├── src/
│   ├── index.ts           ← the Worker: CORS, routing, MCP JSON-RPC handling
│   ├── tools.ts           ← the 11 tools (this is where the verbs live)
│   └── lib.ts             ← data registry, errata resolver, path resolver
└── data/
    ├── acme-m0.json       ← example MCU (register-map profile)
    ├── acme-m0-errata.json
    ├── acme-imu6.json     ← example IMU (register-map + sensor profiles)
    └── acme-imu6-errata.json
```

The two ACME parts are **fictional** — synthetic examples chosen to exercise every feature (two composed profiles, a cross-profile link, and both kinds of errata). Swap in real parts when you're ready.
