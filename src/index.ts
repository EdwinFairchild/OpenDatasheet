// OpenDatasheet MCP server: Cloudflare Worker.
//
// Speaks the Model Context Protocol over the "Streamable HTTP" transport, which
// is just JSON-RPC 2.0 over HTTP POST. This server is stateless and requires no
// auth (like a public read-only API). It implements the minimum MCP surface that
// real clients (Claude Desktop via mcp-remote, the MCP Inspector, etc.) need:
//   - initialize
//   - notifications/initialized  (and other notifications: accepted, no reply)
//   - ping
//   - tools/list
//   - tools/call
//
// All the domain logic (the tools) lives in tools.ts; the data + resolvers in lib.ts.

import { TOOLS } from "./tools";
import { getStaticFile, getCatalog } from "./lib";

const PROTOCOL_VERSION = "2025-06-18";
const SERVER_INFO = { name: "opendatasheet-mcp", version: "0.1.0" };

const CORS: Record<string, string> = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS, DELETE",
  "Access-Control-Allow-Headers": "Content-Type, Accept, Authorization, mcp-session-id, mcp-protocol-version",
  "Access-Control-Expose-Headers": "mcp-session-id",
};

function json(body: unknown, status = 200, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", ...CORS, ...headers },
  });
}

function ok(id: unknown, result: unknown) {
  return { jsonrpc: "2.0", id, result };
}
function rpcErr(id: unknown, code: number, message: string) {
  return { jsonrpc: "2.0", id: id ?? null, error: { code, message } };
}

// Handle one JSON-RPC message. Returns a response object, or null for notifications
// (notifications carry no `id` and must not receive a JSON-RPC reply).
function handleMessage(msg: any): object | null {
  if (!msg || typeof msg !== "object" || Array.isArray(msg)) {
    return rpcErr(null, -32600, "Invalid Request");
  }
  const { id, method, params } = msg as { id?: unknown; method?: string; params?: any };
  const isNotification = id === undefined;

  switch (method) {
    case "initialize":
      // Echo the client's protocol version when present so we never force a
      // version it doesn't support; fall back to our known version otherwise.
      return ok(id, {
        protocolVersion: params?.protocolVersion ?? PROTOCOL_VERSION,
        capabilities: { tools: { listChanged: false } },
        serverInfo: SERVER_INFO,
      });

    case "notifications/initialized":
    case "notifications/cancelled":
      return null;

    case "ping":
      return ok(id, {});

    case "tools/list":
      return ok(id, {
        tools: TOOLS.map((t) => ({
          name: t.name,
          description: t.description,
          inputSchema: t.inputSchema,
        })),
      });

    case "tools/call": {
      const name: string = params?.name;
      const args: Record<string, any> = params?.arguments ?? {};
      const tool = TOOLS.find((t) => t.name === name);
      if (!tool) {
        return ok(id, { content: [{ type: "text", text: `Unknown tool: ${name}` }], isError: true });
      }
      try {
        const out = tool.run(args);
        const text = typeof out === "string" ? out : JSON.stringify(out, null, 2);
        return ok(id, { content: [{ type: "text", text }] });
      } catch (e: any) {
        // MCP convention: tool execution errors are reported in the result with
        // isError:true, not as JSON-RPC protocol errors.
        return ok(id, { content: [{ type: "text", text: `Error: ${e?.message ?? String(e)}` }], isError: true });
      }
    }

    default:
      if (isNotification) return null;
      return rpcErr(id, -32601, `Method not found: ${method}`);
  }
}

export default {
  async fetch(request: Request): Promise<Response> {
    const { method } = request;

    // CORS preflight.
    if (method === "OPTIONS") {
      return new Response(null, { status: 204, headers: CORS });
    }

    if (method === "GET") {
      // Static raw-file route: serve whole part / errata documents by name.
      // This is the non-MCP binding external file consumers use to fetch, cache,
      // and own the data offline. Must come before the SSE/banner logic.
      const url = new URL(request.url);

      // Discovery catalog: one row per part so a consumer can find a part by
      // MPN/family without knowing the exact name, then fetch the full doc.
      // Must precede the generic /parts/{file}.json match below.
      if (url.pathname === "/parts/index.json") {
        return json(
          { parts: getCatalog() },
          200,
          { "cache-control": "public, max-age=3600" },
        );
      }

      const m = url.pathname.match(/^\/parts\/(.+\.json)$/i);
      if (m) {
        const doc = getStaticFile(m[1]);
        if (doc === undefined) {
          return json({ error: `Unknown part file: ${m[1]}` }, 404);
        }
        // Part docs are immutable per revision, so cache them aggressively.
        return json(doc, 200, { "cache-control": "public, max-age=86400" });
      }

      const accept = request.headers.get("accept") ?? "";
      // A client probing for a server->client SSE stream. This stateless server
      // doesn't provide one; 405 tells compliant clients to proceed without it.
      if (accept.includes("text/event-stream")) {
        return new Response("This server does not provide a GET event stream.", { status: 405, headers: CORS });
      }
      // Otherwise show a human-friendly info page.
      const origin = new URL(request.url).origin;
      return json({
        name: SERVER_INFO.name,
        version: SERVER_INFO.version,
        description: "OpenDatasheet MCP server. POST JSON-RPC 2.0 here to use it.",
        transport: "Streamable HTTP (MCP)",
        endpoint: origin,
        tools: TOOLS.map((t) => t.name),
      });
    }

    if (method !== "POST") {
      return json(rpcErr(null, -32600, "Use POST with a JSON-RPC 2.0 body."), 405);
    }

    let payload: any;
    try {
      payload = await request.json();
    } catch {
      return json(rpcErr(null, -32700, "Parse error: body is not valid JSON."), 400);
    }

    // Support a JSON-RPC batch (array) or a single message.
    if (Array.isArray(payload)) {
      const responses = payload.map(handleMessage).filter((r): r is object => r !== null);
      if (responses.length === 0) return new Response(null, { status: 202, headers: CORS });
      return json(responses);
    }

    const response = handleMessage(payload);
    if (response === null) return new Response(null, { status: 202, headers: CORS });
    return json(response);
  },
};
