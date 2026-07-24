/* Admin ops — Dashboard, Replay, Simulator, Runtime Config polish, list pagination */
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

  const pageState = {
    events: { limit: 25, offset: 0 },
    brokers: { limit: 25, offset: 0 },
    ips: { limit: 25, offset: 0 },
    sessions: { limit: 25, offset: 0 },
    orders: { limit: 25, offset: 0 },
    failovers: { limit: 25, offset: 0 },
  };

  async function ensureAuth() {
    if (!api().getToken()) {
      notify("Sign in required");
      if (window.BrokerBridgeAuth) window.BrokerBridgeAuth.applyAuthState();
      throw new Error("Not authenticated");
    }
  }

  function renderPager(elId, stateKey, onChange) {
    const el = document.getElementById(elId);
    if (!el) return;
    const st = pageState[stateKey];
    const total = st.total || 0;
    const limit = st.limit || 25;
    const offset = st.offset || 0;
    const page = Math.floor(offset / limit) + 1;
    const pages = Math.max(1, Math.ceil(total / limit));
    const prevDisabled = offset <= 0 ? "opacity-40 pointer-events-none" : "";
    const nextDisabled = offset + limit >= total ? "opacity-40 pointer-events-none" : "";
    el.innerHTML = `
      <div class="flex flex-wrap items-center justify-between gap-2 text-xs text-gray-400 px-4 py-3 border-t border-white/10">
        <div>Showing ${total ? offset + 1 : 0}–${Math.min(offset + limit, total)} of <span class="text-white">${total}</span></div>
        <div class="flex items-center gap-2">
          <label class="flex items-center gap-1">Page size
            <select data-pager-limit class="bg-dark-800 border border-white/10 rounded px-2 py-1 text-white">
              ${[25, 50, 100].map((n) => `<option value="${n}" ${n === limit ? "selected" : ""}>${n}</option>`).join("")}
            </select>
          </label>
          <button data-pager-prev class="px-2 py-1 bg-dark-700 rounded ${prevDisabled}">Prev</button>
          <span class="font-mono text-gray-300">${page}/${pages}</span>
          <button data-pager-next class="px-2 py-1 bg-dark-700 rounded ${nextDisabled}">Next</button>
        </div>
      </div>`;
    el.querySelector("[data-pager-limit]")?.addEventListener("change", (e) => {
      st.limit = Number(e.target.value) || 25;
      st.offset = 0;
      onChange();
    });
    el.querySelector("[data-pager-prev]")?.addEventListener("click", () => {
      st.offset = Math.max(0, offset - limit);
      onChange();
    });
    el.querySelector("[data-pager-next]")?.addEventListener("click", () => {
      if (offset + limit < total) {
        st.offset = offset + limit;
        onChange();
      }
    });
  }

  const STATUS_STYLE = {
    SUBMITTED: { icon: "fa-paper-plane", color: "text-emerald-400", bg: "bg-emerald-500/15 border-emerald-500/30" },
    ACCEPTED: { icon: "fa-circle-check", color: "text-blue-400", bg: "bg-blue-500/15 border-blue-500/30" },
    FILLED: { icon: "fa-check-double", color: "text-emerald-300", bg: "bg-emerald-500/15 border-emerald-500/30" },
    PARTIAL: { icon: "fa-chart-simple", color: "text-cyan-400", bg: "bg-cyan-500/15 border-cyan-500/30" },
    CREATED: { icon: "fa-plus", color: "text-amber-400", bg: "bg-amber-500/15 border-amber-500/30" },
    PENDING: { icon: "fa-clock", color: "text-amber-300", bg: "bg-amber-500/15 border-amber-500/30" },
    INDOUBT: { icon: "fa-circle-question", color: "text-orange-400", bg: "bg-orange-500/15 border-orange-500/30" },
    CANCELLED: { icon: "fa-ban", color: "text-rose-400", bg: "bg-rose-500/15 border-rose-500/30" },
    REJECTED: { icon: "fa-xmark", color: "text-rose-300", bg: "bg-rose-500/15 border-rose-500/30" },
    FAILED: { icon: "fa-triangle-exclamation", color: "text-rose-400", bg: "bg-rose-500/15 border-rose-500/30" },
    EXPIRED: { icon: "fa-hourglass-end", color: "text-gray-400", bg: "bg-white/5 border-white/10" },
    valid: { icon: "fa-shield-halved", color: "text-emerald-400", bg: "bg-emerald-500/15 border-emerald-500/30" },
    VALID: { icon: "fa-shield-halved", color: "text-emerald-400", bg: "bg-emerald-500/15 border-emerald-500/30" },
    invalid: { icon: "fa-shield", color: "text-rose-400", bg: "bg-rose-500/15 border-rose-500/30" },
    INVALID: { icon: "fa-shield", color: "text-rose-400", bg: "bg-rose-500/15 border-rose-500/30" },
    allocated: { icon: "fa-network-wired", color: "text-blue-400", bg: "bg-blue-500/15 border-blue-500/30" },
    ALLOCATED: { icon: "fa-network-wired", color: "text-blue-400", bg: "bg-blue-500/15 border-blue-500/30" },
    assigned: { icon: "fa-link", color: "text-indigo-400", bg: "bg-indigo-500/15 border-indigo-500/30" },
    ASSIGNED: { icon: "fa-link", color: "text-indigo-400", bg: "bg-indigo-500/15 border-indigo-500/30" },
    attached: { icon: "fa-plug", color: "text-cyan-400", bg: "bg-cyan-500/15 border-cyan-500/30" },
    ATTACHED: { icon: "fa-plug", color: "text-cyan-400", bg: "bg-cyan-500/15 border-cyan-500/30" },
    released: { icon: "fa-unlock", color: "text-gray-400", bg: "bg-white/5 border-white/10" },
    RELEASED: { icon: "fa-unlock", color: "text-gray-400", bg: "bg-white/5 border-white/10" },
    available: { icon: "fa-circle-check", color: "text-emerald-400", bg: "bg-emerald-500/15 border-emerald-500/30" },
    AVAILABLE: { icon: "fa-circle-check", color: "text-emerald-400", bg: "bg-emerald-500/15 border-emerald-500/30" },
    healthy: { icon: "fa-heart-pulse", color: "text-emerald-400", bg: "bg-emerald-500/15 border-emerald-500/30" },
    degraded: { icon: "fa-heart", color: "text-amber-400", bg: "bg-amber-500/15 border-amber-500/30" },
    down: { icon: "fa-heart-crack", color: "text-rose-400", bg: "bg-rose-500/15 border-rose-500/30" },
    ready: { icon: "fa-circle-check", color: "text-emerald-400", bg: "bg-emerald-500/15 border-emerald-500/30" },
    not_ready: { icon: "fa-circle-xmark", color: "text-rose-400", bg: "bg-rose-500/15 border-rose-500/30" },
  };

  function statusStyle(key) {
    return (
      STATUS_STYLE[key] ||
      STATUS_STYLE[String(key || "").toUpperCase()] ||
      STATUS_STYLE[String(key || "").toLowerCase()] || {
        icon: "fa-circle",
        color: "text-gray-300",
        bg: "bg-white/5 border-white/10",
      }
    );
  }

  function statusPills(map) {
    const entries = Object.entries(map || {});
    if (!entries.length) {
      return `<span class="text-[11px] text-gray-500">none</span>`;
    }
    return `<div class="flex flex-wrap gap-1.5 mt-2">${entries
      .map(([k, v]) => {
        const st = statusStyle(k);
        return `<span class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md border text-[11px] ${st.bg}">
          <i class="fa-solid ${st.icon} ${st.color} text-[10px]"></i>
          <span class="text-gray-300 uppercase tracking-wide">${k}</span>
          <span class="font-mono text-white font-semibold">${v}</span>
        </span>`;
      })
      .join("")}</div>`;
  }

  function kpiCard({ label, value, subHtml, icon, iconColor }) {
    return `
      <div class="glass-panel rounded-xl p-4">
        <div class="flex items-start justify-between gap-2">
          <div class="text-[11px] text-gray-400 uppercase tracking-wider">${label}</div>
          <div class="w-8 h-8 rounded-lg bg-white/5 flex items-center justify-center shrink-0">
            <i class="fa-solid ${icon} ${iconColor || "text-blue-400"}"></i>
          </div>
        </div>
        <div class="text-2xl font-semibold text-white mt-1 font-mono">${value}</div>
        ${subHtml || ""}
      </div>`;
  }

  function renderDashboardInto(root, d) {
    const activeFaults = d.simulator?.active_faults || [];
    const faultPills = activeFaults.length
      ? `<div class="flex flex-wrap gap-1.5 mt-2">${activeFaults
          .map(
            (f) => `<span class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md border bg-rose-500/15 border-rose-500/30 text-[11px]">
            <i class="fa-solid fa-bug text-rose-400 text-[10px]"></i>
            <span class="text-rose-200 font-mono">${f.id || f}</span>
          </span>`,
          )
          .join("")}</div>`
      : `<div class="text-[11px] text-gray-500 mt-2">No active faults</div>`;

    const ready = String(d.health?.ready || "—");
    const readySt = statusStyle(ready === "ok" || ready === "ready" ? "ready" : "not_ready");
    const pressure = Number(d.rate_limits?.max_pressure || 0);
    const pressureColor =
      pressure >= 0.8 ? "text-rose-400" : pressure >= 0.4 ? "text-amber-400" : "text-emerald-400";
    const redisSt = String(d.health?.redis?.status || "—");
    const pgSt = String(d.health?.postgres?.status || "—");
    const depPill = (label, st, icon) => {
      const bad = st === "fail" || st === "not_ok";
      const cls = bad
        ? "bg-rose-500/15 border-rose-500/40 text-rose-200"
        : "bg-white/5 border-white/10 text-gray-300";
      const iconCls = bad ? "text-rose-400" : label === "redis" ? "text-red-400" : "text-blue-400";
      return `<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-md border text-[11px] ${cls}"><i class="fa-solid ${icon} ${iconCls}"></i> ${label} ${st}</span>`;
    };
    const rateUnavailable = d.rate_limits?.unavailable
      ? `<div class="text-[11px] text-rose-300 mt-1">${d.rate_limits.unavailable}</div>`
      : "";

    root.innerHTML = `
      <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
        ${kpiCard({
          label: "Orders",
          value: d.orders_total ?? 0,
          icon: "fa-bolt",
          iconColor: "text-amber-400",
          subHtml: `<div class="text-[11px] text-gray-500 mt-1">inflight ${d.engine?.inflight ?? 0}/${d.engine?.max_inflight ?? "—"}</div>`,
        })}
        ${kpiCard({
          label: "Sessions",
          value: d.sessions?.total ?? 0,
          icon: "fa-key",
          iconColor: "text-yellow-400",
          subHtml: statusPills(d.sessions?.by_status),
        })}
        ${kpiCard({
          label: "Static IPs",
          value: d.static_ips?.total ?? 0,
          icon: "fa-network-wired",
          iconColor: "text-indigo-400",
          subHtml: statusPills(d.static_ips?.by_status),
        })}
        ${kpiCard({
          label: "Failovers",
          value: d.failovers?.total ?? 0,
          icon: "fa-shuffle",
          iconColor: "text-rose-400",
          subHtml: `<div class="text-[11px] text-gray-500 mt-1">lifetime count</div>`,
        })}
      </div>
      <div class="grid grid-cols-1 md:grid-cols-3 gap-3 mt-3">
        ${kpiCard({
          label: "Ready",
          value: ready === "ok" ? "ok" : ready,
          icon: readySt.icon,
          iconColor: readySt.color,
          subHtml: `<div class="flex flex-wrap gap-1.5 mt-2">
            ${depPill("pg", pgSt, "fa-database")}
            ${depPill("redis", redisSt, "fa-memory")}
          </div>`,
        })}
        ${kpiCard({
          label: "Event bus",
          value: d.events?.buffered ?? 0,
          icon: "fa-stream",
          iconColor: "text-teal-400",
          subHtml: `<div class="text-[11px] text-gray-500 mt-1">last ${d.events?.last_event_at || "—"} · ${d.events?.source || "empty"}</div>`,
        })}
        ${kpiCard({
          label: "Rate pressure",
          value: pressure.toFixed(2),
          icon: "fa-gauge-high",
          iconColor: pressureColor,
          subHtml: `${faultPills}${rateUnavailable}`,
        })}
      </div>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-3 mt-3">
        <div class="glass-panel rounded-xl p-4">
          <div class="flex items-center gap-2 text-xs text-gray-400 mb-3">
            <i class="fa-solid fa-heart-pulse text-rose-400"></i>
            <span>Broker health summary</span>
          </div>
          ${statusPills(d.broker_health?.statuses)}
        </div>
        <div class="glass-panel rounded-xl p-4">
          <div class="flex items-center gap-2 text-xs text-gray-400 mb-3">
            <i class="fa-solid fa-gears text-blue-400"></i>
            <span>Engine by status</span>
          </div>
          ${statusPills(d.engine?.by_status)}
        </div>
      </div>`;
  }

  let lastRedisOk = null;
  let dashPollTimer = null;

  function updateDepBanner(d) {
    const banner = document.getElementById("w5-dep-banner");
    if (!banner) return;
    const redis = d?.health?.redis;
    const redisFail = redis && redis.status !== "ok";
    const redisOk = !redisFail;
    if (lastRedisOk === true && redisFail) {
      notify("dependency redis down");
    } else if (lastRedisOk === false && redisOk) {
      notify("dependency redis recovered");
    }
    if (redis != null) lastRedisOk = redisOk;
    if (!redisFail) {
      banner.classList.add("hidden");
      banner.innerHTML = "";
      return;
    }
    const detail = redis.detail ? ` — ${redis.detail}` : "";
    banner.classList.remove("hidden");
    banner.innerHTML = `<i class="fa-solid fa-triangle-exclamation text-rose-400 mr-2"></i><strong>dependency redis down</strong>${detail}. Rate limits / session ensure / IP locks return <span class="font-mono">REDIS_UNAVAILABLE</span> (503). Compose: <span class="font-mono">docker compose start redis</span>`;
  }

  async function loadDashboard(rootIds, { silent } = {}) {
    await ensureAuth();
    const ids = Array.isArray(rootIds)
      ? rootIds
      : rootIds
        ? [rootIds]
        : ["w5-dashboard-root"];
    if (!silent) {
      ids.forEach((id) => {
        const el = document.getElementById(id);
        if (el) {
          el.innerHTML = `<div class="glass-panel rounded-xl p-8 text-center text-gray-500 text-xs">Loading live KPIs…</div>`;
        }
      });
    }
    const d = await api().json("/monitoring/dashboard");
    updateDepBanner(d);
    ids.forEach((id) => {
      const root = document.getElementById(id);
      if (root) renderDashboardInto(root, d);
    });
    if (!silent) {
      await loadFailoversPaged().catch(() => {});
    }
    return d;
  }

  function stopDashPoll() {
    if (dashPollTimer) {
      clearInterval(dashPollTimer);
      dashPollTimer = null;
    }
  }

  function startDashPoll() {
    stopDashPoll();
    dashPollTimer = setInterval(() => {
      const dash = document.getElementById("page-dashboard");
      if (!dash || dash.classList.contains("hidden") || !api().getToken()) return;
      loadDashboard("w5-dashboard-root", { silent: true }).catch(() => {});
    }, 5000);
  }

  function renderReplayStats(data) {
    const root = document.getElementById("w5-replay-stats");
    if (!root) return;
    const cards = [
      { key: "scanned", label: "Scanned", icon: "fa-magnifying-glass", color: "text-cyan-400", bg: "bg-cyan-500/15 border-cyan-500/30" },
      { key: "recovered", label: "Recovered", icon: "fa-circle-check", color: "text-emerald-400", bg: "bg-emerald-500/15 border-emerald-500/30" },
      { key: "skipped", label: "Skipped", icon: "fa-forward", color: "text-amber-400", bg: "bg-amber-500/15 border-amber-500/30" },
      { key: "failed", label: "Failed", icon: "fa-triangle-exclamation", color: "text-rose-400", bg: "bg-rose-500/15 border-rose-500/30" },
    ];
    root.innerHTML = cards
      .map((c) => {
        const val = data && data[c.key] != null ? data[c.key] : "—";
        return `<div class="glass-panel rounded-xl p-4 border ${c.bg}">
          <div class="flex items-start justify-between gap-2">
            <div class="text-[11px] text-gray-400 uppercase tracking-wider">${c.label}</div>
            <div class="w-8 h-8 rounded-lg bg-white/5 flex items-center justify-center shrink-0">
              <i class="fa-solid ${c.icon} ${c.color}"></i>
            </div>
          </div>
          <div class="text-2xl font-semibold text-white mt-1 font-mono">${val}</div>
        </div>`;
      })
      .join("");
    const detail = document.getElementById("w5-replay-detail");
    if (detail) detail.textContent = data ? JSON.stringify(data, null, 2) : "—";
  }

  async function runReplay() {
    await ensureAuth();
    const result = await api().json("/admin/replay/run?limit=50", { method: "POST", body: "{}" });
    renderReplayStats(result);
    notify(`Replay scanned=${result.scanned} recovered=${result.recovered} skipped=${result.skipped}`);
    await loadReplayStatus();
  }

  async function loadReplayStatus() {
    await ensureAuth();
    const st = await api().json("/admin/replay/status");
    // Prefer last_run counts when present; otherwise show status envelope on cards
    const stats = st.last_run || st.last_result || st;
    renderReplayStats(stats);
  }

  async function loadSim() {
    await ensureAuth();
    const faults = await api().json("/admin/sim/faults");
    const root = document.getElementById("w5-sim-faults");
    if (!root) return;
    root.innerHTML = faults
      .map(
        (f) => `
      <div class="glass-panel rounded-xl p-4 flex items-start justify-between gap-3 ${f.enabled ? "border border-rose-500/40" : ""}">
        <div class="min-w-0">
          <div class="flex flex-wrap items-center gap-2">
            <div class="text-sm text-white font-medium">${f.label}</div>
            ${
              f.enabled
                ? `<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-md border bg-rose-500/20 border-rose-500/40 text-[10px] text-rose-200 uppercase tracking-wide">Active now</span>`
                : `<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-md border bg-white/5 border-white/10 text-[10px] text-gray-500 uppercase tracking-wide">Off</span>`
            }
          </div>
          <div class="text-[11px] text-gray-500 font-mono mt-1">${f.id} · ${f.target} · ${f.code || ""}</div>
          <div class="text-[11px] text-gray-400 mt-2 leading-relaxed">${f.affects || "Affects mock provider paths while enabled."}</div>
        </div>
        <button data-fault="${f.id}" data-enabled="${f.enabled ? "0" : "1"}"
          class="shrink-0 px-3 py-1.5 rounded text-xs font-semibold ${f.enabled ? "bg-rose-600 hover:bg-rose-500 text-white" : "bg-dark-700 hover:bg-white/10 text-gray-200"}">
          ${f.enabled ? "Disable" : "Enable"}
        </button>
      </div>`,
      )
      .join("");
    root.querySelectorAll("button[data-fault]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        try {
          await ensureAuth();
          const enabling = btn.getAttribute("data-enabled") === "1";
          const faultId = btn.getAttribute("data-fault");
          await api().json("/admin/sim/faults", {
            method: "POST",
            body: JSON.stringify({
              fault_id: faultId,
              enabled: enabling,
            }),
          });
          notify(
            enabling
              ? `Fault ${faultId} ACTIVE — Orders / Health / allocate now affected`
              : `Fault ${faultId} disabled — providers recovered`,
          );
          await loadSim();
          await loadDashboard();
        } catch (e) {
          errNotify(e);
        }
      });
    });
    const links = document.getElementById("w5-sim-links");
    if (links) {
      if (faults.some((f) => f.enabled)) links.classList.remove("hidden");
      else links.classList.add("hidden");
    }
  }

  async function clearSim() {
    await ensureAuth();
    await api().json("/admin/sim/faults/clear", { method: "POST", body: "{}" });
    notify("All faults cleared — providers recovered");
    await loadSim();
    await loadDashboard();
  }

  async function loadAudit() {
    await ensureAuth();
    const payload = await api().json("/admin/sim/history?limit=50&offset=0");
    const rows = api().asItems(payload);
    const tbody = document.getElementById("w5-audit-tbody");
    const hint = document.getElementById("w5-audit-hint");
    if (hint) {
      hint.textContent = "Simulator toggle history (ops activity). Full SOC2 audit warehouse lands later.";
    }
    if (!tbody) return;
    tbody.innerHTML = rows.length
      ? rows
          .map((r) => {
            const when = String(r.at || "").replace("T", " ").slice(0, 19);
            const action = r.action || "—";
            const color =
              action === "enable"
                ? "text-rose-400"
                : action === "disable" || action === "cleared"
                  ? "text-emerald-400"
                  : "text-amber-400";
            return `<tr class="hover:bg-white/5">
              <td class="py-2.5 px-4 text-gray-400">${when}</td>
              <td class="py-2.5 px-4 ${color} font-semibold uppercase text-[10px] tracking-wider">${action}</td>
              <td class="py-2.5 px-4 font-mono text-white">${r.fault_id || "—"}</td>
              <td class="py-2.5 px-4 text-gray-400">chaos simulator</td>
            </tr>`;
          })
          .join("")
      : `<tr><td colspan="4" class="py-6 px-4 text-center text-gray-500">No simulator activity yet. Enable a fault on Simulator.</td></tr>`;
  }

  async function loadInfraProvider() {
    await ensureAuth();
    const statusEl = document.getElementById("w5-infra-status");
    let row = null;
    try {
      row = await api().json("/admin/providers/infrastructure");
    } catch (e) {
      if (e.status !== 404 && e.error_code !== "NOT_FOUND") throw e;
    }
    if (row) {
      if (statusEl) statusEl.textContent = `Active: ${row.provider_type} v${row.version} (secrets masked)`;
      const typeEl = document.getElementById("w5-infra-type");
      if (typeEl) typeEl.value = row.provider_type || "mock";
    } else if (statusEl) {
      statusEl.textContent = "No active DB infra provider — env / mock default";
    }
  }

  async function activateInfraProvider(validateFirst) {
    await ensureAuth();
    const providerType = document.getElementById("w5-infra-type")?.value || "mock";
    const apiKey = document.getElementById("w5-infra-api-key")?.value || "";
    const config = {};
    if (apiKey) config.api_key = apiKey;
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
  }

  async function loadBrokerProvider() {
    await ensureAuth();
    const statusEl = document.getElementById("w5-broker-status");
    let row = null;
    try {
      row = await api().json("/admin/providers/broker_default");
    } catch (e) {
      if (e.status !== 404 && e.error_code !== "NOT_FOUND") throw e;
    }
    if (row) {
      if (statusEl) statusEl.textContent = `Active: ${row.provider_type} v${row.version} (secrets masked)`;
      const typeEl = document.getElementById("w5-broker-type");
      if (typeEl) typeEl.value = row.provider_type || "mock";
    } else if (statusEl) {
      statusEl.textContent = "No active DB broker provider — env / mock default";
    }
  }

  async function activateBrokerProvider(validateFirst) {
    await ensureAuth();
    const providerType = document.getElementById("w5-broker-type")?.value || "mock";
    const apiKey = document.getElementById("w5-broker-api-key")?.value || "";
    const apiSecret = document.getElementById("w5-broker-api-secret")?.value || "";
    const config = {};
    if (apiKey) config.api_key = apiKey;
    if (apiSecret) config.api_secret = apiSecret;
    const row = await api().json("/admin/providers/broker_default", {
      method: "PUT",
      body: JSON.stringify({
        provider_type: providerType,
        validate_first: Boolean(validateFirst),
        activate: true,
        config,
      }),
    });
    notify(`Broker provider activated: ${row.provider_type} v${row.version}`);
    ["w5-broker-api-key", "w5-broker-api-secret"].forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.value = "";
    });
    await loadBrokerProvider();
  }

  function eventPayloadCell(r) {
    const p = r.payload || {};
    const chips = [];
    if (p.code) chips.push({ label: p.code, tone: "rose" });
    if (p.fault_id) chips.push({ label: p.fault_id, tone: "amber" });
    if (p.label) chips.push({ label: p.label, tone: "gray" });
    if (p.action) chips.push({ label: p.action, tone: "teal" });
    if (p.enabled === true) chips.push({ label: "enabled", tone: "rose" });
    if (p.enabled === false) chips.push({ label: "disabled", tone: "emerald" });
    const toneClass = {
      rose: "bg-rose-500/15 border-rose-500/30 text-rose-200",
      amber: "bg-amber-500/15 border-amber-500/30 text-amber-200",
      teal: "bg-teal-500/15 border-teal-500/30 text-teal-200",
      emerald: "bg-emerald-500/15 border-emerald-500/30 text-emerald-200",
      gray: "bg-white/5 border-white/10 text-gray-300",
    };
    const chipHtml = chips.length
      ? `<div class="flex flex-wrap gap-1 mb-1">${chips
          .map(
            (c) =>
              `<span class="inline-flex px-1.5 py-0.5 rounded border text-[10px] font-mono ${toneClass[c.tone] || toneClass.gray}">${String(c.label).slice(0, 40)}</span>`,
          )
          .join("")}</div>`
      : "";
    const raw = JSON.stringify(p);
    const short = raw.length > 100 ? `${raw.slice(0, 100)}…` : raw;
    return `${chipHtml}<details class="text-gray-500"><summary class="cursor-pointer text-[10px] text-gray-500 hover:text-gray-300">payload</summary><pre class="text-[10px] mt-1 whitespace-pre-wrap break-all">${short.replace(/</g, "&lt;")}</pre></details>`;
  }

  async function loadEventsPaged() {
    await ensureAuth();
    const st = pageState.events;
    const payload = await api().json(`/monitoring/events?limit=${st.limit}&offset=${st.offset}`);
    const rows = api().asItems(payload);
    Object.assign(st, api().pageMeta(payload, st.limit));
    if (window.W4Admin && W4Admin.renderEvents) W4Admin.renderEvents(rows);
    else {
      const tbody = document.getElementById("w4-events-tbody");
      if (tbody) {
        tbody.innerHTML = rows.length
          ? rows
              .map((r) => {
                const when = String(r.created_at || "").replace("T", " ").slice(0, 19);
                return `<tr class="hover:bg-white/5">
                  <td class="py-2.5 px-4 text-gray-400">${when}</td>
                  <td class="py-2.5 px-4 text-white">${r.event_type}</td>
                  <td class="py-2.5 px-4">${r.topic}</td>
                  <td class="py-2.5 px-4">${r.status}${r.source ? ` · ${r.source}` : ""}</td>
                  <td class="py-2.5 px-4 text-gray-400 max-w-xs">${eventPayloadCell(r)}</td>
                </tr>`;
              })
              .join("")
          : `<tr><td colspan="5" class="py-6 px-4 text-center text-gray-500">No events yet.</td></tr>`;
      }
    }
    const feed = rows[0]?.source === "consumed" ? "consumer-backed live" : rows.length ? "outbox fallback" : "empty";
    const statusEl = document.getElementById("w4-events-live-status");
    if (statusEl) statusEl.textContent = `Event Bus source: ${feed} · total=${st.total}`;
    renderPager("w5-events-pager", "events", () => loadEventsPaged().catch(errNotify));
  }

  async function loadFailoversPaged() {
    await ensureAuth();
    const st = pageState.failovers;
    const payload = await api().json(`/monitoring/failovers?limit=${st.limit}&offset=${st.offset}`);
    const rows = api().asItems(payload);
    Object.assign(st, api().pageMeta(payload, st.limit));
    const tbody = document.getElementById("w5-failovers-tbody");
    if (tbody) {
      tbody.innerHTML = rows.length
        ? rows
            .map(
              (r) => `<tr class="hover:bg-white/5">
            <td class="py-2 px-4 text-gray-400">${String(r.created_at || "").replace("T", " ").slice(0, 19)}</td>
            <td class="py-2 px-4">${r.reason}</td>
            <td class="py-2 px-4 font-mono text-[11px]">${String(r.from_broker_id || "").slice(0, 8)}</td>
            <td class="py-2 px-4 font-mono text-[11px]">${String(r.to_broker_id || "").slice(0, 8)}</td>
          </tr>`,
            )
            .join("")
        : `<tr><td colspan="4" class="py-6 px-4 text-center text-gray-500">No failover events.</td></tr>`;
    }
    renderPager("w5-failovers-pager", "failovers", () => loadFailoversPaged().catch(errNotify));
  }

  function wrapListLoader(original, stateKey, pathBuilder, after) {
    return async function () {
      await ensureAuth();
      const st = pageState[stateKey];
      const path = pathBuilder(st);
      const payload = await api().json(path);
      Object.assign(st, api().pageMeta(payload, st.limit));
      if (typeof original === "function") await original();
      if (typeof after === "function") after(payload);
    };
  }

  // Enhance existing table loaders with pager chrome when containers exist
  async function enhanceExistingPagination() {
    if (window.W2Admin?.loadBrokers) {
      const orig = W2Admin.loadBrokers.bind(W2Admin);
      W2Admin.loadBrokers = async function () {
        await ensureAuth();
        const st = pageState.brokers;
        cached = await api().json(`/brokers?limit=${st.limit}&offset=${st.offset}`);
        Object.assign(st, api().pageMeta(cached, st.limit));
        // Temporarily monkeypatch json for this call path via direct render using orig after forcing cache
        const _json = api().json.bind(api());
        api().json = async (path, opts) => {
          if (String(path).startsWith("/brokers") && !(opts && opts.method && opts.method !== "GET")) {
            return cached;
          }
          return _json(path, opts);
        };
        try {
          await orig();
        } finally {
          api().json = _json;
        }
        renderPager("w5-brokers-pager", "brokers", () => W2Admin.loadBrokers().catch(errNotify));
      };
    }
    if (window.W2Admin?.loadIps) {
      const orig = W2Admin.loadIps.bind(W2Admin);
      W2Admin.loadIps = async function () {
        await ensureAuth();
        const st = pageState.ips;
        const payload = await api().json(`/infrastructure/ips?limit=${st.limit}&offset=${st.offset}`);
        Object.assign(st, api().pageMeta(payload, st.limit));
        const _json = api().json.bind(api());
        api().json = async (path, opts) => {
          if (String(path).startsWith("/infrastructure/ips") && !(opts && opts.method)) {
            return payload;
          }
          return _json(path, opts);
        };
        try {
          await orig();
        } finally {
          api().json = _json;
        }
        renderPager("w5-ips-pager", "ips", () => W2Admin.loadIps().catch(errNotify));
      };
    }
    if (window.W2Admin?.loadSessions) {
      const orig = W2Admin.loadSessions.bind(W2Admin);
      W2Admin.loadSessions = async function () {
        await ensureAuth();
        const st = pageState.sessions;
        const payload = await api().json(`/monitoring/sessions?limit=${st.limit}&offset=${st.offset}`);
        Object.assign(st, api().pageMeta(payload, st.limit));
        const _json = api().json.bind(api());
        api().json = async (path, opts) => {
          if (String(path).startsWith("/monitoring/sessions")) return payload;
          return _json(path, opts);
        };
        try {
          await orig();
        } finally {
          api().json = _json;
        }
        renderPager("w5-sessions-pager", "sessions", () => W2Admin.loadSessions().catch(errNotify));
      };
    }
    if (window.W3Admin?.loadOrders) {
      const orig = W3Admin.loadOrders.bind(W3Admin);
      W3Admin.loadOrders = async function () {
        await ensureAuth();
        const st = pageState.orders;
        const payload = await api().json(`/orders?limit=${st.limit}&offset=${st.offset}`);
        Object.assign(st, api().pageMeta(payload, st.limit));
        const _json = api().json.bind(api());
        api().json = async (path, opts) => {
          if (String(path).startsWith("/orders") && !(opts && opts.method)) return payload;
          return _json(path, opts);
        };
        try {
          await orig();
        } finally {
          api().json = _json;
        }
        renderPager("w5-orders-pager", "orders", () => W3Admin.loadOrders().catch(errNotify));
      };
    }
  }

  let cached = null;

  const pageLoaders = {
    dashboard: () => loadDashboard("w5-dashboard-root"),
    replay: async () => {
      await loadReplayStatus();
    },
    simulator: loadSim,
    monitoring: async () => {
      // PRD §15 lists Monitoring separately; Admin consolidates into Dashboard.
      if (typeof window.navigateTo === "function") {
        /* redirected in navigateTo wrapper */
      }
      await loadDashboard("w5-dashboard-root");
    },
    events: loadEventsPaged,
    "audit-logs": loadAudit,
    config: async () => {
      if (window.W4Admin?.loadEventProvider) await W4Admin.loadEventProvider();
      await loadInfraProvider();
      await loadBrokerProvider();
    },
    brokers: async () => {
      if (window.W2Admin?.loadBrokers) await W2Admin.loadBrokers();
    },
    "static-ips": async () => {
      if (window.W2Admin?.loadIps) await W2Admin.loadIps();
    },
    sessions: async () => {
      if (window.W2Admin?.loadSessions) await W2Admin.loadSessions();
    },
    orders: async () => {
      if (window.W3Admin?.loadOrders) await W3Admin.loadOrders();
    },
  };

  enhanceExistingPagination();

  const _origNavigate = window.navigateTo;
  window.navigateTo = function (pageId) {
    if (pageId === "monitoring") pageId = "dashboard";
    if (typeof _origNavigate === "function") _origNavigate(pageId);
    if (pageId === "dashboard") startDashPoll();
    else stopDashPoll();
    const loader = pageLoaders[pageId];
    if (loader) loader().catch(errNotify);
  };

  window.W5Admin = {
    loadDashboard,
    runReplay,
    loadReplayStatus,
    loadSim,
    clearSim,
    loadAudit,
    loadInfraProvider,
    activateInfraProvider,
    loadBrokerProvider,
    activateBrokerProvider,
    loadEventsPaged,
    loadFailoversPaged,
    eventPayloadCell,
  };

  // Expose render helper for w4 compatibility
  if (window.W4Admin) {
    W4Admin.renderEvents = function (rows) {
      const tbody = document.getElementById("w4-events-tbody");
      if (!tbody) return;
      if (!rows || !rows.length) {
        tbody.innerHTML = `<tr><td colspan="5" class="py-6 px-4 text-center text-gray-500">No events yet.</td></tr>`;
        return;
      }
      tbody.innerHTML = rows
        .map((r) => {
          const when = String(r.created_at || "").replace("T", " ").slice(0, 19);
          const st =
            r.status === "sent" || r.status === "consumed"
              ? "text-emerald-400"
              : r.status === "error"
                ? "text-rose-400"
                : "text-amber-400";
          return `<tr class="hover:bg-white/5">
            <td class="py-2.5 px-4 text-gray-400">${when}</td>
            <td class="py-2.5 px-4 text-white">${r.event_type}</td>
            <td class="py-2.5 px-4">${r.topic}</td>
            <td class="py-2.5 px-4 ${st}">${r.status}${r.source ? ` · ${r.source}` : ""}</td>
            <td class="py-2.5 px-4 text-gray-400 max-w-xs">${eventPayloadCell(r)}</td>
          </tr>`;
        })
        .join("");
    };
  }

  // Auto-load Dashboard when shell is already visible (token present / post-login race)
  function bootDashboardIfVisible() {
    if (!api().getToken()) return;
    const dash = document.getElementById("page-dashboard");
    if (dash && !dash.classList.contains("hidden")) {
      loadDashboard("w5-dashboard-root").catch(errNotify);
      startDashPoll();
    }
  }
  bootDashboardIfVisible();
  document.addEventListener("bb:auth-ready", bootDashboardIfVisible);
})();
