/* Wave 3 Admin wiring — Health, Rate Limits, Smart Routing, Orders */
(function () {
  const api = () => window.BrokerBridgeApi;
  const notify = (msg) => {
    if (typeof showNotification === "function") showNotification(msg);
    else console.log(msg);
  };
  const errNotify = (err) => {
    const code = err.error_code ? `[${err.error_code}] ` : "";
    let msg = err.message || "Request failed";
    if (err.error_code === "SUBSCRIPTION_EXPIRED" && !/Clients/i.test(msg)) {
      msg += " → Clients: create/extend an ACTIVE window, then retry Buy.";
    }
    notify(code + msg);
  };

  let demoClientId = null;
  let cachedHealth = [];
  let cachedRates = [];
  let cachedOrders = [];
  let filtersBound = false;

  function F() {
    return window.AdminFilters;
  }

  function setText(id, v) {
    const el = document.getElementById(id);
    if (el) el.textContent = v;
  }

  function healthBucket(status) {
    const s = String(status || "").toLowerCase();
    if (s === "healthy") return "healthy";
    if (s === "degraded") return "degraded";
    return "unhealthy";
  }

  function rateBucket(r) {
    return Number(r.pressure) >= 10 ? "pressure" : "ok";
  }

  function bindFiltersOnce() {
    if (filtersBound || !F()) return;
    filtersBound = true;
    F().bindStatCard(document.getElementById("w3-health-kpi-healthy"), "broker-health", "healthy", () => renderHealth());
    F().bindStatCard(document.getElementById("w3-health-kpi-degraded"), "broker-health", "degraded", () => renderHealth());
    F().bindStatCard(document.getElementById("w3-health-kpi-unhealthy"), "broker-health", "unhealthy", () => renderHealth());
    F().bindStatCard(document.getElementById("w3-rate-kpi-ok"), "rate-limits", "ok", () => renderRates());
    F().bindStatCard(document.getElementById("w3-rate-kpi-pressure"), "rate-limits", "pressure", () => renderRates());
  }

  function newClientOrderId(side) {
    const stamp = Date.now();
    if (side === "BUY" || side === "SELL") {
      return `admin-${side.toLowerCase()}-${stamp}`;
    }
    const short =
      typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
        ? crypto.randomUUID().replace(/-/g, "").slice(0, 8)
        : String(stamp).slice(-8);
    return `admin-${short}`;
  }

  function fillClientOrderId(side) {
    const el = document.getElementById("w3-order-client-order-id");
    if (el) el.value = newClientOrderId(side);
  }

  async function ensureAuth() {
    if (!api().getToken()) {
      notify("Sign in required");
      if (window.BrokerBridgeAuth) window.BrokerBridgeAuth.applyAuthState();
      throw new Error("Not authenticated");
    }
  }

  function subscriptionCoversNow(sub) {
    if (!sub || String(sub.status).toLowerCase() !== "active") return false;
    if (sub.teardown_completed_at) return false;
    const now = Date.now();
    const starts = Date.parse(sub.starts_at);
    const ends = Date.parse(sub.ends_at);
    if (Number.isNaN(starts) || Number.isNaN(ends)) return false;
    return starts <= now && now <= ends;
  }

  async function resolveDemoClientId() {
    if (demoClientId) return demoClientId;
    try {
      const subsPayload = await api().json("/subscriptions?limit=50&offset=0");
      const subs = Array.isArray(subsPayload.items)
        ? subsPayload.items
        : Array.isArray(subsPayload)
          ? subsPayload
          : [];
      const covering = subs.find(subscriptionCoversNow);
      if (covering && covering.client_id) {
        demoClientId = covering.client_id;
        return demoClientId;
      }
    } catch (_) {
      /* fall through to brokers */
    }
    const brokers = api().asItems(await api().json("/brokers"));
    if (brokers.length) {
      demoClientId = brokers[0].client_id;
      return demoClientId;
    }
    throw new Error("No demo client — seed brokers missing");
  }

  function readClientIdField() {
    const el = document.getElementById("w3-order-client-id");
    return (el && el.value && el.value.trim()) || "";
  }

  async function resolveOrderClientId() {
    const fromForm = readClientIdField();
    if (fromForm) return fromForm;
    const clientId = await resolveDemoClientId();
    const el = document.getElementById("w3-order-client-id");
    if (el) el.value = clientId;
    return clientId;
  }

  async function ensureClientIdField() {
    const el = document.getElementById("w3-order-client-id");
    if (!el) return;
    if (el.value && el.value.trim()) return;
    try {
      el.value = await resolveDemoClientId();
    } catch (_) {
      /* leave blank until seed/brokers available */
    }
  }

  function healthBadge(status) {
    if (status === "healthy") {
      return `<span class="text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded text-[11px]">healthy</span>`;
    }
    if (status === "degraded") {
      return `<span class="text-amber-400 bg-amber-500/10 px-2 py-0.5 rounded text-[11px]">degraded</span>`;
    }
    return `<span class="text-rose-400 bg-rose-500/10 px-2 py-0.5 rounded text-[11px]">${status || "—"}</span>`;
  }

  async function loadHealth() {
    await ensureAuth();
    bindFiltersOnce();
    cachedHealth = await api().json("/monitoring/brokers/health");
    if (!Array.isArray(cachedHealth)) cachedHealth = [];
    setText("w3-health-healthy", String(cachedHealth.filter((r) => healthBucket(r.status) === "healthy").length));
    setText("w3-health-degraded", String(cachedHealth.filter((r) => healthBucket(r.status) === "degraded").length));
    setText("w3-health-unhealthy", String(cachedHealth.filter((r) => healthBucket(r.status) === "unhealthy").length));
    if (F()) F().applySeed("broker-health", () => renderHealth());
    renderHealth();
  }

  function renderHealth() {
    const tbody = document.getElementById("w3-health-tbody");
    if (!tbody) return;
    const filter = F() ? F().get("broker-health") : null;
    if (F()) {
      F().syncCardStyles("broker-health");
      F().updateChip("broker-health");
    }
    if (!cachedHealth.length) {
      tbody.innerHTML = `<tr><td colspan="7" class="py-6 px-4 text-center text-gray-500">No health snapshots yet — Probe now.</td></tr>`;
      return;
    }
    const rows = filter ? cachedHealth.filter((r) => healthBucket(r.status) === filter) : cachedHealth;
    if (!rows.length) {
      tbody.innerHTML = `<tr><td colspan="7" class="py-6 px-4 text-center text-gray-500">No rows match filter.</td></tr>`;
      return;
    }
    tbody.innerHTML = rows
      .map(
        (r) => `<tr class="hover:bg-white/5">
          <td class="py-3 px-4 font-sans font-semibold text-white">${r.broker_display_name}</td>
          <td class="py-3 px-4">${Number(r.score).toFixed(1)}</td>
          <td class="py-3 px-4 font-sans">${healthBadge(r.status)}</td>
          <td class="py-3 px-4">${Number(r.latency_ms).toFixed(2)} ms</td>
          <td class="py-3 px-4">${(Number(r.success_rate) * 100).toFixed(0)}%</td>
          <td class="py-3 px-4">${Number(r.ip_health).toFixed(0)}</td>
          <td class="py-3 px-4 text-gray-400">${r.measured_at ? (api().formatTs ? api().formatTs(r.measured_at) : new Date(r.measured_at).toLocaleString()) : "—"}</td>
        </tr>`,
      )
      .join("");
  }

  async function probeHealth() {
    try {
      await ensureAuth();
      await api().json("/monitoring/brokers/health/probe", { method: "POST", body: "{}" });
      notify("Health probe complete");
      await loadHealth();
    } catch (e) {
      errNotify(e);
    }
  }

  async function loadRateLimits() {
    await ensureAuth();
    bindFiltersOnce();
    cachedRates = await api().json("/monitoring/rate-limits");
    if (!Array.isArray(cachedRates)) cachedRates = [];
    setText("w3-rate-ok", String(cachedRates.filter((r) => rateBucket(r) === "ok").length));
    setText("w3-rate-pressure", String(cachedRates.filter((r) => rateBucket(r) === "pressure").length));
    if (F()) F().applySeed("rate-limits", () => renderRates());
    renderRates();
  }

  function renderRates() {
    const tbody = document.getElementById("w3-rate-tbody");
    if (!tbody) return;
    const filter = F() ? F().get("rate-limits") : null;
    if (F()) {
      F().syncCardStyles("rate-limits");
      F().updateChip("rate-limits");
    }
    if (!cachedRates.length) {
      tbody.innerHTML = `<tr><td colspan="6" class="py-6 px-4 text-center text-gray-500">No brokers.</td></tr>`;
      return;
    }
    const rows = filter ? cachedRates.filter((r) => rateBucket(r) === filter) : cachedRates;
    if (!rows.length) {
      tbody.innerHTML = `<tr><td colspan="6" class="py-6 px-4 text-center text-gray-500">No rows match filter.</td></tr>`;
      return;
    }
    tbody.innerHTML = rows
      .map(
        (r) => `<tr class="hover:bg-white/5">
          <td class="py-3 px-4 font-sans font-semibold text-white">${r.broker_display_name}</td>
          <td class="py-3 px-4">${Number(r.limit_rps).toFixed(0)}</td>
          <td class="py-3 px-4">${Number(r.used).toFixed(0)}</td>
          <td class="py-3 px-4">${Number(r.remaining).toFixed(0)}</td>
          <td class="py-3 px-4">${Number(r.pressure).toFixed(1)}</td>
          <td class="py-3 px-4">${Number(r.window_seconds).toFixed(0)}s</td>
        </tr>`,
      )
      .join("");
  }

  async function loadRouting() {
    await ensureAuth();
    const weights = await api().json("/admin/config/routing.weights");
    const requireIp = await api().json("/admin/config/routing.require_assigned_ip");
    const policy = await api().json("/admin/config/rate_limit.exceed_policy");
    const v = weights.value || {};
    const set = (id, val) => {
      const el = document.getElementById(id);
      if (el) el.value = val;
    };
    set("w3-w-lat", v.w_lat);
    set("w3-w-succ", v.w_succ);
    set("w3-w-conn", v.w_conn);
    set("w3-w-to", v.w_to);
    set("w3-w-ip", v.w_ip);
    const flags = document.getElementById("w3-routing-flags");
    if (flags) {
      flags.textContent =
        `require_assigned_ip=${!!(requireIp.value && requireIp.value.enabled)} · exceed_policy=${(policy.value && policy.value.policy) || "REROUTE"} · weights v${weights.version}`;
    }
  }

  async function saveWeights() {
    try {
      await ensureAuth();
      const num = (id) => Number(document.getElementById(id).value);
      const value = {
        w_lat: num("w3-w-lat"),
        w_succ: num("w3-w-succ"),
        w_conn: num("w3-w-conn"),
        w_to: num("w3-w-to"),
        w_ip: num("w3-w-ip"),
      };
      await api().json("/admin/config/routing.weights", {
        method: "PUT",
        body: JSON.stringify({ value }),
      });
      notify("Routing weights saved");
      await loadRouting();
    } catch (e) {
      errNotify(e);
    }
  }

  async function previewRouting() {
    try {
      await ensureAuth();
      const clientId = await resolveDemoClientId();
      const preview = await api().json("/monitoring/routing/preview", {
        method: "POST",
        body: JSON.stringify({ client_id: clientId, region_preference: "ewr" }),
      });
      const el = document.getElementById("w3-routing-preview");
      if (el) el.textContent = JSON.stringify(preview, null, 2);
    } catch (e) {
      errNotify(e);
    }
  }

  async function loadOrders() {
    await ensureAuth();
    bindFiltersOnce();
    await ensureClientIdField();
    const listPayload = await api().json("/orders?limit=50&offset=0");
    const list = { items: api().asItems(listPayload), ...api().pageMeta(listPayload, 50) };
    const engine = await api().json("/monitoring/orders/engine");
    const engineEl = document.getElementById("w3-orders-engine");
    if (engineEl) {
      engineEl.textContent = `inflight ${engine.inflight}/${engine.max_inflight} · mode ${engine.execution_mode}`;
    }
    cachedOrders = list.items || [];
    renderOrderStats();
    if (F()) F().applySeed("orders", () => renderOrders());
    renderOrders();
  }

  function renderOrderStats() {
    const root = document.getElementById("w3-orders-stats");
    if (!root) return;
    const counts = {};
    cachedOrders.forEach((o) => {
      const st = o.status || "UNKNOWN";
      counts[st] = (counts[st] || 0) + 1;
    });
    const preferred = ["SUBMITTED", "SUBMITTING", "FAILED", "CANCELLED", "FILLED", "CREATED", "INDOUBT", "REJECTED"];
    const keys = [
      ...preferred.filter((k) => counts[k]),
      ...Object.keys(counts)
        .filter((k) => !preferred.includes(k))
        .sort(),
    ].slice(0, 6);
    if (!keys.length) {
      root.innerHTML = `<div class="glass-panel rounded-xl p-4 text-xs text-gray-500 col-span-2 md:col-span-4">No order statuses yet.</div>`;
      return;
    }
    root.innerHTML = keys
      .map(
        (k) => `<div id="w3-orders-kpi-${k}" class="glass-panel p-4 rounded-xl" data-order-status="${k}">
          <div class="text-xs text-gray-400">${k}</div>
          <div class="text-2xl font-bold text-white font-mono mt-1">${counts[k]}</div>
          <div class="text-[10px] text-gray-400 mt-1">Click to filter · again to clear</div>
        </div>`,
      )
      .join("");
    if (F()) {
      keys.forEach((k) => {
        F().bindStatCard(document.getElementById(`w3-orders-kpi-${k}`), "orders", k, () => renderOrders());
      });
      F().syncCardStyles("orders");
    }
  }

  function renderOrders() {
    const tbody = document.getElementById("w3-orders-tbody");
    if (!tbody) return;
    const filter = F() ? F().get("orders") : null;
    if (F()) {
      F().syncCardStyles("orders");
      F().updateChip("orders");
    }
    if (!cachedOrders.length) {
      tbody.innerHTML = `<tr><td colspan="9" class="py-6 px-4 text-center text-gray-500">No orders yet.</td></tr>`;
      return;
    }
    const items = filter ? cachedOrders.filter((o) => o.status === filter) : cachedOrders;
    if (!items.length) {
      tbody.innerHTML = `<tr><td colspan="9" class="py-6 px-4 text-center text-gray-500">No orders match filter.</td></tr>`;
      return;
    }
    const fmt = (v) => (api().formatTs ? api().formatTs(v) : v || "—");
    const copyBtn = (text, title) =>
      api().copyButtonHtml ? api().copyButtonHtml(text, title) : "";
    tbody.innerHTML = items
      .map(
        (o) => `<tr class="hover:bg-white/5" data-order-id="${o.id}">
          <td class="py-3 px-4">
            <span class="inline-flex items-center gap-1.5 max-w-full">
              <span class="truncate" title="${o.client_order_id}">${o.client_order_id}</span>
              ${copyBtn(o.client_order_id, "Copy client order ID")}
            </span>
          </td>
          <td class="py-3 px-4">${o.side}</td>
          <td class="py-3 px-4">${o.symbol}</td>
          <td class="py-3 px-4">${o.quantity}</td>
          <td class="py-3 px-4 font-sans">${o.status}</td>
          <td class="py-3 px-4 text-gray-400">${o.broker_account_id ? String(o.broker_account_id).slice(0, 8) : "—"}</td>
          <td class="py-3 px-4 text-gray-400 whitespace-nowrap">${fmt(o.created_at)}</td>
          <td class="py-3 px-4 text-gray-400 whitespace-nowrap">${fmt(o.updated_at)}</td>
          <td class="py-3 px-4 text-right font-sans">
            ${
              o.status === "SUBMITTED" || o.status === "SUBMITTING"
                ? `<button data-action="cancel" class="px-2 py-1 bg-dark-700 hover:bg-white/10 rounded text-xs text-rose-400">Cancel</button>`
                : "—"
            }
          </td>
        </tr>`,
      )
      .join("");
    tbody.querySelectorAll("tr[data-order-id]").forEach((tr) => {
      const id = tr.getAttribute("data-order-id");
      const btn = tr.querySelector('button[data-action="cancel"]');
      if (btn) btn.addEventListener("click", () => cancelOrder(id));
    });
  }

  async function cancelOrder(id) {
    try {
      await ensureAuth();
      await api().json(`/orders/${id}/cancel`, { method: "POST", body: "{}" });
      notify("Order cancelled");
      await loadOrders();
    } catch (e) {
      errNotify(e);
    }
  }

  async function placeSide(side) {
    try {
      await ensureAuth();
      const clientId = await resolveOrderClientId();
      const idInput = document.getElementById("w3-order-client-order-id");
      let clientOrderId = (idInput && idInput.value && idInput.value.trim()) || "";
      if (!clientOrderId) {
        fillClientOrderId(side);
        clientOrderId = (idInput && idInput.value) || newClientOrderId(side);
      }
      const symbol = (document.getElementById("w3-order-symbol") || {}).value || "AAPL";
      const qty = Number((document.getElementById("w3-order-qty") || {}).value || 10);
      const region = (document.getElementById("w3-order-region") || {}).value || null;
      const path = side === "BUY" ? "/orders/buy" : "/orders/sell";
      const body = {
        client_id: clientId,
        client_order_id: clientOrderId,
        symbol,
        quantity: qty,
        order_type: "MARKET",
        time_in_force: "DAY",
        region_preference: region || null,
      };
      const res = await api().request(path, { method: "POST", body: JSON.stringify(body) });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        const err = new Error(data.message || `HTTP ${res.status}`);
        err.error_code = data.error_code;
        throw err;
      }
      notify(`${side} ${res.status === 200 ? "replay" : "submitted"} — ${data.status}`);
      fillClientOrderId(side);
      await loadOrders();
    } catch (e) {
      errNotify(e);
    }
  }

  const pageLoaders = {
    "broker-health": loadHealth,
    "rate-limits": loadRateLimits,
    routing: loadRouting,
    orders: async () => {
      fillClientOrderId();
      await ensureClientIdField();
      await loadOrders();
    },
  };

  const _prevNavigate = window.navigateTo;
  window.navigateTo = function (pageId) {
    if (typeof _prevNavigate === "function") _prevNavigate(pageId);
    const loader = pageLoaders[pageId];
    if (loader) loader().catch(errNotify);
  };

  window.W3Admin = {
    loadHealth,
    probeHealth,
    loadRateLimits,
    loadRouting,
    saveWeights,
    previewRouting,
    loadOrders,
    placeBuy: () => placeSide("BUY"),
    placeSell: () => placeSide("SELL"),
    cancelOrder,
  };
})();
