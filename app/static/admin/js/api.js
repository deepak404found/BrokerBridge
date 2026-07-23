window.BrokerBridgeApi = {
  baseUrl: "/api/v1",
  getToken() {
    return localStorage.getItem("bb_token");
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
