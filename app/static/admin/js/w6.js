/* Wave 6 Admin — Vultr infra form, mock backend badge, subscriptions */
(function () {
  function api() {
    return window.BrokerBridgeApi;
  }
  function notify(msg, isError) {
    if (typeof showNotification === "function") showNotification(msg, isError);
    else console.log(msg);
  }
  function errNotify(e) {
    const api = window.BrokerBridgeApi;
    const formatted =
      (api && typeof api.formatError === "function" && api.formatError(e)) ||
      e.displayMessage ||
      e.message ||
      String(e);
    notify(formatted, true);
  }
  async function ensureAuth() {
    if (!api().getToken()) throw new Error("Sign in required");
  }

  function toggleInfraFields() {
    const type = document.getElementById("w5-infra-type")?.value || "mock";
    const wrap = document.getElementById("w6-mock-backend-wrap");
    if (wrap) wrap.classList.toggle("hidden", type !== "mock");
  }

  async function loadInfraProvider() {
    await ensureAuth();
    const statusEl = document.getElementById("w5-infra-status");
    const badge = document.getElementById("w6-infra-backend-badge");
    const degradeEl = document.getElementById("w6-infra-degrade-banner");
    let row = null;
    try {
      row = await api().json("/admin/providers/infrastructure");
    } catch (e) {
      if (e.status !== 404 && e.error_code !== "NOT_FOUND") throw e;
    }
    if (row) {
      const cfg = row.config || {};
      const configured =
        cfg.mock_backend || (row.provider_type === "mock" ? "database" : null);
      const effective = row.effective_backend || configured;
      const label =
        row.provider_type === "mock" && configured
          ? `Active: mock (${configured}) v${row.version}`
          : `Active: ${row.provider_type} v${row.version}`;
      if (statusEl) statusEl.textContent = `${label} (secrets masked)`;
      if (badge) {
        if (row.provider_type === "mock") {
          const eff = effective || configured || "database";
          badge.textContent =
            row.degraded && configured && configured !== eff
              ? `Infra backend: mock/${configured} → ${eff} (degraded)`
              : `Infra backend: mock/${eff}`;
        } else {
          badge.textContent = `Infra backend: ${row.provider_type}`;
        }
      }
      if (degradeEl) {
        if (row.degraded && row.degrade_message) {
          degradeEl.classList.remove("hidden");
          degradeEl.innerHTML =
            `<strong>Docker mock unavailable</strong> — running <span class="font-mono">database</span> fallback. ${row.degrade_message}`;
        } else {
          degradeEl.classList.add("hidden");
          degradeEl.innerHTML = "";
        }
      }
      const typeEl = document.getElementById("w5-infra-type");
      if (typeEl) typeEl.value = row.provider_type || "mock";
      const be = document.getElementById("w6-infra-mock-backend");
      if (be && configured) be.value = configured;
      const region = document.getElementById("w6-infra-region");
      if (region && (cfg.default_region || cfg.region)) {
        region.value = cfg.default_region || cfg.region;
      }
    } else if (statusEl) {
      statusEl.textContent = "No active DB infra provider — env / mock default";
      if (degradeEl) {
        degradeEl.classList.add("hidden");
        degradeEl.innerHTML = "";
      }
    }
    toggleInfraFields();
  }

  async function activateInfraProvider(validateFirst) {
    await ensureAuth();
    const providerType = document.getElementById("w5-infra-type")?.value || "mock";
    const apiKey = document.getElementById("w5-infra-api-key")?.value || "";
    const region = document.getElementById("w6-infra-region")?.value || "";
    const mockBackend = document.getElementById("w6-infra-mock-backend")?.value || "database";
    const config = {};
    if (apiKey) config.api_key = apiKey;
    if (region) config.default_region = region;
    if (providerType === "mock") config.mock_backend = mockBackend;
    try {
      const row = await api().json("/admin/providers/infrastructure", {
        method: "PUT",
        body: JSON.stringify({
          provider_type: providerType,
          validate_first: Boolean(validateFirst),
          activate: true,
          config,
        }),
      });
      notify(`Infra provider activated: ${row.provider_type} v${row.version}`);
      const keyEl = document.getElementById("w5-infra-api-key");
      if (keyEl) keyEl.value = "";
      await loadInfraProvider();
    } catch (e) {
      errNotify(e);
    }
  }

  let cachedSubs = [];
  let filtersBound = false;

  function F() {
    return window.AdminFilters;
  }

  function setText(id, v) {
    const el = document.getElementById(id);
    if (el) el.textContent = v;
  }

  function bindFiltersOnce() {
    if (filtersBound || !F()) return;
    filtersBound = true;
    F().bindStatCard(document.getElementById("w6-subs-kpi-active"), "clients", "active", () => renderSubscriptions());
    F().bindStatCard(document.getElementById("w6-subs-kpi-expired"), "clients", "expired", () => renderSubscriptions());
  }

  function coversNow(r) {
    if (!r || String(r.status).toLowerCase() !== "active") return false;
    if (r.teardown_completed_at) return false;
    const now = Date.now();
    const starts = Date.parse(r.starts_at);
    const ends = Date.parse(r.ends_at);
    if (Number.isNaN(starts) || Number.isNaN(ends)) return false;
    return starts <= now && now <= ends;
  }

  async function loadSubscriptions() {
    await ensureAuth();
    bindFiltersOnce();
    const payload = await api().json("/subscriptions?limit=50&offset=0");
    cachedSubs = payload.items || payload || [];
    if (!Array.isArray(cachedSubs)) cachedSubs = [];
    const covering = cachedSubs.filter(coversNow).length;
    const labeledActive = cachedSubs.filter((r) => r.status === "active").length;
    setText("w6-subs-active", String(covering));
    setText("w6-subs-expired", String(cachedSubs.filter((r) => r.status === "expired").length));
    const activeKpiHint = document.querySelector("#w6-subs-kpi-active .text-\\[10px\\]");
    if (activeKpiHint) {
      activeKpiHint.textContent =
        labeledActive > covering
          ? `Covering now · ${labeledActive - covering} labeled active but outside window`
          : "Covering now · click to filter · again to clear";
    }
    if (F()) F().applySeed("clients", () => renderSubscriptions());
    renderSubscriptions();
  }

  function renderSubscriptions() {
    const tbody = document.getElementById("w6-subs-tbody");
    if (!tbody) return;
    const filter = F() ? F().get("clients") : null;
    if (F()) {
      F().syncCardStyles("clients");
      F().updateChip("clients");
    }
    const rows = filter
      ? filter === "active"
        ? cachedSubs.filter(coversNow)
        : cachedSubs.filter((r) => r.status === filter)
      : cachedSubs;
    if (!cachedSubs.length) {
      tbody.innerHTML = `<tr><td colspan="7" class="py-6 px-4 text-center text-gray-500">No subscriptions yet. Create one for the demo client.</td></tr>`;
      return;
    }
    if (!rows.length) {
      tbody.innerHTML = `<tr><td colspan="7" class="py-6 px-4 text-center text-gray-500">No subscriptions match filter.</td></tr>`;
      return;
    }
    tbody.innerHTML = rows
      .map((r) => {
        const fmt = (v) =>
          api().formatTs
            ? api().formatTs(v)
            : String(v || "").replace("T", " ").slice(0, 19) || "—";
        const starts = fmt(r.starts_at);
        const ends = fmt(r.ends_at);
        const created = fmt(r.created_at);
        const live = coversNow(r);
        const st =
          live
            ? "text-emerald-400"
            : r.status === "active"
              ? "text-amber-400"
              : r.status === "expired"
                ? "text-rose-400"
                : "text-gray-400";
        const statusLabel = live
          ? "ACTIVE"
          : r.status === "active"
            ? "ACTIVE (outside window)"
            : String(r.status || "").toUpperCase();
        const copyBtn = api().copyButtonHtml
          ? api().copyButtonHtml(r.client_id, "Copy client UUID")
          : "";
        return `<tr class="hover:bg-white/5">
              <td class="py-2.5 px-4 font-mono text-[10px]">
                <span class="inline-flex items-center gap-1.5 max-w-full">
                  <span class="truncate" title="${r.client_id}">${r.client_id}</span>
                  ${copyBtn}
                </span>
              </td>
              <td class="py-2.5 px-4 ${st} font-semibold uppercase text-[10px]" title="${live ? "Trading allowed for this window" : "No covering window — trading blocked if no other ACTIVE coverage"}">${statusLabel}</td>
              <td class="py-2.5 px-4 text-gray-400 whitespace-nowrap">${starts}</td>
              <td class="py-2.5 px-4 text-gray-400 whitespace-nowrap">${ends}</td>
              <td class="py-2.5 px-4 text-gray-400 whitespace-nowrap">${created}</td>
              <td class="py-2.5 px-4">${r.teardown_mode}</td>
              <td class="py-2.5 px-4 text-right">
                ${
                  r.status === "active"
                    ? `<button onclick="window.W6Admin.expireSubscription('${r.id}')" class="px-2 py-1 rounded bg-rose-600/30 hover:bg-rose-600/50 text-rose-100 text-[10px] font-semibold">Expire</button>`
                    : "—"
                }
              </td>
            </tr>`;
      })
      .join("");
  }

  async function createSubscription() {
    await ensureAuth();
    const brokers = await api().json("/brokers?limit=1&offset=0");
    const items = brokers.items || [];
    if (!items.length) {
      notify("No brokers/clients seeded", true);
      return;
    }
    const clientId = items[0].client_id;
    const now = new Date();
    const ends = new Date(now.getTime() + 7 * 24 * 3600 * 1000);
    await api().json("/subscriptions", {
      method: "POST",
      body: JSON.stringify({
        client_id: clientId,
        starts_at: now.toISOString(),
        ends_at: ends.toISOString(),
        teardown_mode: "SUSPEND",
      }),
    });
    notify("Subscription created (7-day window) — trading restored if client was suspended");
    await loadSubscriptions();
  }

  async function expireSubscription(id) {
    await ensureAuth();
    await api().json(`/subscriptions/${id}/expire`, { method: "POST", body: "{}" });
    notify("Subscription expired + teardown enforced");
    await loadSubscriptions();
  }

  async function enforceExpiry() {
    await ensureAuth();
    const stats = await api().json("/subscriptions/enforce-expiry", { method: "POST", body: "{}" });
    notify(`Enforce expiry: expired=${stats.expired} torn_down=${stats.instances_torn_down}`);
    await loadSubscriptions();
  }

  window.W6Admin = {
    toggleInfraFields,
    loadInfraProvider,
    activateInfraProvider,
    loadSubscriptions,
    createSubscription,
    expireSubscription,
    enforceExpiry,
  };

  // Prefer W6 infra handlers over W5 stubs
  if (window.W5Admin) {
    window.W5Admin.loadInfraProvider = loadInfraProvider;
    window.W5Admin.activateInfraProvider = activateInfraProvider;
  }

  const origNavigate = window.navigateTo;
  if (typeof origNavigate === "function") {
    window.navigateTo = function (pageId) {
      origNavigate(pageId);
      if (pageId === "clients") loadSubscriptions().catch(errNotify);
      if (pageId === "config") loadInfraProvider().catch(errNotify);
    };
  }

  document.addEventListener("bb:auth-ready", () => {
    toggleInfraFields();
  });
})();
