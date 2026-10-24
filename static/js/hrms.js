(function () {
  const root = document.documentElement;
  try {
    const saved = localStorage.getItem("hrms-theme");
    if (saved) root.setAttribute("data-bs-theme", saved);
  } catch (e) {}
  const btn = document.getElementById("themeToggle");
  if (btn) btn.addEventListener("click", function () {
    const next = root.getAttribute("data-bs-theme") === "dark" ? "light" : "dark";
    root.setAttribute("data-bs-theme", next);
    try { localStorage.setItem("hrms-theme", next); } catch (e) {}
  });
  document.querySelectorAll("[data-confirm]").forEach(function (el) {
    el.addEventListener("click", function (ev) { if (!confirm(el.dataset.confirm)) ev.preventDefault(); });
  });
  // Mantiene la pestaña activa según el hash de la URL (#documentos, #licencias...)
  if (location.hash) {
    const tab = document.querySelector('[data-bs-target="' + location.hash + '"]');
    if (tab && window.bootstrap) new bootstrap.Tab(tab).show();
  }
  document.querySelectorAll('[data-bs-toggle="tab"]').forEach(function (t) {
    t.addEventListener("shown.bs.tab", function () { history.replaceState(null, "", t.dataset.bsTarget); });
  });
})();
