/* Wave 2 Admin wiring — Brokers, Sessions, Static IPs, Whitelist */
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
  let cachedBrokers = [];
  let cachedIps = [];
  let cachedInstances = [];
  let cachedAssignByIp = {};
  let cachedSessionRows = [];
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
    F().bindStatCard(document.getElementById("w2-ip-kpi-available"), "static-ips", "available", () => renderIpsTable());
    F().bindStatCard(document.getElementById("w2-ip-kpi-attached"), "static-ips", "attached", () => renderIpsTable());
    F().bindStatCard(document.getElementById("w2-ip-kpi-released"), "static-ips", "released", () => renderIpsTable());
    F().bindStatCard(document.getElementById("w2-inst-kpi-running"), "infrastructure", "running", () => renderInstancesTables());
    F().bindStatCard(document.getElementById("w2-inst-kpi-suspended"), "infrastructure", "suspended", () => renderInstancesTables());
    F().bindStatCard(document.getElementById("w2-inst-kpi-destroyed"), "infrastructure", "destroyed", () => renderInstancesTables());
    F().bindStatCard(document.getElementById("w2-brokers-kpi-enabled"), "brokers", "enabled", () => renderBrokersTable());
    F().bindStatCard(document.getElementById("w2-brokers-kpi-disabled"), "brokers", "disabled", () => renderBrokersTable());
    F().bindStatCard(document.getElementById("w2-sess-kpi-valid"), "sessions", "valid", () => renderSessionsTable());
    F().bindStatCard(document.getElementById("w2-sess-kpi-missing"), "sessions", "missing", () => renderSessionsTable());
    F().bindStatCard(document.getElementById("w2-sess-kpi-other"), "sessions", "other", () => renderSessionsTable());

    const runNav = document.getElementById("w2-ip-kpi-instances");
    if (runNav) {
      const go = (e) => {
        e.preventDefault();
        if (typeof window.navigateTo === "function") window.navigateTo("infrastructure");
      };
      runNav.onclick = go;
      runNav.onkeydown = (e) => {
        if (e.key === "Enter" || e.key === " ") go(e);
      };
    }
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

  function capsHtml(caps) {
    if (!caps || typeof caps !== "object") return "—";
    const classes = caps.asset_classes || caps.order_types || [];
    return (Array.isArray(classes) ? classes : Object.keys(caps))
      .slice(0, 4)
      .map((c) => `<span class="text-gray-300 bg-white/5 px-1.5 py-0.5 rounded text-[10px]">${c}</span>`)
      .join(" ");
  }

  function statusBadge(enabled) {
    return enabled
      ? `<span class="text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded text-[11px] font-medium">ENABLED</span>`
      : `<span class="text-rose-400 bg-rose-500/10 px-2 py-0.5 rounded text-[11px] font-medium">DISABLED</span>`;
  }

  function fmtTs(value) {
    return api().formatTs ? api().formatTs(value) : value || "—";
  }

  function instanceStatusBadge(status) {
    const s = String(status || "").toLowerCase();
    if (s === "running") {
      return `<span class="bg-emerald-500/10 text-emerald-400 px-2 py-0.5 rounded text-[10px] font-bold">RUNNING</span>`;
    }
    if (s === "suspended") {
      return `<span class="bg-amber-500/10 text-amber-400 px-2 py-0.5 rounded text-[10px] font-bold">SUSPENDED</span>`;
    }
    if (s === "destroyed") {
      return `<span class="bg-rose-500/10 text-rose-400 px-2 py-0.5 rounded text-[10px] font-bold">DESTROYED</span>`;
    }
    return `<span class="bg-white/5 text-gray-300 px-2 py-0.5 rounded text-[10px] font-bold">${(status || "—").toUpperCase()}</span>`;
  }

  async function loadBrokers() {
    await ensureAuth();
    bindFiltersOnce();
    cachedBrokers = api().asItems(await api().json("/brokers?limit=100"));
    if (F()) F().applySeed("brokers", () => renderBrokersTable());
    const enabled = cachedBrokers.filter((b) => b.enabled).length;
    setText("w2-brokers-enabled", String(enabled));
    setText("w2-brokers-disabled", String(cachedBrokers.length - enabled));
    renderBrokersTable();
  }

  function renderBrokersTable() {
    const tbody = document.getElementById("w2-brokers-tbody");
    if (!tbody) return;
    const filter = F() ? F().get("brokers") : null;
    let rows = cachedBrokers;
    if (filter === "enabled") rows = rows.filter((b) => b.enabled);
    else if (filter === "disabled") rows = rows.filter((b) => !b.enabled);
    if (F()) {
      F().syncCardStyles("brokers");
      F().updateChip("brokers");
    }
    if (!cachedBrokers.length) {
      tbody.innerHTML = `<tr><td colspan="9" class="py-6 px-4 text-center text-gray-500">No brokers yet — connect one.</td></tr>`;
      return;
    }
    if (!rows.length) {
      tbody.innerHTML = `<tr><td colspan="9" class="py-6 px-4 text-center text-gray-500">No brokers match filter.</td></tr>`;
      return;
    }
    tbody.innerHTML = rows
      .map((b) => {
        const regions = (b.allowed_regions || []).join(", ") || "—";
        return `<tr class="hover:bg-white/5 transition" data-broker-id="${b.id}">
          <td class="py-3.5 px-4 font-sans font-semibold text-white">${b.display_name}</td>
          <td class="py-3.5 px-4 font-sans text-gray-300">${b.provider_type}</td>
          <td class="py-3.5 px-4"><span class="bg-blue-500/10 text-blue-400 px-2 py-0.5 rounded">P${b.priority}</span></td>
          <td class="py-3.5 px-4 font-sans">${capsHtml(b.capabilities)}</td>
          <td class="py-3.5 px-4 font-sans text-gray-400">${regions}</td>
          <td class="py-3.5 px-4 font-sans">${statusBadge(b.enabled)}</td>
          <td class="py-3.5 px-4 text-gray-400 whitespace-nowrap">${fmtTs(b.created_at)}</td>
          <td class="py-3.5 px-4 text-gray-400 whitespace-nowrap">${fmtTs(b.updated_at)}</td>
          <td class="py-3.5 px-4 text-right font-sans space-x-1 whitespace-nowrap">
            <button data-action="detail" class="px-2 py-1 bg-dark-700 hover:bg-white/10 rounded text-xs text-blue-400">Details</button>
            <button data-action="caps" class="px-2 py-1 bg-dark-700 hover:bg-white/10 rounded text-xs text-emerald-400" title="Refresh capabilities"><i class="fa-solid fa-plug"></i></button>
            <button data-action="toggle" class="px-2 py-1 bg-dark-700 hover:bg-white/10 rounded text-xs text-amber-400">${b.enabled ? "Disable" : "Enable"}</button>
            <button data-action="session" class="p-1 text-gray-400 hover:text-white" title="Ensure session"><i class="fa-solid fa-arrows-rotate"></i></button>
            <button data-action="whitelist" class="p-1 text-indigo-400 hover:text-indigo-300" title="Whitelist sync"><i class="fa-solid fa-list-check"></i></button>
          </td>
        </tr>`;
      })
      .join("");

    tbody.querySelectorAll("tr[data-broker-id]").forEach((tr) => {
      const id = tr.getAttribute("data-broker-id");
      tr.querySelectorAll("button[data-action]").forEach((btn) => {
        btn.addEventListener("click", () => handleBrokerAction(btn.getAttribute("data-action"), id));
      });
    });
  }

  async function handleBrokerAction(action, id) {
    try {
      await ensureAuth();
      if (action === "detail") {
        const b = await api().json(`/brokers/${id}`);
        const el = document.getElementById("w2-broker-detail-body");
        if (el) {
          el.textContent = JSON.stringify(
            {
              id: b.id,
              display_name: b.display_name,
              provider_type: b.provider_type,
              enabled: b.enabled,
              priority: b.priority,
              capabilities: b.capabilities,
              allowed_regions: b.allowed_regions,
              rate_limit_rps: b.rate_limit_rps,
            },
            null,
            2,
          );
          openModal("w2-broker-detail-modal");
        }
      } else if (action === "caps") {
        await api().json(`/brokers/${id}/capabilities/refresh`, { method: "POST", body: "{}" });
        notify("Capabilities refreshed");
        await loadBrokers();
      } else if (action === "toggle") {
        const b = cachedBrokers.find((x) => x.id === id);
        await api().json(`/brokers/${id}`, {
          method: "PATCH",
          body: JSON.stringify({ enabled: !(b && b.enabled) }),
        });
        notify(`Broker ${b && b.enabled ? "disabled" : "enabled"}`);
        await loadBrokers();
      } else if (action === "session") {
        await api().json(`/brokers/${id}/sessions/ensure`, { method: "POST", body: "{}" });
        notify("Session ensured");
        await loadSessions();
      } else if (action === "whitelist") {
        const result = await api().json(`/infrastructure/brokers/${id}/whitelist/sync`, {
          method: "POST",
          body: "{}",
        });
        showWhitelistFindings(result);
        notify(`Whitelist synced (${result.findings.length} findings)`);
      }
    } catch (e) {
      errNotify(e);
    }
  }

  function showWhitelistFindings(result) {
    const el = document.getElementById("w2-whitelist-body");
    if (!el) return;
    const rows = (result.findings || [])
      .map(
        (f) =>
          `<tr><td class="py-2 px-3 font-mono text-blue-400">${f.ip_address}</td>` +
          `<td class="py-2 px-3">${f.finding_type}</td>` +
          `<td class="py-2 px-3 text-gray-400">${JSON.stringify(f.details || {})}</td></tr>`,
      )
      .join("");
    el.innerHTML = `
      <div class="text-xs text-gray-400 mb-2">Format: <span class="text-white">${result.raw_format}</span> ·
        Normalized IPs: ${(result.normalized && result.normalized.ips) || []}</div>
      <table class="w-full text-left text-xs"><thead class="text-gray-400"><tr>
        <th class="py-2 px-3">IP</th><th class="py-2 px-3">Finding</th><th class="py-2 px-3">Details</th>
      </tr></thead><tbody>${rows || '<tr><td colspan="3" class="py-3 px-3 text-gray-500">No findings</td></tr>'}</tbody></table>`;
    openModal("w2-whitelist-modal");
  }

  async function createBroker() {
    try {
      await ensureAuth();
      const clientId = await resolveDemoClientId();
      const name = document.getElementById("w2-broker-name").value.trim();
      const provider = document.getElementById("w2-broker-provider").value;
      const apiKey = document.getElementById("w2-broker-api-key").value.trim() || "mock-key";
      if (!name) {
        notify("Display name required");
        return;
      }
      await api().json("/brokers", {
        method: "POST",
        body: JSON.stringify({
          client_id: clientId,
          provider_type: provider,
          display_name: name,
          priority: 50,
          enabled: true,
          allowed_regions: ["ewr"],
          credentials: { api_key: apiKey, api_secret: "mock-secret" },
          rate_limit_rps: 40,
        }),
      });
      closeModal("add-broker-modal");
      notify("Broker onboarded");
      await loadBrokers();
    } catch (e) {
      errNotify(e);
    }
  }

  async function loadSessions() {
    await ensureAuth();
    bindFiltersOnce();
    const sessions = api().asItems(await api().json("/monitoring/sessions?limit=100"));
    const brokers = cachedBrokers.length ? cachedBrokers : api().asItems(await api().json("/brokers?limit=100"));
    cachedBrokers = brokers;
    const byId = Object.fromEntries(sessions.map((s) => [s.broker_account_id, s]));
    cachedSessionRows = brokers.map((b) => {
      const s = byId[b.id];
      const status = s ? s.status : "missing";
      return { broker: b, session: s, status };
    });
    const valid = cachedSessionRows.filter((r) => r.status === "valid").length;
    const missing = cachedSessionRows.filter((r) => r.status === "missing").length;
    const other = cachedSessionRows.length - valid - missing;
    setText("w2-sess-valid", String(valid));
    setText("w2-sess-missing", String(missing));
    setText("w2-sess-other", String(other));
    if (F()) F().applySeed("sessions", () => renderSessionsTable());
    renderSessionsTable();
  }

  function renderSessionsTable() {
    const tbody = document.getElementById("w2-sessions-tbody");
    if (!tbody) return;
    const filter = F() ? F().get("sessions") : null;
    let rows = cachedSessionRows;
    if (filter === "valid") rows = rows.filter((r) => r.status === "valid");
    else if (filter === "missing") rows = rows.filter((r) => r.status === "missing");
    else if (filter === "other") rows = rows.filter((r) => r.status !== "valid" && r.status !== "missing");
    if (F()) {
      F().syncCardStyles("sessions");
      F().updateChip("sessions");
    }
    if (!cachedSessionRows.length) {
      tbody.innerHTML = `<tr><td colspan="7" class="py-6 px-4 text-center text-gray-500">No brokers</td></tr>`;
      return;
    }
    if (!rows.length) {
      tbody.innerHTML = `<tr><td colspan="7" class="py-6 px-4 text-center text-gray-500">No sessions match filter.</td></tr>`;
      return;
    }
    tbody.innerHTML = rows
      .map(({ broker: b, session: s, status }) => {
        const expires = s && s.expires_at ? fmtTs(s.expires_at) : "—";
        const updated = s && s.updated_at ? fmtTs(s.updated_at) : "—";
        const badge =
          status === "valid"
            ? `<span class="bg-emerald-500/10 text-emerald-400 px-2 py-0.5 rounded text-[10px] font-bold">VALID</span>`
            : `<span class="bg-amber-500/10 text-amber-400 px-2 py-0.5 rounded text-[10px] font-bold">${status.toUpperCase()}</span>`;
        return `<tr class="hover:bg-white/5 transition">
        <td class="py-3.5 px-4 font-sans font-bold text-white">${b.display_name}</td>
        <td class="py-3.5 px-4 text-blue-400 font-mono text-[10px]">${b.id.slice(0, 8)}…</td>
        <td class="py-3.5 px-4 text-gray-400">${s && s.has_tokens ? "(encrypted — not shown)" : "—"}</td>
        <td class="py-3.5 px-4 text-emerald-400 whitespace-nowrap">${expires}</td>
        <td class="py-3.5 px-4 text-gray-400 whitespace-nowrap">${updated}</td>
        <td class="py-3.5 px-4 font-sans">${badge}</td>
        <td class="py-3.5 px-4 text-right font-sans">
          <button data-broker-id="${b.id}" class="w2-session-refresh px-2 py-1 bg-blue-500/10 hover:bg-blue-500/20 text-blue-400 rounded text-xs">Ensure / Refresh</button>
        </td>
      </tr>`;
      })
      .join("");
    tbody.querySelectorAll(".w2-session-refresh").forEach((btn) => {
      btn.addEventListener("click", async () => {
        try {
          await api().json(`/brokers/${btn.getAttribute("data-broker-id")}/sessions/ensure?force_refresh=true`, {
            method: "POST",
            body: "{}",
          });
          notify("Session refreshed");
          await loadSessions();
        } catch (e) {
          errNotify(e);
        }
      });
    });
  }

  async function refreshAllSessions() {
    try {
      await ensureAuth();
      const brokers = api().asItems(await api().json("/brokers?limit=100"));
      for (const b of brokers) {
        await api().json(`/brokers/${b.id}/sessions/ensure`, { method: "POST", body: "{}" });
      }
      notify(`Ensured ${brokers.length} sessions`);
      await loadSessions();
    } catch (e) {
      errNotify(e);
    }
  }

  function escapeAttr(value) {
    return String(value || "")
      .replace(/&/g, "&amp;")
      .replace(/"/g, "&quot;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function instancePickerLabel(inst) {
    const short = (inst.external_id || "").replace(/^mock-inst-/, "").slice(0, 8);
    const name = inst.display_name || inst.label || `Lab Instance ${inst.region}-${short}`;
    return `${name} (${inst.region})`;
  }

  /** Status + assignment → which IP row actions are valid (invalid clicks toast reason). */
  function ipActionSpecs(ip, assignment) {
    const status = ip.status;
    const assigned = Boolean(assignment);
    const freePool = status === "allocated" || status === "detached";
    const attached = status === "attached";
    const released = status === "released";
    const quarantined = status === "quarantined";

    const assign = {
      action: "assign",
      label: assigned ? "Reassign" : "Assign",
      icon: assigned ? "fa-right-left" : "fa-link",
      enabled: false,
      reason: "",
      title: assigned ? "Reassign to another broker" : "Assign to a broker",
      className: "bg-indigo-500/10 text-indigo-400",
    };
    if (quarantined) {
      assign.reason = "IP is quarantined";
    } else if (attached) {
      assign.reason = "Detach before assigning to a broker";
    } else if (released) {
      assign.reason = "IP released — use Reuse-test to re-bind (BR-G04 may apply)";
    } else if (assigned) {
      assign.reason = "Release this IP before assigning to another broker";
    } else if (freePool) {
      assign.enabled = true;
    } else {
      assign.reason = `Cannot assign from status ${status}`;
    }

    const attach = {
      action: "attach",
      label: "Attach",
      icon: "fa-plug",
      enabled: false,
      reason: "",
      title: "Attach to an instance",
      className: "bg-emerald-500/10 text-emerald-400",
    };
    if (quarantined) {
      attach.reason = "IP is quarantined";
    } else if (attached) {
      attach.reason = "Already attached to an instance";
    } else if (released) {
      attach.reason = "Released IPs cannot be attached";
    } else if (!assigned) {
      attach.reason = "Assign to a broker before attaching";
    } else if (freePool) {
      attach.enabled = true;
    } else {
      attach.reason = `Cannot attach from status ${status}`;
    }

    const detach = {
      action: "detach",
      label: "Detach",
      icon: "fa-link-slash",
      enabled: attached,
      reason: attached ? "" : "Not attached to an instance",
      title: "Detach from instance",
      className: "bg-amber-500/10 text-amber-400",
    };

    const release = {
      action: "release",
      label: "Release",
      icon: "fa-circle-xmark",
      enabled: false,
      reason: "",
      title: "Release this IP",
      className: "bg-rose-500/10 text-rose-400",
    };
    if (attached) {
      release.reason = "Detach before release";
    } else if (released) {
      release.reason = "Already released";
    } else if (quarantined) {
      release.reason = "IP is quarantined";
    } else if (freePool) {
      release.enabled = true;
    } else {
      release.reason = `Cannot release from status ${status}`;
    }

    const reuse = {
      action: "reuse",
      label: "Reuse-test",
      icon: "fa-flask",
      enabled: released,
      reason: released
        ? "Re-assign same broker after release (expect BR-G04 during cooldown)"
        : "Available after release for BR-G04 cooldown testing",
      title: "Re-assign after release (BR-G04 cooldown test)",
      className: "bg-dark-700 text-gray-300",
    };

    const rotate = {
      action: "rotate",
      label: "Rotate",
      icon: "fa-arrows-rotate",
      enabled: Boolean(assigned && assignment && assignment.broker_account_id),
      reason: assigned ? "" : "Assign to a broker before rotating",
      title: "Zero-downtime IP rotate for assigned broker",
      className: "bg-violet-500/10 text-violet-300",
      brokerId: assigned && assignment ? assignment.broker_account_id : null,
    };

    return [assign, attach, detach, release, reuse, rotate];
  }

  function renderActionButton(spec) {
    const tip = spec.enabled ? spec.title || spec.label : spec.reason || spec.title || spec.label;
    const title = tip ? ` title="${escapeAttr(tip)}"` : "";
    const reasonAttr = spec.reason ? ` data-reason="${escapeAttr(spec.reason)}"` : "";
    const icon = spec.icon
      ? `<i class="fa-solid ${spec.icon} mr-1" aria-hidden="true"></i>`
      : "";
    return (
      `<button type="button" data-action="${spec.action}" data-enabled="${spec.enabled ? "1" : "0"}"` +
      `${reasonAttr}${title} ` +
      `class="inline-flex items-center px-2 py-1 ${spec.className} rounded text-xs hover:brightness-125 transition">${icon}${spec.label}</button>`
    );
  }

  async function loadIps() {
    await ensureAuth();
    bindFiltersOnce();
    cachedIps = api().asItems(await api().json("/infrastructure/ips?limit=100"));
    cachedInstances = await api().json("/infrastructure/instances");
    if (!Array.isArray(cachedInstances)) cachedInstances = [];
    const assignments = await api().json("/infrastructure/assignments");
    cachedAssignByIp = {};
    (assignments || []).forEach((a) => {
      if (a.status === "active") cachedAssignByIp[a.static_ip_id] = a;
    });

    const available = cachedIps.filter((i) => i.status === "allocated" || i.status === "detached").length;
    const attached = cachedIps.filter((i) => i.status === "attached").length;
    const released = cachedIps.filter((i) => i.status === "released").length;
    setText("w2-ip-available", String(available));
    setText("w2-ip-attached", String(attached));
    setText("w2-ip-released", String(released));
    setText("w2-ip-instances", String(cachedInstances.filter((i) => i.status === "running").length));
    setText("w2-inst-running", String(cachedInstances.filter((i) => String(i.status).toLowerCase() === "running").length));
    setText("w2-inst-suspended", String(cachedInstances.filter((i) => String(i.status).toLowerCase() === "suspended").length));
    setText("w2-inst-destroyed", String(cachedInstances.filter((i) => String(i.status).toLowerCase() === "destroyed").length));

    const brokerSelect = document.getElementById("w2-assign-broker");
    if (brokerSelect) {
      const brokers = cachedBrokers.length ? cachedBrokers : api().asItems(await api().json("/brokers?limit=100"));
      cachedBrokers = brokers;
      brokerSelect.innerHTML = brokers
        .map((b) => `<option value="${b.id}">${b.display_name}</option>`)
        .join("");
    }
    const instSelect = document.getElementById("w2-attach-instance");
    if (instSelect) {
      instSelect.innerHTML = cachedInstances
        .filter((i) => i.status === "running")
        .map(
          (i) =>
            `<option value="${i.id}" data-external-id="${escapeAttr(i.external_id)}">${escapeAttr(
              instancePickerLabel(i),
            )}</option>`,
        )
        .join("");
    }

    if (F()) {
      F().applySeed("static-ips", () => renderIpsTable());
      F().applySeed("infrastructure", () => renderInstancesTables());
    }
    renderInstancesTables();
    renderIpsTable();
  }

  function ipMatchesFilter(ip, filter) {
    if (!filter) return true;
    if (filter === "available") return ip.status === "allocated" || ip.status === "detached";
    if (filter === "attached") return ip.status === "attached";
    if (filter === "released") return ip.status === "released";
    return String(ip.status).toLowerCase() === String(filter).toLowerCase();
  }

  function renderIpsTable() {
    const tbody = document.getElementById("w2-ips-tbody");
    if (!tbody) return;
    const filter = F() ? F().get("static-ips") : null;
    if (F()) {
      F().syncCardStyles("static-ips");
      F().updateChip("static-ips");
    }
    if (!cachedIps.length) {
      tbody.innerHTML = `<tr><td colspan="7" class="py-6 px-4 text-center text-gray-500">No static IPs — allocate one.</td></tr>`;
      return;
    }
    const rows = cachedIps.filter((ip) => ipMatchesFilter(ip, filter));
    if (!rows.length) {
      tbody.innerHTML = `<tr><td colspan="7" class="py-6 px-4 text-center text-gray-500">No IPs match filter.</td></tr>`;
      return;
    }
    tbody.innerHTML = rows
      .map((ip) => {
        const a = cachedAssignByIp[ip.id];
        const actions = ipActionSpecs(ip, a)
          .map((spec) => {
            const html = renderActionButton(spec);
            if (spec.action === "rotate" && spec.brokerId) {
              return html.replace(
                'data-action="rotate"',
                `data-action="rotate" data-broker-id="${escapeAttr(spec.brokerId)}"`,
              );
            }
            return html;
          })
          .join("");
        return `<tr class="hover:bg-white/5 transition" data-ip-id="${ip.id}">
          <td class="py-3 px-4 text-blue-400 font-bold">${ip.ip_address}</td>
          <td class="py-3 px-4 font-sans text-gray-300">${ip.region}</td>
          <td class="py-3 px-4 font-sans"><span class="bg-white/5 px-2 py-0.5 rounded text-gray-300">${ip.provider}</span></td>
          <td class="py-3 px-4 font-sans">${a ? a.broker_display_name : "—"}</td>
          <td class="py-3 px-4 font-sans"><span class="bg-white/5 px-2 py-0.5 rounded text-[10px]">${ip.status.toUpperCase()}</span></td>
          <td class="py-3 px-4 text-gray-400 whitespace-nowrap">${fmtTs(ip.created_at)}</td>
          <td class="py-3 px-4 text-right font-sans space-x-1 whitespace-nowrap">${actions}</td>
        </tr>`;
      })
      .join("");

    tbody.querySelectorAll("tr[data-ip-id]").forEach((tr) => {
      const id = tr.getAttribute("data-ip-id");
      tr.querySelectorAll("button[data-action]").forEach((btn) => {
        btn.addEventListener("click", () => {
          if (btn.getAttribute("data-enabled") !== "1") {
            notify(btn.getAttribute("data-reason") || "Action not available for this IP");
            return;
          }
          const action = btn.getAttribute("data-action");
          if (action === "rotate") {
            if (window.W4Admin && typeof window.W4Admin.openRotate === "function") {
              window.W4Admin.openRotate(btn.getAttribute("data-broker-id"), id);
            } else {
              notify("Rotate UI not loaded");
            }
            return;
          }
          handleIpAction(action, id);
        });
      });
    });
  }

  function renderInstancesTables() {
    const empty =
      `<tr><td colspan="7" class="py-6 px-4 text-center text-gray-500">No instances — use Provision Instance.</td></tr>`;
    const filter = F() ? F().get("infrastructure") : null;
    if (F()) {
      F().syncCardStyles("infrastructure");
      F().updateChip("infrastructure");
    }
    let list = cachedInstances;
    if (filter) {
      list = list.filter((i) => String(i.status || "").toLowerCase() === filter);
    }
    const html = !cachedInstances.length
      ? empty
      : !list.length
        ? `<tr><td colspan="7" class="py-6 px-4 text-center text-gray-500">No instances match filter.</td></tr>`
        : list
            .map((inst) => {
              const st = String(inst.status || "").toLowerCase();
              const destroyed = st === "destroyed";
              const running = st === "running";
              const suspended = st === "suspended";
              const name = escapeAttr(inst.display_name || instancePickerLabel(inst));
              const actions = destroyed
                ? "—"
                : [
                    running
                      ? `<button data-action="suspend" class="px-2 py-1 bg-amber-500/10 text-amber-400 rounded text-xs hover:brightness-125">Suspend</button>`
                      : "",
                    suspended
                      ? `<button data-action="start" class="px-2 py-1 bg-emerald-500/10 text-emerald-400 rounded text-xs hover:brightness-125">Start</button>`
                      : "",
                    `<button data-action="destroy" class="px-2 py-1 bg-rose-500/10 text-rose-400 rounded text-xs hover:brightness-125">Destroy</button>`,
                  ]
                    .filter(Boolean)
                    .join(" ");
              return `<tr class="hover:bg-white/5 transition" data-instance-id="${inst.id}">
              <td class="py-3 px-4 font-sans font-semibold text-white">${name}</td>
              <td class="py-3 px-4 text-blue-400 text-[10px]" title="${escapeAttr(inst.id)}">${escapeAttr(inst.external_id)}</td>
              <td class="py-3 px-4 font-sans text-gray-300">${escapeAttr(inst.region)}</td>
              <td class="py-3 px-4 font-sans"><span class="bg-white/5 px-2 py-0.5 rounded text-gray-300">${escapeAttr(inst.provider)}</span></td>
              <td class="py-3 px-4 font-sans">${instanceStatusBadge(inst.status)}</td>
              <td class="py-3 px-4 text-gray-400 whitespace-nowrap">${fmtTs(inst.created_at)}</td>
              <td class="py-3 px-4 text-right font-sans space-x-1 whitespace-nowrap">${actions}</td>
            </tr>`;
            })
            .join("");

    const tbody = document.getElementById("w2-infra-instances-tbody");
    if (!tbody) return;
    tbody.innerHTML = html;
    tbody.querySelectorAll("tr[data-instance-id]").forEach((tr) => {
      const instanceId = tr.getAttribute("data-instance-id");
      tr.querySelectorAll("button[data-action]").forEach((btn) => {
        btn.addEventListener("click", () =>
          handleInstanceAction(btn.getAttribute("data-action"), instanceId),
        );
      });
    });
  }

  async function handleInstanceAction(action, instanceId) {
    try {
      await ensureAuth();
      if (action === "destroy") {
        if (!window.confirm("Destroy this instance? This stops/removes the mock container.")) return;
        await api().json(`/infrastructure/instances/${instanceId}`, { method: "DELETE" });
        notify("Instance destroyed");
      } else if (action === "suspend") {
        await api().json(`/infrastructure/instances/${instanceId}/suspend`, {
          method: "POST",
          body: "{}",
        });
        notify("Instance suspended");
      } else if (action === "start") {
        await api().json(`/infrastructure/instances/${instanceId}/start`, {
          method: "POST",
          body: "{}",
        });
        notify("Instance started");
      } else {
        return;
      }
      await loadIps();
    } catch (e) {
      errNotify(e);
    }
  }

  let pendingIpAction = null;

  function prepareAssignModal(action) {
    const title = document.getElementById("w2-assign-modal-title");
    const hint = document.getElementById("w2-assign-modal-hint");
    const confirm = document.getElementById("w2-assign-confirm");
    if (action === "reuse") {
      if (title) title.textContent = "Reuse-test: Assign IP to Broker";
      if (hint) hint.textContent = "Expect BR-G04 (IP_REUSE_POLICY) if cooldown has not elapsed.";
      if (confirm) confirm.textContent = "Reuse-test";
    } else {
      if (title) title.textContent = "Assign IP to Broker";
      if (hint) hint.textContent = "BR-G04 reuse policy is enforced after release cooldown.";
      if (confirm) confirm.textContent = "Assign";
    }
  }

  async function handleIpAction(action, ipId) {
    try {
      await ensureAuth();
      if (action === "assign" || action === "reuse") {
        pendingIpAction = { action, ipId };
        prepareAssignModal(action);
        openModal("w2-assign-modal");
        return;
      }
      if (action === "attach") {
        pendingIpAction = { action, ipId };
        if (!cachedInstances.filter((i) => i.status === "running").length) {
          const clientId = await resolveDemoClientId();
          await api().json("/infrastructure/instances", {
            method: "POST",
            body: JSON.stringify({ client_id: clientId, region: "ewr" }),
          });
          notify("Provisioned mock instance");
          await loadIps();
        }
        openModal("w2-attach-modal");
        return;
      }
      if (action === "detach") {
        await api().json(`/infrastructure/ips/${ipId}/detach`, { method: "POST", body: "{}" });
        notify("IP detached");
        await loadIps();
      } else if (action === "release") {
        await api().json(`/infrastructure/ips/${ipId}`, { method: "DELETE" });
        notify("IP released");
        await loadIps();
      }
    } catch (e) {
      errNotify(e);
    }
  }

  async function confirmAssign() {
    try {
      await ensureAuth();
      const brokerId = document.getElementById("w2-assign-broker").value;
      const ipId = pendingIpAction && pendingIpAction.ipId;
      if (!ipId || !brokerId) return;
      await api().json(`/infrastructure/ips/${ipId}/assign`, {
        method: "POST",
        body: JSON.stringify({ broker_account_id: brokerId }),
      });
      closeModal("w2-assign-modal");
      notify("IP assigned to broker");
      await loadIps();
    } catch (e) {
      errNotify(e);
    }
  }

  async function confirmAttach() {
    try {
      await ensureAuth();
      const instanceId = document.getElementById("w2-attach-instance").value;
      const ipId = pendingIpAction && pendingIpAction.ipId;
      if (!ipId || !instanceId) {
        notify("Select an instance");
        return;
      }
      await api().json(`/infrastructure/ips/${ipId}/attach`, {
        method: "POST",
        body: JSON.stringify({ instance_id: instanceId }),
      });
      closeModal("w2-attach-modal");
      notify("IP attached");
      await loadIps();
    } catch (e) {
      errNotify(e);
    }
  }

  async function allocateIp() {
    try {
      await ensureAuth();
      const region = document.getElementById("w2-ip-region").value;
      const ip = await api().json("/infrastructure/ips", {
        method: "POST",
        body: JSON.stringify({ region }),
      });
      closeModal("allocate-ip-modal");
      notify(`Static IP allocated: ${ip.ip_address}`);
      await loadIps();
    } catch (e) {
      errNotify(e);
    }
  }

  async function provisionInstance() {
    try {
      await ensureAuth();
      const clientId = await resolveDemoClientId();
      const inst = await api().json("/infrastructure/instances", {
        method: "POST",
        body: JSON.stringify({ client_id: clientId, region: "ewr" }),
      });
      notify(`Instance ${inst.display_name || inst.external_id} running`);
      await loadIps();
    } catch (e) {
      errNotify(e);
    }
  }

  const pageLoaders = {
    brokers: loadBrokers,
    sessions: loadSessions,
    "static-ips": loadIps,
    infrastructure: loadIps,
  };

  const _origNavigate = window.navigateTo;
  window.navigateTo = function (pageId) {
    if (typeof _origNavigate === "function") _origNavigate(pageId);
    const loader = pageLoaders[pageId];
    if (loader) loader().catch(errNotify);
  };

  window.W2Admin = {
    createBroker,
    allocateIp,
    confirmAssign,
    confirmAttach,
    refreshAllSessions,
    provisionInstance,
    loadBrokers,
    loadSessions,
    loadIps,
  };
})();
