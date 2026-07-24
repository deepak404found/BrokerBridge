/* Wave 3 Admin wiring — Health, Rate Limits, Smart Routing, Orders */
(function () {
  const api = () => window.BrokerBridgeApi;
  const notify = (msg) => {
    if (typeof showNotification === "function") showNotification(msg);
    else console.log(msg);
  };
  const errNotify = (err) => {
    const code = err.error_code ? `[${err.error_code}] ` : "";
    notify(code + (err.message || "Request failed"));
  };

  let demoClientId = null;

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

  async function resolveDemoClientId() {
    if (demoClientId) return demoClientId;
    const brokers = api().asItems(await api().json("/brokers"));
    if (brokers.length) {
      demoClientId = brokers[0].client_id;
      return demoClientId;
    }
    throw new Error("No demo client — seed brokers missing");
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
    const rows = await api().json("/monitoring/brokers/health");
    const tbody = document.getElementById("w3-health-tbody");
    if (!tbody) return;
    if (!rows.length) {
      tbody.innerHTML = `<tr><td colspan="7" class="py-6 px-4 text-center text-gray-500">No health snapshots yet — Probe now.</td></tr>`;
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
          <td class="py-3 px-4 text-gray-400">${r.measured_at ? new Date(r.measured_at).toLocaleString() : "—"}</td>
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
    const rows = await api().json("/monitoring/rate-limits");
    const tbody = document.getElementById("w3-rate-tbody");
    if (!tbody) return;
    if (!rows.length) {
      tbody.innerHTML = `<tr><td colspan="6" class="py-6 px-4 text-center text-gray-500">No brokers.</td></tr>`;
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
    const listPayload = await api().json("/orders?limit=50&offset=0");
    const list = { items: api().asItems(listPayload), ...api().pageMeta(listPayload, 50) };
    const engine = await api().json("/monitoring/orders/engine");
    const engineEl = document.getElementById("w3-orders-engine");
    if (engineEl) {
      engineEl.textContent = `inflight ${engine.inflight}/${engine.max_inflight} · mode ${engine.execution_mode}`;
    }
    const tbody = document.getElementById("w3-orders-tbody");
    if (!tbody) return;
    const items = list.items || [];
    if (!items.length) {
      tbody.innerHTML = `<tr><td colspan="7" class="py-6 px-4 text-center text-gray-500">No orders yet.</td></tr>`;
      return;
    }
    tbody.innerHTML = items
      .map(
        (o) => `<tr class="hover:bg-white/5" data-order-id="${o.id}">
          <td class="py-3 px-4">${o.client_order_id}</td>
          <td class="py-3 px-4">${o.side}</td>
          <td class="py-3 px-4">${o.symbol}</td>
          <td class="py-3 px-4">${o.quantity}</td>
          <td class="py-3 px-4 font-sans">${o.status}</td>
          <td class="py-3 px-4 text-gray-400">${o.broker_account_id ? String(o.broker_account_id).slice(0, 8) : "—"}</td>
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
      const clientId = await resolveDemoClientId();
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
