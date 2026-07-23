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
    const res = await fetch(this.baseUrl + path, Object.assign({}, options, { headers }));
    return res;
  },
};

(function mountLoginBar() {
  if (document.getElementById("bb-login-bar")) return;
  const bar = document.createElement("div");
  bar.id = "bb-login-bar";
  bar.style.cssText =
    "position:fixed;right:12px;bottom:12px;z-index:9999;background:#121824;border:1px solid rgba(255,255,255,.12);padding:10px 12px;border-radius:8px;font:12px/1.4 Inter,sans-serif;color:#e2e8f0;min-width:240px;box-shadow:0 8px 24px rgba(0,0,0,.45);";
  bar.innerHTML = `
    <div style="font-weight:600;margin-bottom:6px;">Admin JWT</div>
    <div id="bb-login-status" style="margin-bottom:8px;opacity:.85;">Checking…</div>
    <form id="bb-login-form" style="display:grid;gap:6px;">
      <input id="bb-email" type="email" placeholder="email" value="admin@brokerbridge.local"
        style="background:#0c1017;border:1px solid rgba(255,255,255,.12);color:#e2e8f0;padding:6px 8px;border-radius:6px;" />
      <input id="bb-password" type="password" placeholder="password" value="admin123!"
        style="background:#0c1017;border:1px solid rgba(255,255,255,.12);color:#e2e8f0;padding:6px 8px;border-radius:6px;" />
      <div style="display:flex;gap:6px;">
        <button type="submit" style="flex:1;background:#2563eb;color:#fff;border:0;padding:6px 8px;border-radius:6px;cursor:pointer;">Login</button>
        <button type="button" id="bb-logout" style="background:#1a2234;color:#e2e8f0;border:1px solid rgba(255,255,255,.12);padding:6px 8px;border-radius:6px;cursor:pointer;">Logout</button>
      </div>
    </form>
  `;
  document.body.appendChild(bar);
  const status = document.getElementById("bb-login-status");
  const refresh = () => {
    const t = window.BrokerBridgeApi.getToken();
    status.textContent = t ? "Signed in (token stored)" : "Not signed in";
  };
  refresh();
  document.getElementById("bb-login-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    status.textContent = "Signing in…";
    try {
      await window.BrokerBridgeApi.login(
        document.getElementById("bb-email").value,
        document.getElementById("bb-password").value,
      );
      refresh();
    } catch (err) {
      status.textContent = err.message || "Login failed";
    }
  });
  document.getElementById("bb-logout").addEventListener("click", () => {
    window.BrokerBridgeApi.logout();
    refresh();
  });
})();
