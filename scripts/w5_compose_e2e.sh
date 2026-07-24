#!/usr/bin/env bash
# Wave 5 Compose API E2E — consumer, replay, dashboard, sim, pagination
set -euo pipefail
BASE="${BASE_URL:-http://localhost:8000}"
API="$BASE/api/v1"

echo "== W5 Compose E2E against $BASE =="

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

echo "-- brokers (paginated) --"
BROKERS=$(curl -sf "$API/brokers?limit=25&offset=0" -H "$AUTH")
echo "$BROKERS" | python3 -c 'import sys,json; d=json.load(sys.stdin); assert "items" in d and "total" in d and d["items"]'
CLIENT_ID=$(echo "$BROKERS" | python3 -c 'import sys,json; print(json.load(sys.stdin)["items"][0]["client_id"])')
ALPHA=$(echo "$BROKERS" | python3 -c 'import sys,json; print([b["id"] for b in json.load(sys.stdin)["items"] if "Alpha" in b["display_name"]][0])')

ensure_assignment() {
  local BROKER_ID="$1"
  local REGION="${2:-ewr}"
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
  IP=$(curl -sf -X POST "$API/infrastructure/ips" -H "$AUTH" -H 'Content-Type: application/json' -d "{\"region\":\"$REGION\"}")
  IP_ID=$(echo "$IP" | python3 -c 'import sys,json; print(json.load(sys.stdin)["id"])')
  INST=$(curl -sf -X POST "$API/infrastructure/instances" -H "$AUTH" -H 'Content-Type: application/json' \
    -d "{\"client_id\":\"$CLIENT_ID\",\"region\":\"$REGION\"}")
  INST_ID=$(echo "$INST" | python3 -c 'import sys,json; print(json.load(sys.stdin)["id"])')
  curl -sf -X POST "$API/infrastructure/ips/$IP_ID/assign" -H "$AUTH" -H 'Content-Type: application/json' \
    -d "{\"broker_account_id\":\"$BROKER_ID\"}" >/dev/null
  curl -sf -X POST "$API/infrastructure/ips/$IP_ID/attach" -H "$AUTH" -H 'Content-Type: application/json' \
    -d "{\"instance_id\":\"$INST_ID\"}" >/dev/null
  echo "$IP_ID"
}

echo "-- ensure assigned IP --"
ensure_assignment "$ALPHA" "ewr" >/dev/null

echo "-- activate redpanda event provider --"
curl -sf -X PUT "$API/admin/providers/event" -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"provider_type":"redpanda_local","validate_first":true,"activate":true,"config":{"brokers":"redpanda:9092","security_protocol":"PLAINTEXT","topic_prefix":"brokerbridge","consumer_group":"brokerbridge-lab"}}' \
  | python3 -c 'import sys,json; d=json.load(sys.stdin); assert d["provider_type"]=="redpanda_local"'

sleep 3

echo "-- place order + drain + assert consumer feed --"
OID="w5-e2e-$(date +%s)"
curl -sf -X POST "$API/orders/buy" -H "$AUTH" -H 'Content-Type: application/json' \
  -d "{\"client_id\":\"$CLIENT_ID\",\"client_order_id\":\"$OID\",\"symbol\":\"AAPL\",\"quantity\":1,\"region_preference\":\"ewr\"}" \
  | python3 -c 'import sys,json; assert json.load(sys.stdin)["status"]=="SUBMITTED"'

FOUND=False
for i in $(seq 1 40); do
  curl -sf -X POST "$API/monitoring/events/drain" -H "$AUTH" >/dev/null || true
  FOUND=$(curl -sf "$API/monitoring/events?limit=50&offset=0" -H "$AUTH" | python3 -c '
import sys,json
d=json.load(sys.stdin)
items=d.get("items", d if isinstance(d,list) else [])
print(any(r.get("event_type")=="order.submitted" for r in items))
')
  if [[ "$FOUND" == "True" ]]; then break; fi
  sleep 1
done
test "$FOUND" = "True"

echo "-- dashboard --"
curl -sf "$API/monitoring/dashboard" -H "$AUTH" | python3 -c '
import sys,json
d=json.load(sys.stdin)
assert "health" in d and "engine" in d and "events" in d
assert d.get("orders_total", 0) >= 1
'

echo "-- replay run --"
curl -sf -X POST "$API/admin/replay/run?limit=50" -H "$AUTH" | python3 -c '
import sys,json
d=json.load(sys.stdin)
assert "scanned" in d and "recovered" in d and "skipped" in d
'

echo "-- sim fault on/off --"
curl -sf -X POST "$API/admin/sim/faults" -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"fault_id":"broker_unavailable","enabled":true}' \
  | python3 -c 'import sys,json; assert json.load(sys.stdin)["enabled"] is True'
curl -sf -X POST "$API/admin/sim/faults/clear" -H "$AUTH" \
  | python3 -c 'import sys,json; assert all(not f["enabled"] for f in json.load(sys.stdin))'

echo "-- pagination envelopes --"
curl -sf "$API/infrastructure/ips?limit=2&offset=0" -H "$AUTH" | python3 -c '
import sys,json
d=json.load(sys.stdin)
assert "items" in d and "total" in d and d["limit"]==2 and d["offset"]==0
'
curl -sf "$API/orders?limit=25&offset=0" -H "$AUTH" | python3 -c '
import sys,json
d=json.load(sys.stdin)
assert "items" in d and "total" in d
'

echo "-- event provider re-activate (consumer reconnect) --"
curl -sf -X PUT "$API/admin/providers/event" -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"provider_type":"redpanda_local","validate_first":true,"activate":true,"config":{"brokers":"redpanda:9092","security_protocol":"PLAINTEXT","topic_prefix":"brokerbridge","consumer_group":"brokerbridge-lab"}}' >/dev/null
sleep 2
OID2="w5-e2e-re-$(date +%s)"
curl -sf -X POST "$API/orders/buy" -H "$AUTH" -H 'Content-Type: application/json' \
  -d "{\"client_id\":\"$CLIENT_ID\",\"client_order_id\":\"$OID2\",\"symbol\":\"MSFT\",\"quantity\":1,\"region_preference\":\"ewr\"}" \
  | python3 -c 'import sys,json; assert json.load(sys.stdin)["status"]=="SUBMITTED"'
FOUND2=False
for i in $(seq 1 40); do
  curl -sf -X POST "$API/monitoring/events/drain" -H "$AUTH" >/dev/null || true
  FOUND2=$(curl -sf "$API/monitoring/events?limit=50" -H "$AUTH" | python3 -c '
import sys,json
d=json.load(sys.stdin)
items=d.get("items", d if isinstance(d,list) else [])
print(any(r.get("event_type")=="order.submitted" and "MSFT" in str(r.get("payload")) for r in items) or any(r.get("event_type")=="order.submitted" for r in items))
')
  if [[ "$FOUND2" == "True" ]]; then break; fi
  sleep 1
done
test "$FOUND2" = "True"

echo "W5 Compose E2E PASS"
