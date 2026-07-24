window.BrokerBridgeApi = {
  baseUrl: "/api/v1",
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
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const msg = data.message || (data.error && data.error.message) || `HTTP ${res.status}`;
      const err = new Error(msg);
      err.status = res.status;
      err.error_code = data.error_code;
      err.details = data.details;
      err.payload = data;
      throw err;
    }
    return data;
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

  function setSignedInUser(email) {
    const label = document.getElementById("sidebar-user-email");
    const name = document.getElementById("sidebar-user-name");
    if (label) label.textContent = email || "admin@brokerbridge.local";
    if (name) name.textContent = "Admin";
  }

  function applyAuthState() {
    const token = window.BrokerBridgeApi.getToken();
    if (token) {
      gate.classList.add("hidden");
      shell.classList.remove("hidden");
      shell.classList.add("flex");
      document.body.classList.add("admin-authed");
      setSignedInUser(localStorage.getItem("bb_admin_email") || "admin@brokerbridge.local");
    } else {
      shell.classList.add("hidden");
      shell.classList.remove("flex");
      gate.classList.remove("hidden");
      document.body.classList.remove("admin-authed");
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
      localStorage.removeItem("bb_admin_email");
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
        await window.BrokerBridgeApi.login(email, password);
        localStorage.setItem("bb_admin_email", email);
        applyAuthState();
        if (typeof showNotification === "function") {
          showNotification("Signed in — Admin console ready");
        }
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
