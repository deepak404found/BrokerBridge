#!/usr/bin/env bash
# Wave 2 Compose API E2E — mirrors Admin action sequence
set -euo pipefail
BASE="${BASE_URL:-http://localhost:8000}"
API="$BASE/api/v1"

echo "== W2 Compose E2E against $BASE =="

echo "-- wait for live --"
for i in $(seq 1 60); do
  if curl -sf "$BASE/health/live" >/dev/null; then break; fi
  sleep 2
  if [[ $i -eq 60 ]]; then echo "API not live"; exit 1; fi
done

echo "-- login --"
TOKEN=$(curl -sf -X POST "$API/auth/token" \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d 'username=admin@brokerbridge.local&password=admin123!' | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')
AUTH="Authorization: Bearer $TOKEN"

echo "-- list brokers (seed) --"
BROKERS=$(curl -sf "$API/brokers" -H "$AUTH")
CLIENT_ID=$(echo "$BROKERS" | python3 -c 'import sys,json; print(json.load(sys.stdin)[0]["client_id"])')
SEED_BROKER=$(echo "$BROKERS" | python3 -c 'import sys,json; print(json.load(sys.stdin)[0]["id"])')

echo "-- create broker --"
NEW_BROKER=$(curl -sf -X POST "$API/brokers" -H "$AUTH" -H 'Content-Type: application/json' \
  -d "{\"client_id\":\"$CLIENT_ID\",\"provider_type\":\"mock\",\"display_name\":\"E2E Compose Broker\",\"priority\":55,\"enabled\":true,\"allowed_regions\":[\"ewr\"],\"credentials\":{\"api_key\":\"e2e\",\"api_secret\":\"secret\"},\"rate_limit_rps\":15}")
BROKER_ID=$(echo "$NEW_BROKER" | python3 -c 'import sys,json; print(json.load(sys.stdin)["id"])')

echo "-- capabilities refresh --"
curl -sf -X POST "$API/brokers/$BROKER_ID/capabilities/refresh" -H "$AUTH" >/dev/null

echo "-- disable / enable --"
curl -sf -X PATCH "$API/brokers/$BROKER_ID" -H "$AUTH" -H 'Content-Type: application/json' -d '{"enabled":false}' >/dev/null
curl -sf -X PATCH "$API/brokers/$BROKER_ID" -H "$AUTH" -H 'Content-Type: application/json' -d '{"enabled":true}' >/dev/null

echo "-- ensure session --"
SESS=$(curl -sf -X POST "$API/brokers/$BROKER_ID/sessions/ensure" -H "$AUTH")
echo "$SESS" | python3 -c 'import sys,json; d=json.load(sys.stdin); assert d["status"]=="valid" and d["has_tokens"] and "access_token" not in d'

echo "-- allocate IP --"
IP=$(curl -sf -X POST "$API/infrastructure/ips" -H "$AUTH" -H 'Content-Type: application/json' -d '{"region":"ewr"}')
IP_ID=$(echo "$IP" | python3 -c 'import sys,json; d=json.load(sys.stdin); assert d["ip_address"].startswith(("198.51.100.","203.0.113.")); print(d["id"])')

echo "-- provision instance --"
INST=$(curl -sf -X POST "$API/infrastructure/instances" -H "$AUTH" -H 'Content-Type: application/json' \
  -d "{\"client_id\":\"$CLIENT_ID\",\"region\":\"ewr\"}")
INST_ID=$(echo "$INST" | python3 -c 'import sys,json; print(json.load(sys.stdin)["id"])')

echo "-- assign + attach --"
curl -sf -X POST "$API/infrastructure/ips/$IP_ID/assign" -H "$AUTH" -H 'Content-Type: application/json' \
  -d "{\"broker_account_id\":\"$BROKER_ID\"}" >/dev/null
ATTACHED=$(curl -sf -X POST "$API/infrastructure/ips/$IP_ID/attach" -H "$AUTH" -H 'Content-Type: application/json' \
  -d "{\"instance_id\":\"$INST_ID\"}")
echo "$ATTACHED" | python3 -c 'import sys,json; assert json.load(sys.stdin)["status"]=="attached"'

echo "-- whitelist sync --"
WL=$(curl -sf -X POST "$API/infrastructure/brokers/$BROKER_ID/whitelist/sync" -H "$AUTH")
echo "$WL" | python3 -c 'import sys,json; d=json.load(sys.stdin); assert d["snapshot_id"] and len(d["findings"])>=1'

echo "-- detach + release --"
curl -sf -X POST "$API/infrastructure/ips/$IP_ID/detach" -H "$AUTH" >/dev/null
curl -sf -X DELETE "$API/infrastructure/ips/$IP_ID" -H "$AUTH" >/dev/null

echo "-- reuse reject (expect 409) --"
CODE=$(curl -s -o /tmp/w2_reuse.json -w '%{http_code}' -X POST "$API/infrastructure/ips/$IP_ID/assign" \
  -H "$AUTH" -H 'Content-Type: application/json' -d "{\"broker_account_id\":\"$BROKER_ID\"}")
test "$CODE" = "409"
python3 -c 'import json; d=json.load(open("/tmp/w2_reuse.json")); assert d["error_code"]=="IP_REUSE_POLICY"'

echo "-- monitoring sessions + assignments --"
curl -sf "$API/monitoring/sessions" -H "$AUTH" >/dev/null
curl -sf "$API/infrastructure/assignments" -H "$AUTH" >/dev/null

echo "W2 Compose E2E PASS (broker=$BROKER_ID seed=$SEED_BROKER)"
