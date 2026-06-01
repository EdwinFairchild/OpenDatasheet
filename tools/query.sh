#!/usr/bin/env bash
# Quick tester for the OpenDatasheet MCP server.
#
# Usage:
#   ./tools/query.sh                       # list_parts on REMOTE
#   ./tools/query.sh local                 # list_parts on LOCAL (localhost:8787)
#   ./tools/query.sh remote describe ACME-IMU6
#   ./tools/query.sh local  measurands ACME-IMU6
#   ./tools/query.sh remote errata ACME-IMU6
#   ./tools/query.sh remote raw /parts/STM32G474RE.json
#
# Subcommands: list | describe <MPN> | measurands <MPN> | errata <MPN> | raw <path>

REMOTE_URL="https://opendatasheet-mcp.opendatasheet.workers.dev"
LOCAL_URL="http://localhost:8787"

# Optional first arg = target (local|remote). Default remote.
BASE="$REMOTE_URL"
if [ "${1:-}" = "local" ]; then BASE="$LOCAL_URL"; shift
elif [ "${1:-}" = "remote" ]; then BASE="$REMOTE_URL"; shift
fi

CMD="${1:-list}"
ARG="${2:-}"

prettify() {
  if command -v jq >/dev/null 2>&1; then
    jq -r '.result.content[0].text // .'
  else
    cat
  fi
}

# call_tool <tool-name> <json-arguments>
call_tool() {
  curl -s -X POST "$BASE/" \
    -H 'Content-Type: application/json' \
    -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"$1\",\"arguments\":$2}}"
}

echo "# target: $BASE  cmd: $CMD ${ARG}" >&2

case "$CMD" in
  list)       call_tool "list_parts"     "{}"                  | prettify ;;
  describe)   call_tool "describe_part"  "{\"mpn\":\"$ARG\"}"  | prettify ;;
  measurands) call_tool "get_measurands" "{\"mpn\":\"$ARG\"}"  | prettify ;;
  errata)     call_tool "get_errata"     "{\"mpn\":\"$ARG\"}"  | prettify ;;
  raw)        curl -s "$BASE$ARG" | prettify ;;
  *)          echo "unknown subcommand: $CMD" >&2; exit 2 ;;
esac
