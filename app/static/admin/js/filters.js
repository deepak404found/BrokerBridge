/* Shared click-to-filter helpers for Admin KPI / status cards */
(function () {
  const SEED_KEY = "bb_admin_filter_seed";
  const activeFilter = Object.create(null);
  const rerenders = Object.create(null);
  const ACTIVE_RING = ["ring-1", "ring-indigo-400", "bg-indigo-500/10"];

  function get(pageId) {
    return activeFilter[pageId] || null;
  }

  function setRerender(pageId, fn) {
    if (typeof fn === "function") rerenders[pageId] = fn;
  }

  function syncCardStyles(pageId) {
    const active = get(pageId);
    document.querySelectorAll(`[data-filter-page="${pageId}"]`).forEach((el) => {
      const on = el.getAttribute("data-filter-key") === active;
      ACTIVE_RING.forEach((c) => el.classList.toggle(c, on));
      el.setAttribute("aria-pressed", on ? "true" : "false");
    });
  }

  function updateChip(pageId) {
    const chip = document.getElementById(`filter-chip-${pageId}`);
    if (!chip) return;
    const key = get(pageId);
    if (!key) {
      chip.classList.add("hidden");
      chip.innerHTML = "";
      return;
    }
    chip.classList.remove("hidden");
    chip.innerHTML =
      `Filtered: <span class="text-white font-semibold">${key}</span> — ` +
      `<button type="button" class="text-indigo-300 underline hover:text-indigo-200" data-clear-filter>clear</button>`;
    const btn = chip.querySelector("[data-clear-filter]");
    if (btn) {
      btn.addEventListener("click", (e) => {
        e.preventDefault();
        clear(pageId);
      });
    }
  }

  function runRerender(pageId) {
    const fn = rerenders[pageId];
    if (typeof fn === "function") fn();
  }

  function toggleFilter(pageId, key, rerenderFn) {
    if (typeof rerenderFn === "function") setRerender(pageId, rerenderFn);
    if (activeFilter[pageId] === key) {
      activeFilter[pageId] = null;
    } else {
      activeFilter[pageId] = key;
    }
    syncCardStyles(pageId);
    updateChip(pageId);
    runRerender(pageId);
    return get(pageId);
  }

  function clear(pageId, rerenderFn) {
    if (typeof rerenderFn === "function") setRerender(pageId, rerenderFn);
    activeFilter[pageId] = null;
    syncCardStyles(pageId);
    updateChip(pageId);
    runRerender(pageId);
  }

  function setFilter(pageId, key, rerenderFn) {
    if (typeof rerenderFn === "function") setRerender(pageId, rerenderFn);
    activeFilter[pageId] = key || null;
    syncCardStyles(pageId);
    updateChip(pageId);
  }

  function bindStatCard(el, pageId, key, rerenderFn) {
    if (!el) return;
    if (typeof rerenderFn === "function") setRerender(pageId, rerenderFn);
    el.setAttribute("role", "button");
    el.setAttribute("tabindex", "0");
    el.setAttribute("data-filter-page", pageId);
    el.setAttribute("data-filter-key", key);
    el.classList.add("cursor-pointer", "transition", "select-none");
    el.setAttribute("aria-pressed", get(pageId) === key ? "true" : "false");
    const activate = (e) => {
      e.preventDefault();
      toggleFilter(pageId, key, rerenderFn);
    };
    el.onclick = activate;
    el.onkeydown = (e) => {
      if (e.key === "Enter" || e.key === " ") activate(e);
    };
    syncCardStyles(pageId);
  }

  function filterRows(rows, predicate) {
    const list = Array.isArray(rows) ? rows : [];
    if (typeof predicate !== "function") return list;
    return list.filter(predicate);
  }

  function seedNavigate(pageId, filterKey) {
    try {
      sessionStorage.setItem(SEED_KEY, JSON.stringify({ pageId, filterKey: filterKey || null }));
    } catch (_) {
      /* ignore quota */
    }
    if (typeof window.navigateTo === "function") window.navigateTo(pageId);
  }

  function consumeSeed(pageId) {
    let raw;
    try {
      raw = sessionStorage.getItem(SEED_KEY);
    } catch (_) {
      return null;
    }
    if (!raw) return null;
    try {
      const parsed = JSON.parse(raw);
      if (!parsed || parsed.pageId !== pageId) return null;
      sessionStorage.removeItem(SEED_KEY);
      return parsed.filterKey || null;
    } catch (_) {
      try {
        sessionStorage.removeItem(SEED_KEY);
      } catch (__) {
        /* ignore */
      }
      return null;
    }
  }

  function applySeed(pageId, rerenderFn) {
    const key = consumeSeed(pageId);
    if (key) setFilter(pageId, key, rerenderFn);
    else if (typeof rerenderFn === "function") setRerender(pageId, rerenderFn);
    syncCardStyles(pageId);
    updateChip(pageId);
    return key;
  }

  window.AdminFilters = {
    get,
    setFilter,
    setRerender,
    toggleFilter,
    clear,
    bindStatCard,
    filterRows,
    syncCardStyles,
    updateChip,
    seedNavigate,
    consumeSeed,
    applySeed,
  };
})();
