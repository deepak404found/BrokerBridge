window.BrokerBridgeApi = {
  baseUrl: "/api/v1",
  asItems(payload) {
    if (payload && typeof payload === "object" && Array.isArray(payload.items)) return payload.items;
    return Array.isArray(payload) ? payload : [];
  },
  pageMeta(payload, fallbackLimit) {
    if (payload && typeof payload === "object" && "total" in payload) {
      return {
        total: Number(payload.total) || 0,
        limit: Number(payload.limit) || fallbackLimit || 25,
        offset: Number(payload.offset) || 0,
        next_offset: payload.next_offset == null ? null : Number(payload.next_offset),
      };
    }
    const items = this.asItems(payload);
    return { total: items.length, limit: fallbackLimit || 25, offset: 0, next_offset: null };
  },
  /** Locale-friendly timestamp for Admin tables; blank if missing. */
  formatTs(value) {
    if (value == null || value === "") return "—";
    const d = value instanceof Date ? value : new Date(value);
    if (Number.isNaN(d.getTime())) {
      return String(value).replace("T", " ").replace(/\.\d+Z?$/, "").slice(0, 19);
    }
    return d.toLocaleString(undefined, {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    });
  },
  getToken() {
    return localStorage.getItem("bb_token");
  },
  setToken(token) {
    if (token) localStorage.setItem("bb_token", token);
    else localStorage.removeItem("bb_token");
  },
  async login(email, password) {
    const body = new URLSearchParams();
    body.set("username", email);
    body.set("password", password);
    const res = await fetch(this.baseUrl + "/auth/token", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const msg = data.message || (data.error && data.error.message) || "Login failed";
      throw new Error(msg);
    }
    this.setToken(data.access_token);
    return data;
  },
  logout() {
    this.setToken(null);
  },
  async request(path, options = {}) {
    const headers = Object.assign(
      { "Content-Type": "application/json" },
      options.headers || {},
    );
    const token = this.getToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;
    const method = (options.method || "GET").toUpperCase();
    if (method === "GET" || method === "HEAD" || options.body == null) {
      delete headers["Content-Type"];
    }
    const res = await fetch(this.baseUrl + path, Object.assign({}, options, { headers }));
    return res;
  },
  async json(path, options = {}) {
    const res = await this.request(path, options);
    if (res.status === 204) return null;
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const msg = data.message || (data.error && data.error.message) || `HTTP ${res.status}`;
      const err = new Error(msg);
      err.status = res.status;
      err.error_code = data.error_code;
      err.details = data.details;
      err.payload = data;
      err.displayMessage = this.formatError(err);
      throw err;
    }
    return data;
  },

  formatError(err) {
    const code = err.error_code ? `[${err.error_code}] ` : "";
    let msg = err.message || "Request failed";
    const d = err.details;
    if (d && typeof d === "object") {
      const detailMsg = d.message || d.hint || (typeof d.error === "string" ? d.error : null);
      if (detailMsg && !msg.includes(String(detailMsg))) {
        msg = `${msg} — ${detailMsg}`;
      }
    }
    return code + msg;
  },

  /** Copy plain text to clipboard; toast "Copied" on success. */
  async copyText(str) {
    const text = String(str ?? "");
    if (!text) {
      if (typeof showNotification === "function") showNotification("Nothing to copy", true);
      return false;
    }
    try {
      if (navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
        await navigator.clipboard.writeText(text);
      } else {
        const ta = document.createElement("textarea");
        ta.value = text;
        ta.setAttribute("readonly", "");
        ta.style.position = "fixed";
        ta.style.left = "-9999px";
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        ta.remove();
      }
      if (typeof showNotification === "function") showNotification("Copied");
      return true;
    } catch (_) {
      if (typeof showNotification === "function") showNotification("Copy failed", true);
      return false;
    }
  },

  escapeAttr(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;")
      .replace(/</g, "&lt;");
  },

  /** Small icon button; reads text from data-copy. */
  copyButtonHtml(text, title) {
    const label = this.escapeAttr(title || "Copy");
    const payload = this.escapeAttr(text);
    return (
      `<button type="button" class="inline-flex items-center justify-center shrink-0 w-6 h-6 rounded border border-white/10 bg-dark-800 hover:bg-white/10 text-gray-400 hover:text-white transition" ` +
      `title="${label}" aria-label="${label}" data-copy="${payload}" ` +
      `onclick="event.preventDefault(); event.stopPropagation(); window.BrokerBridgeApi.copyText(this.getAttribute('data-copy'))">` +
      `<i class="fa-solid fa-copy text-[10px]"></i></button>`
    );
  },
};

(function mountAuthGate() {
  const gate = document.getElementById("login-gate");
  const shell = document.getElementById("admin-shell");
  if (!gate || !shell) return;

  const form = document.getElementById("login-form");
  const status = document.getElementById("login-status");
  const emailInput = document.getElementById("login-email");
  const passwordInput = document.getElementById("login-password");
  const submitBtn = document.getElementById("login-submit");

  const USER_EMAIL_KEY = "bb_admin_email";
  const USER_ROLE_KEY = "bb_admin_role";

  function titleCaseRole(role) {
    if (!role) return "User";
    return String(role)
      .split(/[_\s-]+/)
      .filter(Boolean)
      .map((part) => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase())
      .join(" ");
  }

  function initialsFromEmail(email) {
    if (!email) return "—";
    const local = String(email).split("@")[0] || "";
    const parts = local.split(/[._-]+/).filter(Boolean);
    if (parts.length >= 2) {
      return (parts[0][0] + parts[1][0]).toUpperCase();
    }
    return local.slice(0, 2).toUpperCase() || "—";
  }

  function decodeJwtPayload(token) {
    try {
      const part = String(token || "").split(".")[1];
      if (!part) return null;
      const b64 = part.replace(/-/g, "+").replace(/_/g, "/");
      const padded = b64 + "=".repeat((4 - (b64.length % 4)) % 4);
      return JSON.parse(atob(padded));
    } catch (_) {
      return null;
    }
  }

  function clearSignedInUser() {
    localStorage.removeItem(USER_EMAIL_KEY);
    localStorage.removeItem(USER_ROLE_KEY);
    const emailEl = document.getElementById("sidebar-user-email");
    const nameEl = document.getElementById("sidebar-user-name");
    const roleEl = document.getElementById("sidebar-user-role");
    const initialsEl = document.getElementById("sidebar-user-initials");
    if (emailEl) emailEl.textContent = "—";
    if (nameEl) nameEl.textContent = "Signed out";
    if (roleEl) roleEl.textContent = "—";
    if (initialsEl) initialsEl.textContent = "—";
  }

  function setSignedInUser(email, role) {
    const displayRole = titleCaseRole(role);
    const emailEl = document.getElementById("sidebar-user-email");
    const nameEl = document.getElementById("sidebar-user-name");
    const roleEl = document.getElementById("sidebar-user-role");
    const initialsEl = document.getElementById("sidebar-user-initials");
    if (emailEl) emailEl.textContent = email || "—";
    if (nameEl) nameEl.textContent = displayRole;
    if (roleEl) roleEl.textContent = role || "—";
    if (initialsEl) initialsEl.textContent = initialsFromEmail(email);
  }

  function persistUser(email, role) {
    if (email) localStorage.setItem(USER_EMAIL_KEY, email);
    else localStorage.removeItem(USER_EMAIL_KEY);
    if (role) localStorage.setItem(USER_ROLE_KEY, role);
    else localStorage.removeItem(USER_ROLE_KEY);
  }

  function resolveStoredUser(token) {
    let email = localStorage.getItem(USER_EMAIL_KEY);
    let role = localStorage.getItem(USER_ROLE_KEY);
    const claims = decodeJwtPayload(token);
    if (!role && claims && claims.role) {
      role = claims.role;
      localStorage.setItem(USER_ROLE_KEY, role);
    }
    return { email, role };
  }

  function applyAuthState() {
    const token = window.BrokerBridgeApi.getToken();
    if (token) {
      gate.classList.add("hidden");
      shell.classList.remove("hidden");
      shell.classList.add("flex");
      document.body.classList.add("admin-authed");
      const user = resolveStoredUser(token);
      setSignedInUser(user.email, user.role);
      document.dispatchEvent(new CustomEvent("bb:auth-ready"));
    } else {
      shell.classList.add("hidden");
      shell.classList.remove("flex");
      gate.classList.remove("hidden");
      document.body.classList.remove("admin-authed");
      clearSignedInUser();
      if (status) {
        status.textContent = "Sign in to open the operations console.";
        status.classList.remove("text-rose-400");
        status.classList.add("text-gray-400");
      }
    }
  }

  window.BrokerBridgeAuth = {
    applyAuthState,
    logout() {
      window.BrokerBridgeApi.logout();
      clearSignedInUser();
      applyAuthState();
      if (typeof navigateTo === "function") navigateTo("dashboard");
    },
  };

  if (form) {
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      if (status) {
        status.textContent = "Signing in…";
        status.classList.remove("text-rose-400");
        status.classList.add("text-gray-400");
      }
      if (submitBtn) submitBtn.disabled = true;
      try {
        const email = (emailInput && emailInput.value) || "";
        const password = (passwordInput && passwordInput.value) || "";
        const data = await window.BrokerBridgeApi.login(email, password);
        const resolvedEmail = data.email || email;
        const resolvedRole = data.role || "";
        persistUser(resolvedEmail, resolvedRole);
        applyAuthState();
        if (typeof showNotification === "function") {
          showNotification("Signed in — Admin console ready");
        }
        // Fire after w5 wrappers are loaded; also notify listeners for dashboard boot
        document.dispatchEvent(new CustomEvent("bb:auth-ready"));
        if (typeof navigateTo === "function") navigateTo("dashboard");
      } catch (err) {
        if (status) {
          status.textContent = err.message || "Login failed";
          status.classList.remove("text-gray-400");
          status.classList.add("text-rose-400");
        }
      } finally {
        if (submitBtn) submitBtn.disabled = false;
      }
    });
  }

  applyAuthState();
})();
