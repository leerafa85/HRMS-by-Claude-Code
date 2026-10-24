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

// Barra de estado: reloj en tiempo real e indicador de conexión con el servidor y la base de datos.
(function () {
  const bar = document.getElementById("statusBar");
  if (!bar) return;
  const clock = document.getElementById("sbClock"), text = document.getElementById("sbText"), msg = document.getElementById("sbMsg");
  const tz = "America/Argentina/Buenos_Aires";
  function tick() {
    const now = new Date();
    clock.textContent = now.toLocaleDateString("es-AR", { timeZone: tz, weekday: "short", day: "2-digit", month: "2-digit", year: "numeric" })
      + " " + now.toLocaleTimeString("es-AR", { timeZone: tz, hour12: false });
  }
  tick(); setInterval(tick, 1000);

  const STATES = {
    ok: ["status-ok", "Conectado y funcionando", ""],
    warn: ["status-warn", "Funcionando con inestabilidad",
      "⚠ Después de cualquier modificación, verificá que el indicador vuelva a verde antes de darla por guardada."],
    down: ["status-down", "Sin conexión",
      "⛔ El sistema no está conectado: ningún cambio que hagas se va a ver reflejado ni se va a guardar en la base de datos."],
  };
  let state = null, history = [], timer = null;

  function setState(s) {
    state = s;
    bar.classList.remove("status-ok", "status-warn", "status-down");
    bar.classList.add(STATES[s][0]);
    text.textContent = STATES[s][1];
    msg.textContent = STATES[s][2];
    msg.title = STATES[s][2];
  }

  async function check() {
    clearTimeout(timer);
    const started = performance.now();
    let ok = false, slow = false;
    if (navigator.onLine !== false) {
      const ctrl = new AbortController();
      const abort = setTimeout(() => ctrl.abort(), 8000);
      try {
        const r = await fetch(bar.dataset.url, { cache: "no-store", signal: ctrl.signal, credentials: "same-origin" });
        const data = r.ok ? await r.json() : null;
        ok = !!(data && data.db);
        slow = performance.now() - started > 3000 || (data && data.db_ms > 1500);
      } catch (e) { ok = false; }
      clearTimeout(abort);
    }
    history = history.concat([ok]).slice(-5);
    const failures = history.filter(x => !x).length;
    if (!ok) {
      // Un solo error aislado se marca como inestable; dos seguidos o sin red, como desconectado.
      const prevOk = history.length > 1 && history[history.length - 2];
      setState(navigator.onLine === false || !prevOk ? "down" : "warn");
    } else if (slow || failures > 0) {
      setState("warn");
    } else {
      setState("ok");
    }
    timer = setTimeout(check, state === "ok" ? 30000 : 8000);
  }
  window.addEventListener("online", check);
  window.addEventListener("offline", () => { history.push(false); setState("down"); });
  document.addEventListener("visibilitychange", () => { if (!document.hidden) check(); });
  check();

  // Sin conexión: se avisa antes de enviar formularios, porque los cambios no se guardarían.
  document.addEventListener("submit", function (ev) {
    if (state === "down" && ev.target.method && ev.target.method.toLowerCase() === "post") {
      ev.preventDefault();
      alert(STATES.down[2] + "\n\nEsperá a que el indicador vuelva a verde e intentá nuevamente.");
    }
  }, true);
})();
