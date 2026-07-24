/* Wave 4 Admin wiring — Rotate, Event Bus, Runtime Config / Events */
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

  let pendingRotate = null;
  let eventsWs = null;
  let eventsPollTimer = null;
  let eventsLive = false;

  async function ensureAuth() {
    if (!api().getToken()) {
      notify("Sign in required");
      if (window.BrokerBridgeAuth) window.BrokerBridgeAuth.applyAuthState();
      throw new Error("Not authenticated");
    }
  }

  function openRotate(brokerId, ipId) {
    pendingRotate = { brokerId, ipId };
    const force = document.getElementById("w4-rotate-force");
    if (force) force.checked = false;
    if (typeof openModal === "function") openModal("w4-rotate-modal");
  }

  async function confirmRotate() {
    try {
      await ensureAuth();
      if (!pendingRotate || !pendingRotate.brokerId) {
        notify("No broker selected for rotate");
        return;
      }
      const force = Boolean(document.getElementById("w4-rotate-force")?.checked);
      notify(force ? "FORCE rotate in progress…" : "Rotating IP (drain)…");
      const result = await api().json(
        `/infrastructure/brokers/${pendingRotate.brokerId}/rotate-ip`,
        { method: "POST", body: JSON.stringify({ force }) },
      );
      if (typeof closeModal === "function") closeModal("w4-rotate-modal");
      notify(`Rotated ${result.old_ip} → ${result.new_ip}${result.drained ? "" : " (forced)"}`);
      if (window.W2Admin && W2Admin.loadIps) await W2Admin.loadIps();
      await loadEvents();
    } catch (e) {
      errNotify(e);
    }
  }

  function renderEvents(rows) {
    const tbody = document.getElementById("w4-events-tbody");
    if (!tbody) return;
    if (!rows || !rows.length) {
      tbody.innerHTML = `<tr><td colspan="5" class="py-6 px-4 text-center text-gray-500">No outbox events yet.</td></tr>`;
      return;
    }
    tbody.innerHTML = rows
      .map((r) => {
        const when = (r.created_at || "").replace("T", " ").slice(0, 19);
        const payload = JSON.stringify(r.payload || {}).slice(0, 120);
        const st =
          r.status === "sent"
            ? "text-emerald-400"
            : r.status === "error"
              ? "text-rose-400"
              : "text-amber-400";
        return `<tr class="hover:bg-white/5">
            <td class="py-2.5 px-4 text-gray-400">${when}</td>
            <td class="py-2.5 px-4 text-white">${r.event_type}</td>
            <td class="py-2.5 px-4">${r.topic}</td>
            <td class="py-2.5 px-4 ${st}">${r.status}</td>
            <td class="py-2.5 px-4 text-gray-400 truncate max-w-xs" title="${payload.replace(/"/g, "&quot;")}">${payload}</td>
          </tr>`;
      })
      .join("");
  }

  function setEventsLiveStatus(text) {
    const el = document.getElementById("w4-events-live-status");
    if (el) el.textContent = text;
  }

  function stopEventsLive() {
    eventsLive = false;
    if (eventsWs) {
      try {
        eventsWs.close();
      } catch (_) {}
      eventsWs = null;
    }
    if (eventsPollTimer) {
      clearInterval(eventsPollTimer);
      eventsPollTimer = null;
    }
  }

  function startEventsPollingFallback() {
    if (eventsPollTimer) return;
    setEventsLiveStatus("Polling (WS unavailable)");
    eventsPollTimer = setInterval(() => {
      loadEvents({ silent: true }).catch(() => {});
    }, 3000);
  }

  function startEventsWs() {
    stopEventsLive();
    eventsLive = true;
    const token = api().getToken();
    if (!token) return;
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const url = `${proto}://${location.host}/api/v1/ws/events?token=${encodeURIComponent(token)}&limit=50`;
    try {
      eventsWs = new WebSocket(url);
    } catch (_) {
      startEventsPollingFallback();
      return;
    }
    setEventsLiveStatus("Connecting…");
    eventsWs.onopen = () => setEventsLiveStatus("Live (WebSocket)");
    eventsWs.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data);
        if (msg && Array.isArray(msg.events)) renderEvents(msg.events);
      } catch (_) {}
    };
    eventsWs.onerror = () => {
      setEventsLiveStatus("WS error — falling back");
    };
    eventsWs.onclose = () => {
      eventsWs = null;
      if (eventsLive) startEventsPollingFallback();
    };
  }

  async function loadEvents(opts) {
    const silent = Boolean(opts && opts.silent);
    try {
      await ensureAuth();
      const rows = await api().json("/monitoring/events?limit=50");
      renderEvents(rows);
    } catch (e) {
      if (!silent) errNotify(e);
    }
  }

  async function drainEvents() {
    try {
      await ensureAuth();
      const stats = await api().json("/monitoring/events/drain", { method: "POST", body: "{}" });
      notify(`Drained outbox — sent=${stats.sent} error=${stats.error}`);
      await loadEvents();
    } catch (e) {
      errNotify(e);
    }
  }

  function setVal(id, value) {
    const el = document.getElementById(id);
    if (el) el.value = value == null ? "" : String(value);
  }

  async function loadEventProvider() {
    try {
      await ensureAuth();
      const statusEl = document.getElementById("w4-event-provider-status");
      let row = null;
      try {
        row = await api().json("/admin/providers/event");
      } catch (e) {
        if (e.status !== 404 && e.error_code !== "NOT_FOUND") throw e;
      }
      if (row) {
        if (statusEl) {
          statusEl.textContent = `Active: ${row.provider_type} v${row.version} (${row.status}) — secrets masked`;
        }
        setVal("w4-event-type", row.provider_type);
        const cfg = row.config || {};
        setVal("w4-event-brokers", cfg.brokers || "");
        setVal("w4-event-security", cfg.security_protocol || "PLAINTEXT");
        setVal("w4-event-sasl", cfg.sasl_mechanism || "");
        setVal("w4-event-prefix", cfg.topic_prefix || "brokerbridge");
        const ssl = document.getElementById("w4-event-ssl");
        if (ssl) ssl.checked = Boolean(cfg.ssl);
        const map = cfg.topic_map || {};
        const singles = Object.values(map);
        const single =
          singles.length && singles.every((t) => t === singles[0]) ? singles[0] : "";
        setVal("w4-event-single-topic", single || "");
        setVal("w4-event-user", "");
        setVal("w4-event-pass", "");
      } else if (statusEl) {
        statusEl.textContent = "No active DB event provider — using env bootstrap / memory fallback";
      }

      try {
        const drain = await api().json("/admin/config/ip.rotation.drain_timeout_seconds");
        setVal("w4-drain-timeout", drain.value?.seconds ?? 30);
      } catch (_) {}
      try {
        const onTimeout = await api().json("/admin/config/ip.rotation.on_timeout");
        setVal("w4-on-timeout", onTimeout.value?.policy || "ABORT");
      } catch (_) {}
    } catch (e) {
      errNotify(e);
    }
  }

  async function activateEventProvider(validateFirst) {
    try {
      await ensureAuth();
      const providerType = document.getElementById("w4-event-type").value;
      const config = {
        brokers: document.getElementById("w4-event-brokers").value.trim(),
        security_protocol: document.getElementById("w4-event-security").value,
        sasl_mechanism: document.getElementById("w4-event-sasl").value.trim() || undefined,
        topic_prefix: document.getElementById("w4-event-prefix").value.trim() || "brokerbridge",
        ssl: Boolean(document.getElementById("w4-event-ssl")?.checked),
      };
      const singleTopic = document.getElementById("w4-event-single-topic")?.value.trim();
      if (singleTopic) {
        config.topic_map = {
          orders: singleTopic,
          brokers: singleTopic,
          ip: singleTopic,
          subscriptions: singleTopic,
          config: singleTopic,
        };
      }
      const user = document.getElementById("w4-event-user").value;
      const pass = document.getElementById("w4-event-pass").value;
      if (user) config.username = user;
      if (pass) config.password = pass;
      if (providerType === "memory") {
        delete config.brokers;
      }
      const body = {
        provider_type: providerType,
        validate_first: Boolean(validateFirst),
        activate: true,
        config,
      };
      const row = await api().json("/admin/providers/event", {
        method: "PUT",
        body: JSON.stringify(body),
      });
      notify(`Event provider activated: ${row.provider_type} v${row.version}`);
      await loadEventProvider();
    } catch (e) {
      errNotify(e);
    }
  }

  async function saveRotationConfig() {
    try {
      await ensureAuth();
      const seconds = Number(document.getElementById("w4-drain-timeout").value || 30);
      const policy = document.getElementById("w4-on-timeout").value || "ABORT";
      await api().json("/admin/config/ip.rotation.drain_timeout_seconds", {
        method: "PUT",
        body: JSON.stringify({ value: { seconds } }),
      });
      await api().json("/admin/config/ip.rotation.on_timeout", {
        method: "PUT",
        body: JSON.stringify({ value: { policy } }),
      });
      notify("Rotation config saved");
    } catch (e) {
      errNotify(e);
    }
  }

  const pageLoaders = {
    events: async () => {
      await loadEvents();
      startEventsWs();
    },
    config: loadEventProvider,
  };

  const _origNavigate = window.navigateTo;
  window.navigateTo = function (pageId) {
    if (pageId !== "events") stopEventsLive();
    if (typeof _origNavigate === "function") _origNavigate(pageId);
    const loader = pageLoaders[pageId];
    if (loader) loader().catch(errNotify);
  };

  window.W4Admin = {
    openRotate,
    confirmRotate,
    loadEvents,
    drainEvents,
    loadEventProvider,
    activateEventProvider,
    saveRotationConfig,
    startEventsWs,
    stopEventsLive,
  };
})();
