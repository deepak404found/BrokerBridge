#!/usr/bin/env bash
# Wave 3 Compose API E2E — allocate/assign/attach then health/routing/orders
set -euo pipefail
BASE="${BASE_URL:-http://localhost:8000}"
API="$BASE/api/v1"

echo "== W3 Compose E2E against $BASE =="

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

echo "-- list brokers --"
BROKERS=$(curl -sf "$API/brokers" -H "$AUTH")
CLIENT_ID=$(echo "$BROKERS" | python3 -c 'import sys,json; print(json.load(sys.stdin)[0]["client_id"])')
ALPHA=$(echo "$BROKERS" | python3 -c 'import sys,json; print([b["id"] for b in json.load(sys.stdin) if "Alpha" in b["display_name"]][0])')
BETA=$(echo "$BROKERS" | python3 -c 'import sys,json; print([b["id"] for b in json.load(sys.stdin) if "Beta" in b["display_name"]][0])')

setup_ip() {
  local BROKER_ID="$1"
  # Skip if broker already has an active assignment
  local EXISTING
  EXISTING=$(curl -sf "$API/infrastructure/assignments" -H "$AUTH" | python3 -c "
import sys,json
rows=json.load(sys.stdin)
for r in rows:
  if r.get('broker_account_id')=='$BROKER_ID' and r.get('status')=='active':
    print(r['static_ip_id']); break
")
  if [[ -n "$EXISTING" ]]; then
    echo "$EXISTING"
    return 0
  fi
  local IP INST IP_ID INST_ID
  IP=$(curl -sf -X POST "$API/infrastructure/ips" -H "$AUTH" -H 'Content-Type: application/json' -d '{"region":"ewr"}')
  IP_ID=$(echo "$IP" | python3 -c 'import sys,json; print(json.load(sys.stdin)["id"])')
  INST=$(curl -sf -X POST "$API/infrastructure/instances" -H "$AUTH" -H 'Content-Type: application/json' \
    -d "{\"client_id\":\"$CLIENT_ID\",\"region\":\"ewr\"}")
  INST_ID=$(echo "$INST" | python3 -c 'import sys,json; print(json.load(sys.stdin)["id"])')
  local ASSIGN_CODE
  ASSIGN_CODE=$(curl -s -o /tmp/w3_assign.json -w '%{http_code}' -X POST "$API/infrastructure/ips/$IP_ID/assign" -H "$AUTH" -H 'Content-Type: application/json' \
    -d "{\"broker_account_id\":\"$BROKER_ID\"}")
  if [[ "$ASSIGN_CODE" != "200" && "$ASSIGN_CODE" != "201" ]]; then
    echo "assign failed code=$ASSIGN_CODE body=$(cat /tmp/w3_assign.json)" >&2
    exit 1
  fi
  curl -sf -X POST "$API/infrastructure/ips/$IP_ID/attach" -H "$AUTH" -H 'Content-Type: application/json' \
    -d "{\"instance_id\":\"$INST_ID\"}" >/dev/null
  echo "$IP_ID"
}

echo "-- W2 allocate/assign/attach for Alpha + Beta --"
setup_ip "$ALPHA" >/dev/null
setup_ip "$BETA" >/dev/null

echo "-- health probe --"
curl -sf -X POST "$API/monitoring/brokers/health/probe" -H "$AUTH" | python3 -c 'import sys,json; d=json.load(sys.stdin); assert len(d)>=2 and all("score" in x for x in d)'

echo "-- rate-limits --"
curl -sf "$API/monitoring/rate-limits" -H "$AUTH" | python3 -c 'import sys,json; d=json.load(sys.stdin); assert len(d)>=2'

echo "-- get/put routing weights --"
curl -sf "$API/admin/config/routing.weights" -H "$AUTH" | python3 -c 'import sys,json; assert json.load(sys.stdin)["value"]["w_lat"]==0.25'
curl -sf -X PUT "$API/admin/config/routing.weights" -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"value":{"w_lat":0.25,"w_succ":0.30,"w_conn":0.15,"w_to":0.20,"w_ip":0.10}}' >/dev/null

echo "-- routing preview --"
curl -sf -X POST "$API/monitoring/routing/preview" -H "$AUTH" -H 'Content-Type: application/json' \
  -d "{\"client_id\":\"$CLIENT_ID\",\"region_preference\":\"ewr\"}" | python3 -c 'import sys,json; d=json.load(sys.stdin); assert d["require_assigned_ip"] is True and d["primary"]'

OID="e2e-$(date +%s)-buy"
echo "-- buy --"
BUY=$(curl -sf -w '\n%{http_code}' -X POST "$API/orders/buy" -H "$AUTH" -H 'Content-Type: application/json' \
  -d "{\"client_id\":\"$CLIENT_ID\",\"client_order_id\":\"$OID\",\"symbol\":\"AAPL\",\"quantity\":3,\"order_type\":\"MARKET\",\"time_in_force\":\"DAY\",\"region_preference\":\"ewr\"}")
BUY_CODE=$(echo "$BUY" | tail -n1)
BUY_BODY=$(echo "$BUY" | sed '$d')
test "$BUY_CODE" = "201"
ORDER_ID=$(echo "$BUY_BODY" | python3 -c 'import sys,json; d=json.load(sys.stdin); assert d["status"]=="SUBMITTED"; print(d["id"])')

echo "-- idempotent buy (200) --"
CODE=$(curl -s -o /tmp/w3_idem.json -w '%{http_code}' -X POST "$API/orders/buy" -H "$AUTH" -H 'Content-Type: application/json' \
  -d "{\"client_id\":\"$CLIENT_ID\",\"client_order_id\":\"$OID\",\"symbol\":\"AAPL\",\"quantity\":3,\"order_type\":\"MARKET\",\"time_in_force\":\"DAY\",\"region_preference\":\"ewr\"}")
test "$CODE" = "200"
python3 -c 'import json; d=json.load(open("/tmp/w3_idem.json")); assert d["id"]=="'"$ORDER_ID"'"'

echo "-- sell --"
curl -sf -X POST "$API/orders/sell" -H "$AUTH" -H 'Content-Type: application/json' \
  -d "{\"client_id\":\"$CLIENT_ID\",\"client_order_id\":\"e2e-$(date +%s)-sell\",\"symbol\":\"MSFT\",\"quantity\":1,\"order_type\":\"MARKET\",\"time_in_force\":\"DAY\"}" \
  | python3 -c 'import sys,json; assert json.load(sys.stdin)["side"]=="SELL"'

echo "-- cancel --"
curl -sf -X POST "$API/orders/$ORDER_ID/cancel" -H "$AUTH" | python3 -c 'import sys,json; assert json.load(sys.stdin)["status"]=="CANCELLED"'

echo "-- failovers + orders/engine --"
curl -sf "$API/monitoring/failovers" -H "$AUTH" >/dev/null
curl -sf "$API/monitoring/orders/engine" -H "$AUTH" | python3 -c 'import sys,json; d=json.load(sys.stdin); assert d["execution_mode"]=="inline"'

echo "-- OpenAPI paths present --"
curl -sf "$BASE/openapi.json" | python3 -c 'import sys,json; p=json.load(sys.stdin)["paths"]; assert "/api/v1/orders/buy" in p and "/api/v1/monitoring/brokers/health" in p and "/api/v1/admin/config/{key}" in p'

echo "W3 Compose E2E PASS (order=$ORDER_ID)"
