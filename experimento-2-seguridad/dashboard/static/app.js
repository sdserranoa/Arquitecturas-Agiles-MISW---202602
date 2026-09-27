/* Experimento 2 — dashboard. Todo lo que se muestra sale del estado real de
 * los servicios (vía /api/*); los gráficos son SVG hechos a mano, sin CDN. */
"use strict";

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

// Motivos de intrusión: orden y color fijos en todo el dashboard.
const MOTIVOS = [
  { id: "TOKEN_ALTERADO", nombre: "Token alterado", color: "var(--m-token)",
    regla: "Firma inválida, alg=none o clave distinta a la del borde" },
  { id: "ROL_INCONSISTENTE", nombre: "Rol inconsistente", color: "var(--m-rol)",
    regla: "El rol del token no coincide con el rol activo en la fuente de verdad" },
  { id: "PRIVILEGIO_INSUFICIENTE", nombre: "Privilegio insuficiente", color: "var(--m-priv)",
    regla: "El rol real no tiene permiso: la autorización de borde fue evadida" },
  { id: "USUARIO_DESCONOCIDO", nombre: "Usuario desconocido", color: "var(--m-usuario)",
    regla: "El usuario del token no existe o está inactivo" },
];
const MOTIVO = Object.fromEntries(MOTIVOS.map((m) => [m.id, m]));
const SERIES_LAT = [
  { id: "rbac_local", nombre: "RBAC local (sin verificador)", color: "var(--s-local)" },
  { id: "verificador_central", nombre: "Con verificador central", color: "var(--s-central)" },
];
const FASES = ["preparando", "enviando", "auditando", "midiendo_latencia", "reporte"];
const NOMBRE_FASE = {
  preparando: "Preparando: esperando servicios y reiniciando datos",
  enviando: "Enviando solicitudes",
  auditando: "Auditando alertas por solicitud_id",
  midiendo_latencia: "Midiendo sobrecosto de latencia",
  reporte: "Reporte listo",
};

const S = {
  tab: "experimento",
  catalogo: null,
  ultimoSeq: 0,
  feed: [],
  nLegit: 0,
  nAttack: 0,
  animando: 0,
  corridaVista: null,
  reporte: null,
  historial: [],
  alertas: null,
  alertasFirma: "",
  alertasConocidas: new Set(),
  filtro: null,
  busqueda: "",
  bannerCerrado: false,
  prev: {},
};

// ----------------------------------------------------------------- utils
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = (n, d = 0) => (n == null || Number.isNaN(n) ? "–" :
  Number(n).toLocaleString("es-CO", { minimumFractionDigits: d, maximumFractionDigits: d }));
const hora = (ts) => new Date(ts * 1000).toLocaleTimeString("es-CO", { hour12: false });
const etiqueta = (tipo) => (tipo || "").replace(/_/g, " ");

async function api(path, { method = "GET", body } = {}) {
  try {
    const r = await fetch(path, {
      method,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
    let data = null;
    try { data = await r.json(); } catch { /* sin cuerpo */ }
    return { ok: r.ok, status: r.status, data };
  } catch (e) {
    return { ok: false, status: 0, data: { error: String(e) } };
  }
}

function setNum(id, valor, sufijo = "") {
  const el = typeof id === "string" ? document.getElementById(id) : id;
  if (!el) return;
  const txt = valor == null ? "–" : fmt(valor) + sufijo;
  if (el.textContent !== txt) {
    el.textContent = txt;
    el.classList.remove("bump");
    void el.offsetWidth;
    el.classList.add("bump");
  }
}

function toast(msg, ms = 3500) {
  const t = $("#toast");
  t.innerHTML = msg;
  t.classList.remove("hidden");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => t.classList.add("hidden"), ms);
}

function feedback(msg, cls = "") {
  const f = $("#feedback");
  f.textContent = msg;
  f.className = "feedback " + cls;
}

function motivoChip(id) {
  const m = MOTIVO[id];
  if (!m) return `<span class="muted">${esc(id || "—")}</span>`;
  return `<span class="motivo" style="--c:${m.color}">${esc(m.nombre)}</span>`;
}

function decision(e) {
  if (e.status >= 200 && e.status < 300) return `<span class="estado ok">✓ Autorizada</span>`;
  if (e.status === 503) return `<span class="estado warn">⚠ Negada: verificador caído (fail-closed)</span>`;
  if (e.status === 401) return `<span class="estado warn">⚠ Sin token</span>`;
  if (MOTIVO[e.motivo]) return `<span class="estado bad">✕ Bloqueada</span> · ${motivoChip(e.motivo)}`;
  return `<span class="estado bad">✕ ${esc(e.motivo || "Rechazada")}</span>`;
}

// --------------------------------------------------------------- tooltip
const tip = $("#tooltip");
function moverTip(ev) {
  const pad = 14;
  const r = tip.getBoundingClientRect();
  let x = ev.clientX + pad;
  let y = ev.clientY + pad;
  if (x + r.width > innerWidth - 8) x = ev.clientX - r.width - pad;
  if (y + r.height > innerHeight - 8) y = ev.clientY - r.height - pad;
  tip.style.left = x + "px";
  tip.style.top = y + "px";
}
function enlazarTips(contenedor, tips) {
  $$("[data-i]", contenedor).forEach((el) => {
    const html = tips[+el.dataset.i];
    if (!html) return;
    const mark = el.previousElementSibling;
    el.addEventListener("mouseenter", (ev) => {
      tip.innerHTML = html;
      tip.classList.remove("hidden");
      moverTip(ev);
      mark?.classList.add("hover");
    });
    el.addEventListener("mousemove", moverTip);
    el.addEventListener("mouseleave", () => {
      tip.classList.add("hidden");
      mark?.classList.remove("hover");
    });
  });
}
const filaTip = (color, nombre, valor) =>
  `<div class="t-row"><i style="--c:${color}"></i>${esc(nombre)}<b>${valor}</b></div>`;

// ----------------------------------------------------------------- tabs
function irATab(nombre) {
  S.tab = nombre;
  $$(".tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === nombre));
  $$(".panel").forEach((p) => p.classList.toggle("hidden", p.id !== "tab-" + nombre));
  if (nombre === "resultados") $("#tab-dot-resultados").classList.add("hidden");
  if (nombre === "alertas") { S.alertasFirma = ""; pollAlertas(); }
  if (nombre === "resultados" && S.reporte) renderResultados(S.reporte);
}
$$(".tab").forEach((t) => t.addEventListener("click", () => irATab(t.dataset.tab)));

// ====================================================== ESTADO EN VIVO
async function pollEstado() {
  const { ok, data: d } = await api("/api/estado");
  if (!ok || !d) {
    $$("#health .pill[data-svc]").forEach((p) => (p.className = "pill down"));
    return;
  }
  for (const [svc, up] of Object.entries(d.salud)) {
    const p = $(`#health .pill[data-svc="${svc}"]`);
    if (p) p.className = "pill " + (up ? "up" : "down");
  }
  const dp = $("#docker-pill");
  dp.className = "pill " + (d.docker_mode === "manual" ? "warn" : "up");
  dp.lastChild.textContent = "docker: " + d.docker_mode;
  $("#manual-cmd").textContent = `${d.manual.stop} / ${d.manual.start}`;
  $("#manual-banner").classList.toggle("hidden", d.docker_mode !== "manual" || S.bannerCerrado);

  const v = d.verificador;
  setNum("n-intrusiones", v?.intrusiones);
  setNum("n-verificaciones", v?.verificaciones);
  setNum("n-pendientes", v?.alertas_pendientes);
  setNum("k-verif", v?.verificaciones);
  setNum("k-autorizadas", v?.autorizadas);
  setNum("k-intrusiones", v?.intrusiones);

  const a = d.alertas;
  setNum("n-alertas", a?.total);
  setNum("k-alertas", a?.total);
  const p95 = a?.latencia_registro_ms?.p95;
  $("#k-lat-alerta").textContent = p95 == null ? "–" : fmt(p95, 1) + " ms";
  const badge = $("#tab-badge-alertas");
  badge.textContent = fmt(a?.total ?? 0);
  badge.classList.toggle("zero", !a?.total);

  setNum("n-aprobaciones", d.aprobaciones?.total);
  setNum("k-aprob", d.aprobaciones?.total);

  // El verificador cuenta como caído si su /health no responde, aunque docker no esté disponible.
  const arriba = d.salud.verificador;
  const texto = arriba ? "● en línea" : "● caído — fail-closed";
  for (const id of ["chip-verificador", "chip-verificador-2"]) {
    const c = document.getElementById(id);
    c.textContent = texto;
    c.className = "chip " + (arriba ? "running" : "stopped");
  }
  $("#node-verificador").classList.toggle("down", !arriba);
  $("#btn-stop").disabled = !arriba;
  $("#btn-start").disabled = arriba;
  if (arriba && S.prev.verificadorArriba === false) cargarUsuarios();
  S.prev.verificadorArriba = arriba;
}

// ------------------------------------------------------------- eventos
async function pollEventos() {
  const { ok, data } = await api(`/api/eventos?desde=${S.ultimoSeq}`);
  // La primera carga solo llena la tabla: no se re-animan solicitudes viejas.
  const historicos = !S.eventosCargados;
  S.eventosCargados = ok;
  if (!ok || !Array.isArray(data) || !data.length) return;
  data.forEach((e, i) => {
    S.ultimoSeq = Math.max(S.ultimoSeq, e.seq);
    e.clase === "ataque" ? S.nAttack++ : S.nLegit++;
    S.feed.unshift(e);
    // Escalona las animaciones de un mismo lote y limita las simultáneas.
    if (!historicos && S.animando < 8) setTimeout(() => animarEvento(e), i * 140);
  });
  S.feed.length = Math.min(S.feed.length, 200);
  setNum("n-legit", S.nLegit);
  setNum("n-attack", S.nAttack);
  renderFeed(new Set(data.map((e) => e.seq)));
}

function renderFeed(nuevos = new Set()) {
  const tbody = $("#tabla-feed tbody");
  $("#feed-count").textContent = `${fmt(S.nLegit + S.nAttack)} solicitudes · mostrando las últimas ${S.feed.length}`;
  if (!S.feed.length) {
    tbody.innerHTML = `<tr class="empty"><td colspan="7">Aún no hay solicitudes. Corre el experimento o usa el disparo manual.</td></tr>`;
    return;
  }
  tbody.innerHTML = S.feed.map((e) => `
    <tr class="${nuevos.has(e.seq) ? "nuevo" : ""}">
      <td class="mono">${hora(e.ts)}</td>
      <td><span class="chip">${esc(e.origen)}</span></td>
      <td>${esc(etiqueta(e.tipo))}</td>
      <td>${e.clase === "ataque" ? `<span class="estado bad">✕ ataque</span>` : `<span class="estado ok">✓ legítima</span>`}</td>
      <td class="mono">${e.status}</td>
      <td>${decision(e)}</td>
      <td class="num">${fmt(e.ms, 1)}</td>
    </tr>`).join("");
}

// ----------------------------------------------------------- animación
const vertical = () => matchMedia("(max-width: 900px)").matches;

function viajar(track, cls, dur = 360) {
  const t = document.getElementById("track-" + track);
  const p = document.createElement("div");
  p.className = "packet " + cls;
  t.appendChild(p);
  const prop = vertical() ? "top" : "left";
  const anim = p.animate([{ [prop]: "0%" }, { [prop]: "100%" }],
    { duration: dur, easing: "ease-in-out", fill: "forwards" });
  return anim.finished.then(() => p.remove(), () => p.remove());
}

function pulso(nodo, cls) {
  const n = document.getElementById("node-" + nodo);
  n.classList.remove("ok-pulse", "bad-pulse", "alert-pulse");
  void n.offsetWidth;
  n.classList.add(cls);
  clearTimeout(n._t);
  n._t = setTimeout(() => n.classList.remove(cls), 650);
}

function destello(nodo, texto, cls) {
  const f = document.getElementById("flash-" + nodo);
  if (!f) return;
  f.textContent = texto;
  f.className = "node-flash " + cls;
  void f.offsetWidth;
  f.classList.add("show");
}

async function animarEvento(e) {
  S.animando++;
  try {
    const cls = e.clase === "ataque" ? "attack" : "legit";
    await viajar(0, cls);
    if (e.status === 401) { destello("siniestros", "401 sin token", "warn"); return; }
    if (e.status === 503) {
      await viajar(1, "dead");
      pulso("siniestros", "alert-pulse");
      destello("siniestros", "503 · fail-closed", "warn");
      return;
    }
    await viajar(1, cls);
    if (e.status >= 200 && e.status < 300) {
      pulso("verificador", "ok-pulse");
      destello("verificador", "✓ autorizada", "ok");
      pulso("siniestros", "ok-pulse");
      destello("siniestros", e.tipo.endsWith("consulta") ? "✓ consulta" : "✓ aprobada", "ok");
      return;
    }
    pulso("verificador", "bad-pulse");
    destello("verificador", "✕ " + (MOTIVO[e.motivo]?.nombre || e.motivo || "negada"), "bad");
    if (MOTIVO[e.motivo]) {
      await viajar(2, "alert", 300);
      pulso("bus", "alert-pulse");
      await viajar(3, "alert", 300);
      pulso("auditoria", "alert-pulse");
    }
  } finally {
    S.animando--;
  }
}

// ============================================================ CONTROLES
async function cargarCatalogo() {
  const { ok, data } = await api("/api/catalogo");
  if (!ok) return;
  S.catalogo = data;
  const opciones = (lista) => lista.map((c) => `<option value="${esc(c.tipo)}">${esc(etiqueta(c.tipo))}</option>`).join("");
  $("#sel-ataque").innerHTML = opciones(data.ataques);
  $("#sel-legitima").innerHTML = opciones(data.legitimas);
  describir();
}

function describir() {
  if (!S.catalogo) return;
  const a = S.catalogo.ataques.find((c) => c.tipo === $("#sel-ataque").value);
  const l = S.catalogo.legitimas.find((c) => c.tipo === $("#sel-legitima").value);
  $("#desc-ataque").innerHTML = a ? `${esc(a.descripcion)}<br>Esperado: ${motivoChip(a.motivo_esperado)}` : "—";
  $("#desc-legitima").innerHTML = l ? `${esc(l.descripcion)}<br>Esperado: <span class="estado ok">✓ autorizada</span>` : "—";
}
$("#sel-ataque").addEventListener("change", describir);
$("#sel-legitima").addEventListener("change", describir);

async function disparar(escenario) {
  const r = await api("/api/solicitud", { method: "POST", body: { escenario } });
  const box = $("#manual-result");
  box.classList.remove("hidden");
  if (!r.ok) {
    box.className = "result bad";
    box.innerHTML = `<span class="big">Error</span><br>${esc(r.data?.error || "HTTP " + r.status)}`;
    return r;
  }
  const e = r.data;
  const esAtaque = e.clase === "ataque";
  const detectado = esAtaque && e.status === 403 && MOTIVO[e.motivo];
  const correcto = esAtaque ? detectado : e.status >= 200 && e.status < 300;
  box.className = "result " + (e.status === 503 ? "warn" : correcto ? "ok" : "bad");
  box.innerHTML = `
    <div class="big">HTTP ${e.status} · ${decision(e)}</div>
    <div class="muted">${esc(etiqueta(e.tipo))} · ${fmt(e.ms, 1)} ms · <span class="mono">${esc(e.solicitud_id)}</span></div>
    <div>${detectado ? "🚨 Alerta de intrusión emitida al bus de auditoría"
      : esAtaque ? "⚠ El ataque no fue detectado como intrusión"
      : e.status === 503 ? "El verificador no respondió: Siniestros negó la operación"
      : "Sin alerta: la solicitud es legítima"}</div>`;
  pollEventos();
  return r;
}

$("#btn-ataque").addEventListener("click", () => disparar($("#sel-ataque").value));
$("#btn-legitima").addEventListener("click", () => disparar($("#sel-legitima").value));
$("#btn-todos").addEventListener("click", async (ev) => {
  const btn = ev.currentTarget;
  btn.disabled = true;
  for (const c of S.catalogo?.ataques || []) {
    await disparar(c.tipo);
    await new Promise((r) => setTimeout(r, 450));
  }
  btn.disabled = false;
});

// ------------------------------------------------------ fuente de verdad
async function cargarUsuarios() {
  const { ok, data } = await api("/api/usuarios");
  const tbody = $("#tabla-usuarios tbody");
  if (!ok || !Array.isArray(data)) {
    tbody.innerHTML = `<tr><td class="muted">Verificador no disponible</td></tr>`;
    return;
  }
  const roles = ["AtencionCliente", "LiquidadorSiniestros"];
  tbody.innerHTML = data.map((u) => `
    <tr data-u="${esc(u.usuario)}">
      <td>${esc(u.usuario)}</td>
      <td><select data-campo="rol" aria-label="Rol de ${esc(u.usuario)}">${roles.map((r) =>
        `<option ${r === u.rol ? "selected" : ""}>${r}</option>`).join("")}</select></td>
      <td><label class="small"><input type="checkbox" data-campo="activo" ${u.activo ? "checked" : ""}> activo</label></td>
    </tr>`).join("");
}

$("#tabla-usuarios").addEventListener("change", async (ev) => {
  const campo = ev.target.dataset.campo;
  const tr = ev.target.closest("tr");
  if (!campo || !tr) return;
  const valor = campo === "activo" ? ev.target.checked : ev.target.value;
  const r = await api(`/api/usuarios/${encodeURIComponent(tr.dataset.u)}`, { method: "PUT", body: { [campo]: valor } });
  if (r.ok) {
    tr.classList.add("changed");
    feedback(`${tr.dataset.u}: ${campo} → ${valor}. Sus tokens anteriores ya no sirven.`, "ok");
  } else {
    feedback(r.data?.error || "No se pudo actualizar", "error");
    cargarUsuarios();
  }
});

// ------------------------------------------------- verificador on/off
async function controlarVerificador(accion) {
  $("#btn-stop").disabled = $("#btn-start").disabled = true;
  feedback(accion === "stop" ? "Apagando verificador…" : "Encendiendo verificador…");
  const r = await api(`/api/verificador/${accion}`, { method: "POST" });
  if (r.ok) {
    feedback(accion === "stop" ? "Verificador apagado: prueba una solicitud legítima (debe dar 503)."
      : "Verificador encendido.", "ok");
  } else {
    feedback(`Hazlo a mano: ${r.data?.manual || "docker " + accion + " verificador-autorizacion"}`, "error");
  }
  pollEstado();
}
$("#btn-stop").addEventListener("click", () => controlarVerificador("stop"));
$("#btn-start").addEventListener("click", () => controlarVerificador("start"));

$("#btn-reset").addEventListener("click", async () => {
  if (!confirm("¿Borrar aprobaciones, alertas y contadores, y devolver los roles a su valor inicial?")) return;
  const r = await api("/api/reset", { method: "POST" });
  if (r.ok) {
    S.feed = []; S.nLegit = 0; S.nAttack = 0;
    S.alertasConocidas.clear(); S.alertasFirma = "";
    setNum("n-legit", 0); setNum("n-attack", 0);
    renderFeed();
    cargarUsuarios();
    feedback("Datos reiniciados.", "ok");
    pollAlertas();
  } else {
    feedback(r.data?.error || "No se pudo reiniciar", "error");
  }
});

$("#banner-close").addEventListener("click", () => {
  S.bannerCerrado = true;
  $("#manual-banner").classList.add("hidden");
});

// ======================================================== EXPERIMENTO
const pausa = $("#in-pausa");
pausa.addEventListener("input", () => ($("#out-pausa").textContent = pausa.value + " ms"));

$("#btn-iniciar").addEventListener("click", async () => {
  const body = {
    legitimas: parseInt($("#in-legitimas").value, 10),
    ataques: parseInt($("#in-ataques").value, 10),
    latencia: parseInt($("#in-latencia").value, 10),
    pausa_ms: parseInt(pausa.value, 10),
  };
  const r = await api("/api/experimento/iniciar", { method: "POST", body });
  if (!r.ok) {
    toast(`⚠ ${esc(r.data?.error || "No se pudo iniciar")}`);
    return;
  }
  S.feed = []; S.nLegit = 0; S.nAttack = 0;
  setNum("n-legit", 0); setNum("n-attack", 0);
  renderFeed();
  $("#btn-iniciar").disabled = true;
  $("#progress").classList.remove("hidden");
  pollExperimento();
});

async function pollExperimento() {
  const { ok, data: st } = await api("/api/experimento/estado");
  if (!ok || !st) return;
  // Una corrida que ya había terminado al abrir la página se muestra sin toast ni cambio de pestaña.
  const alAbrir = !S.expVisto;
  S.expVisto = true;
  if (st.status === "idle") return;
  const corriendo = st.status === "running";
  $("#btn-iniciar").disabled = corriendo;
  $("#progress").classList.remove("hidden");

  const idx = st.status === "done" ? FASES.length : FASES.indexOf(st.fase);
  $$("#steps li").forEach((li, i) => {
    li.className = i < idx ? "done" : i === idx && corriendo ? "current" : "";
  });
  const frac = st.total ? st.hechas / st.total : 0;
  const avance = { preparando: 0.03, enviando: 0.05 + 0.65 * frac, auditando: 0.72,
    midiendo_latencia: 0.75 + 0.23 * frac, reporte: 1 }[st.fase] ?? 0;
  $("#bar-fill").style.width = (st.status === "done" ? 100 : avance * 100).toFixed(1) + "%";

  const p = st.parcial || {};
  const meta = $("#progress-meta");
  if (st.status === "error") {
    meta.innerHTML = `<span class="estado bad">✕ La corrida falló:</span> ${esc(st.error)}`;
  } else if (st.status === "done") {
    meta.innerHTML = `<span class="estado ok">✓ Terminado</span> · ${fmt(p.enviadas)} solicitudes · revisa la pestaña Resultados`;
  } else {
    const cuenta = st.total && ["enviando", "midiendo_latencia"].includes(st.fase) ? ` ${fmt(st.hechas)}/${fmt(st.total)}` : "";
    meta.innerHTML = `${esc(NOMBRE_FASE[st.fase] || st.fase)}${cuenta} · ✓ ${fmt(p.legitimas_ok)} legítimas OK · ✕ ${fmt(p.ataques_bloqueados)} ataques bloqueados`;
  }

  if (st.status === "done" && S.corridaVista !== st.started_at) {
    S.corridaVista = st.started_at;
    S.reporte = st.reporte;
    await cargarHistorial();
    renderResultados(S.reporte);
    if (!alAbrir) {
      const okH = S.reporte.hipotesis_confirmada;
      toast(okH ? "✅ Experimento terminado: <b>hipótesis confirmada</b>" : "❌ Experimento terminado: hipótesis <b>no</b> confirmada");
      $("#tab-dot-resultados").classList.remove("hidden");
      setTimeout(() => irATab("resultados"), 1200);
    }
  }
}

// ===================================================== CENTRO DE ALERTAS
async function pollAlertas() {
  const { ok, data } = await api("/api/alertas?limite=500");
  if (!ok || !data) return;
  const firma = `${data.total}|${data.alertas[0]?.alerta_id || ""}|${data.duplicados}`;
  if (firma === S.alertasFirma && S.tab !== "alertas") return;
  const cambio = firma !== S.alertasFirma;
  S.alertasFirma = firma;
  S.alertas = data;
  if (S.tab === "alertas" && cambio) renderAlertas();
}

function renderAlertas() {
  const d = S.alertas;
  if (!d) return;
  const ahora = Date.now() / 1000;
  setNum("a-total", d.total);
  setNum("a-minuto", d.alertas.filter((a) => a.registrado_ts > ahora - 60).length);
  $("#a-p50").textContent = d.latencia_registro_ms.p50 == null ? "–" : fmt(d.latencia_registro_ms.p50, 1) + " ms";
  $("#a-p95").textContent = d.latencia_registro_ms.p95 == null ? "–" : fmt(d.latencia_registro_ms.p95, 1) + " ms";
  setNum("a-usuarios", new Set(d.alertas.map((a) => a.usuario)).size);
  setNum("a-dup", d.duplicados);

  const total = d.total || 0;
  barrasH($("#chart-motivos"), MOTIVOS.map((m) => ({
    label: m.nombre, value: d.por_motivo[m.id] || 0, color: m.color,
    tip: `<div class="t-title">${esc(m.nombre)}</div>${esc(m.regla)}` +
      filaTip(m.color, "Alertas", `${fmt(d.por_motivo[m.id] || 0)} (${total ? fmt(100 * (d.por_motivo[m.id] || 0) / total) : 0} %)`),
  })), "Alertas por motivo");

  // Usuarios con más alertas: una sola serie, en color neutro (no es un motivo).
  const porUsuario = {};
  d.alertas.forEach((a) => {
    const u = a.usuario || "(sin usuario)";
    porUsuario[u] ??= { n: 0, motivos: {} };
    porUsuario[u].n++;
    porUsuario[u].motivos[a.motivo] = (porUsuario[u].motivos[a.motivo] || 0) + 1;
  });
  const top = Object.entries(porUsuario).sort((a, b) => b[1].n - a[1].n).slice(0, 5);
  if (top.length) {
    barrasH($("#chart-usuarios"), top.map(([u, info]) => ({
      label: u, value: info.n, color: "var(--muted)",
      tip: `<div class="t-title">${esc(u)}</div>` +
        MOTIVOS.filter((m) => info.motivos[m.id]).map((m) => filaTip(m.color, m.nombre, fmt(info.motivos[m.id]))).join(""),
    })), "Usuarios con más alertas");
  } else {
    $("#chart-usuarios").innerHTML = `<div class="chart-empty">Sin alertas todavía.</div>`;
  }

  columnasTiempo($("#chart-tiempo"), d.alertas);
  $("#legend-tiempo").innerHTML = MOTIVOS.map((m) =>
    `<span><i class="sw" style="background:${m.color}"></i>${esc(m.nombre)}</span>`).join("");

  renderFiltros();
  renderTablaAlertas();
}

function renderFiltros() {
  const d = S.alertas;
  const chips = [{ id: null, nombre: "Todos", n: d.total, color: "var(--muted)" },
    ...MOTIVOS.map((m) => ({ ...m, n: d.por_motivo[m.id] || 0 }))];
  $("#filtro-motivos").innerHTML = chips.map((c) => `
    <button class="fchip ${S.filtro === c.id ? "on" : ""}" data-id="${c.id ?? ""}" style="--c:${c.color}">
      ${c.id ? "<i></i>" : ""}${esc(c.nombre)} <b>${fmt(c.n)}</b></button>`).join("");
}
$("#filtro-motivos").addEventListener("click", (ev) => {
  const b = ev.target.closest(".fchip");
  if (!b) return;
  S.filtro = b.dataset.id || null;
  renderFiltros();
  renderTablaAlertas();
});
$("#buscar").addEventListener("input", (ev) => {
  S.busqueda = ev.target.value.trim().toLowerCase();
  renderTablaAlertas();
});

function renderTablaAlertas() {
  const tbody = $("#tabla-alertas tbody");
  const filas = S.alertas.alertas.filter((a) =>
    (!S.filtro || a.motivo === S.filtro) &&
    (!S.busqueda || `${a.usuario} ${a.solicitud_id} ${a.recurso}`.toLowerCase().includes(S.busqueda)));
  if (!filas.length) {
    tbody.innerHTML = `<tr class="empty"><td colspan="7">${S.alertas.total ? "Ninguna alerta coincide con el filtro." : "Sin alertas registradas."}</td></tr>`;
    return;
  }
  const primera = S.alertasConocidas.size === 0;
  tbody.innerHTML = filas.map((a) => {
    const nueva = !primera && !S.alertasConocidas.has(a.alerta_id);
    const real = a.rol_real ? `<span class="real">${esc(a.rol_real)}</span>`
      : `<span class="none">${a.motivo === "USUARIO_DESCONOCIDO" ? "no existe" : "no verificado"}</span>`;
    return `<tr class="${nueva ? "nuevo" : ""}">
      <td class="mono">${hora(a.registrado_ts)}</td>
      <td>${motivoChip(a.motivo)}</td>
      <td class="mono">${esc(a.usuario || "—")}</td>
      <td><span class="roles">${esc(a.rol_declarado || "—")}<span class="arrow">→</span>${real}</span></td>
      <td>${esc(a.operacion)} <span class="muted">${esc(a.recurso || "")}</span></td>
      <td class="mono">${esc(a.solicitud_id)}</td>
      <td class="num">${fmt((a.registrado_ts - a.detectado_ts) * 1000, 1)} ms</td>
    </tr>`;
  }).join("");
  S.alertas.alertas.forEach((a) => S.alertasConocidas.add(a.alerta_id));
}

// ============================================================ GRÁFICOS
function anchoDe(el) { return Math.max(280, Math.floor(el.clientWidth || el.parentElement.clientWidth || 480)); }

function maxBonito(v) {
  if (v <= 0) return 1;
  const p = 10 ** Math.floor(Math.log10(v));
  const n = v / p;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * p;
}

/** Barras horizontales: una fila por categoría, valor rotulado al final. */
function barrasH(el, filas, aria) {
  const W = anchoDe(el);
  const labelW = Math.min(170, Math.round(W * 0.36));
  const valW = 48;
  const rowH = 34;
  const barH = 14;
  const plotW = W - labelW - valW;
  const H = filas.length * rowH;
  const max = Math.max(1, ...filas.map((f) => f.value));
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(aria)}">`;
  filas.forEach((f, i) => {
    const y = i * rowH;
    const yb = y + (rowH - barH) / 2;
    const w = f.value ? Math.max(4, (plotW - 4) * f.value / max) : 0;
    s += `<text class="lbl" x="0" y="${y + rowH / 2 + 4}">${esc(f.label)}</text>`;
    s += `<rect x="${labelW}" y="${yb}" width="${plotW - 4}" height="${barH}" rx="4" style="fill:var(--bg)"/>`;
    s += w ? `<rect class="mark" x="${labelW}" y="${yb}" width="${w}" height="${barH}" rx="4" style="fill:${f.color}"/>` : `<g></g>`;
    s += `<rect class="hit" data-i="${i}" x="0" y="${y}" width="${W}" height="${rowH}"/>`;
    s += `<text class="val" x="${W}" y="${y + rowH / 2 + 4}" text-anchor="end">${fmt(f.value)}</text>`;
  });
  el.innerHTML = s + "</svg>";
  enlazarTips(el, filas.map((f) => f.tip));
}

/** Columnas apiladas por motivo a lo largo del tiempo (intervalo adaptativo). */
function columnasTiempo(el, alertas) {
  if (!alertas.length) {
    el.innerHTML = `<div class="chart-empty">Sin alertas todavía.</div>`;
    return;
  }
  const ts = alertas.map((a) => a.registrado_ts);
  const t0 = Math.floor(Math.min(...ts));
  const t1 = Math.ceil(Math.max(...ts));
  const pasos = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 1800, 3600];
  const paso = pasos.find((p) => (t1 - t0) / p <= 36) || 3600;
  const inicio = Math.floor(t0 / paso) * paso;
  const n = Math.max(1, Math.ceil((t1 - inicio + 1) / paso));
  const cubetas = Array.from({ length: n }, () => Object.fromEntries(MOTIVOS.map((m) => [m.id, 0])));
  alertas.forEach((a) => {
    const i = Math.min(n - 1, Math.floor((a.registrado_ts - inicio) / paso));
    if (cubetas[i][a.motivo] != null) cubetas[i][a.motivo]++;
  });
  $("#hint-tiempo").textContent = `Alertas registradas cada ${paso >= 60 ? paso / 60 + " min" : paso + " s"}, apiladas por motivo.`;

  const W = anchoDe(el);
  const H = 190;
  const m = { l: 34, r: 6, t: 8, b: 22 };
  const pw = W - m.l - m.r;
  const ph = H - m.t - m.b;
  const totales = cubetas.map((c) => Object.values(c).reduce((x, y) => x + y, 0));
  // Conteos: marcas enteras (paso 1, 2, 5, 10…) para no rotular 2,5 alertas.
  const minimo = Math.max(1, Math.ceil(Math.max(...totales) / 4));
  const p10 = 10 ** Math.floor(Math.log10(minimo));
  const paso_y = [1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10].map((f) => Math.round(f * p10)).find((s) => s >= minimo);
  const max = paso_y * 4;
  const bw = pw / n;
  const barW = Math.max(3, Math.min(28, bw - 2));
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Alertas en el tiempo">`;
  for (let k = 0; k <= 4; k++) {
    const y = m.t + ph - ph * k / 4;
    s += `<line class="grid" x1="${m.l}" x2="${W - m.r}" y1="${y}" y2="${y}"/>`;
    s += `<text x="${m.l - 6}" y="${y + 4}" text-anchor="end">${fmt(paso_y * k)}</text>`;
  }
  const tips = [];
  cubetas.forEach((c, i) => {
    const x = m.l + i * bw + (bw - barW) / 2;
    let y = m.t + ph;
    let g = "";
    MOTIVOS.forEach((mo) => {
      if (!c[mo.id]) return;
      const h = ph * c[mo.id] / max;
      const hv = Math.max(1, h - 2); // 2 px de separación entre segmentos
      y -= h;
      g += `<rect x="${x}" y="${y + (h - hv)}" width="${barW}" height="${hv}" rx="${Math.min(3, hv / 2)}" style="fill:${mo.color}"/>`;
    });
    s += `<g class="mark">${g}</g>`;
    s += `<rect class="hit" data-i="${i}" x="${m.l + i * bw}" y="${m.t}" width="${bw}" height="${ph}"/>`;
    const desde = inicio + i * paso;
    tips.push(`<div class="t-title">${hora(desde)} – ${hora(desde + paso)}</div>` +
      MOTIVOS.map((mo) => filaTip(mo.color, mo.nombre, fmt(c[mo.id]))).join("") +
      `<div class="t-row">Total<b>${fmt(totales[i])}</b></div>`);
  });
  s += `<line class="axis" x1="${m.l}" x2="${W - m.r}" y1="${m.t + ph}" y2="${m.t + ph}"/>`;
  const marcas = n <= 3 ? [...Array(n).keys()] : [0, Math.floor((n - 1) / 2), n - 1];
  marcas.forEach((i) => {
    const anchor = i === 0 ? "start" : i === n - 1 ? "end" : "middle";
    const x = i === 0 ? m.l : i === n - 1 ? W - m.r : m.l + (i + 0.5) * bw;
    s += `<text x="${x}" y="${H - 4}" text-anchor="${anchor}">${hora(inicio + i * paso)}</text>`;
  });
  el.innerHTML = s + "</svg>";
  enlazarTips(el, tips);
}

/** Histogramas de latencia como múltiplos pequeños con la misma escala x. */
function histogramas(el, muestras) {
  const todas = SERIES_LAT.flatMap((s) => muestras[s.id] || []);
  if (!todas.length) { el.innerHTML = `<div class="chart-empty">Sin muestras.</div>`; return; }
  const ordenadas = [...todas].sort((a, b) => a - b);
  const tope = maxBonito(ordenadas[Math.floor(0.99 * (ordenadas.length - 1))] * 1.05);
  const nb = 30;
  const ancho = tope / nb;
  const W = anchoDe(el);
  const m = { l: 8, r: 8, t: 22, b: 24 };
  const alto = 70;
  const sep = 26;
  const H = m.t + SERIES_LAT.length * alto + (SERIES_LAT.length - 1) * sep + m.b;
  const pw = W - m.l - m.r;
  const bw = pw / nb;
  const conteos = SERIES_LAT.map((s) => {
    const c = new Array(nb).fill(0);
    (muestras[s.id] || []).forEach((v) => c[Math.min(nb - 1, Math.floor(v / ancho))]++);
    return c;
  });
  const maxC = Math.max(...conteos.flat(), 1);
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Distribución de latencias">`;
  const tips = [];
  let idx = 0;
  SERIES_LAT.forEach((serie, k) => {
    const y0 = m.t + k * (alto + sep);
    const base = y0 + alto;
    s += `<text class="lbl" x="${m.l}" y="${y0 - 8}">${esc(serie.nombre)}</text>`;
    conteos[k].forEach((c, i) => {
      const h = alto * c / maxC;
      const x = m.l + i * bw + 1;
      s += c ? `<rect class="mark" x="${x}" y="${base - h}" width="${Math.max(1, bw - 2)}" height="${h}" rx="${Math.min(3, h / 2)}" style="fill:${serie.color}"/>` : `<g></g>`;
      s += `<rect class="hit" data-i="${idx}" x="${m.l + i * bw}" y="${y0}" width="${bw}" height="${alto}"/>`;
      const desde = i * ancho;
      tips[idx++] = `<div class="t-title">${esc(serie.nombre)}</div>` +
        filaTip(serie.color, `${fmt(desde, 1)}–${i === nb - 1 ? "∞" : fmt(desde + ancho, 1)} ms`, `${fmt(c)} solicitudes`);
    });
    s += `<line class="axis" x1="${m.l}" x2="${W - m.r}" y1="${base}" y2="${base}"/>`;
  });
  for (let k = 0; k <= 4; k++) {
    const x = m.l + pw * k / 4;
    s += `<text x="${x}" y="${H - 6}" text-anchor="${k === 0 ? "start" : k === 4 ? "end" : "middle"}">${fmt(tope * k / 4, tope < 20 ? 1 : 0)}${k === 4 ? " ms" : ""}</text>`;
  }
  el.innerHTML = s + "</svg>";
  enlazarTips(el, tips);
}

// ============================================================ RESULTADOS
function criterio(nombre, cumple, valorHtml, metaTxt, meterHtml, detalle) {
  return `<div class="crit">
    <div class="crit-head"><span class="crit-name">${esc(nombre)}</span>
      <span class="estado ${cumple ? "ok" : "bad"}">${cumple ? "✓ Cumple" : "✕ No cumple"}</span></div>
    <div class="crit-value">${valorHtml}</div>
    ${meterHtml}
    <div class="crit-meta">${metaTxt}</div>
    <div class="crit-meta">${detalle}</div>
  </div>`;
}

function medidor(pct, ok, marca) {
  const p = Math.max(0, Math.min(100, pct));
  return `<div class="meter"><div class="meter-fill ${ok ? "ok" : "bad"}" style="width:${p}%"></div>${marca || ""}</div>`;
}

function renderResultados(r) {
  if (!r) return;
  $("#res-vacio").classList.add("hidden");
  $("#res-contenido").classList.remove("hidden");

  const ok = r.hipotesis_confirmada;
  $("#verdict").classList.toggle("fail", !ok);
  $("#verdict-icon").textContent = ok ? "✓" : "✕";
  $("#verdict-title").textContent = ok ? "Hipótesis confirmada" : "Hipótesis no confirmada";
  const pr = r.parametros;
  $("#verdict-sub").innerHTML = `ASR-SEG-09 · ${esc(new Date(r.fecha).toLocaleString("es-CO"))} · ` +
    `${fmt(pr.legitimas)} solicitudes legítimas, ${fmt(pr.ataques)} ataques y ${fmt(pr.latencia)} pares de latencia (semilla ${pr.semilla}).<br>` +
    (ok ? "El verificador central detectó todas las elevaciones de privilegio sin afectar a los usuarios legítimos y dentro del presupuesto de latencia."
      : "Al menos un criterio no se cumplió; revisa las tarjetas y la tabla por escenario.");

  const ataques = Object.keys(r.por_tipo).filter((t) => r.descripciones?.[t]?.motivo_esperado !== "OK");
  const legitimas = Object.keys(r.por_tipo).filter((t) => r.descripciones?.[t]?.motivo_esperado === "OK");
  const suma = (tipos, k) => tipos.reduce((acc, t) => acc + (r.por_tipo[t][k] || 0), 0);
  const nAtq = suma(ataques, "enviadas");
  const nDet = suma(ataques, "detectadas");
  const nLeg = suma(legitimas, "enviadas");
  const nFp = suma(legitimas, "falsos_positivos");
  const cumple = (prefijo) => Object.entries(r.cumple).find(([k]) => k.startsWith(prefijo))?.[1];
  const sc = r.latencia.sobrecosto_ms;
  const meta = 50;
  const escala = Math.max(60, sc.p95 * 1.2);

  $("#criteria").innerHTML = [
    criterio("Detección de intrusiones", cumple("deteccion"),
      `${fmt(r.deteccion_pct, 1)}<small>%</small>`, "Meta: 100 %",
      medidor(r.deteccion_pct, cumple("deteccion")),
      `${fmt(nDet)} de ${fmt(nAtq)} ataques con alerta · ${fmt(r.bloqueo_pct, 1)} % bloqueados (403)`),
    criterio("Falsos positivos", cumple("falsos"),
      `${fmt(r.falsos_positivos_pct, 1)}<small>%</small>`, "Meta: 0 %",
      medidor(r.falsos_positivos_pct, cumple("falsos")),
      `${fmt(nFp)} de ${fmt(nLeg)} solicitudes legítimas rechazadas o alertadas`),
    criterio("Integridad", cumple("integridad"),
      `${fmt(r.aprobaciones_indebidas)}`, "Meta: 0 aprobaciones indebidas",
      medidor(r.aprobaciones_indebidas ? 100 : 0, cumple("integridad")),
      "Aprobaciones ejecutadas por solicitudes de ataque"),
    criterio("Sobrecosto de latencia (p95)", cumple("sobrecosto"),
      `${fmt(sc.p95, 1)}<small>ms</small>`, `Meta: menos de ${meta} ms · p50 ${fmt(sc.p50, 1)} ms`,
      medidor(100 * Math.max(0, sc.p95) / escala, cumple("sobrecosto"),
        `<div class="meter-mark" style="left:${100 * meta / escala}%"><span>meta ${meta} ms</span></div>`),
      "&nbsp;"),
  ].join("");

  // Tabla por escenario
  const fila = (t) => {
    const d = r.por_tipo[t];
    const info = r.descripciones?.[t] || {};
    const esAtaque = info.motivo_esperado !== "OK";
    const bien = esAtaque ? d.detectadas : d.enviadas - d.falsos_positivos;
    const pct = d.enviadas ? 100 * bien / d.enviadas : 0;
    const completo = bien === d.enviadas;
    const extra = esAtaque ? ` · ${fmt(d.bloqueadas)} bloqueadas` : d.falsos_positivos ? ` · ${fmt(d.falsos_positivos)} falsos positivos` : "";
    return `<tr>
      <td><b>${esc(etiqueta(t))}</b></td>
      <td class="muted">${esc(info.descripcion || "")}</td>
      <td>${esAtaque ? motivoChip(info.motivo_esperado) : `<span class="estado ok">✓ autorizada</span>`}</td>
      <td class="num">${fmt(d.enviadas)}</td>
      <td><div class="ratio">${medidor(pct, completo)}<span>${fmt(bien)}/${fmt(d.enviadas)}</span></div>
        <div class="small ${completo ? "muted" : "estado bad"}">${esAtaque ? "detectadas" : "autorizadas"}${extra}</div></td>
    </tr>`;
  };
  $("#tabla-escenarios tbody").innerHTML =
    `<tr class="group"><td colspan="5">Ataques (vulnerabilidad materializada)</td></tr>` + ataques.map(fila).join("") +
    `<tr class="group"><td colspan="5">Solicitudes legítimas</td></tr>` + legitimas.map(fila).join("");

  // Latencia
  const L = r.latencia;
  const latStat = (nombre, color, v, signo = "") => `
    <div class="lat-stat"><div class="ls-name">${color ? `<i style="--c:${color}"></i>` : ""}${nombre}</div>
      <div class="ls-val">${signo}${fmt(v.p50, 1)} <small>ms p50</small></div>
      <div class="ls-val sec">${signo}${fmt(v.p95, 1)} <small>ms p95</small></div></div>`;
  $("#lat-stats").innerHTML =
    latStat("RBAC local", "var(--s-local)", L.rbac_local_ms) +
    latStat("Verificador central", "var(--s-central)", L.verificador_central_ms) +
    latStat("Sobrecosto", null, sc, "+");
  if (L.muestras_ms) histogramas($("#chart-latencia"), L.muestras_ms);
  else $("#chart-latencia").innerHTML = `<div class="chart-empty">Esta corrida no guardó muestras.</div>`;
  $("#legend-latencia").innerHTML = SERIES_LAT.map((s) =>
    `<span><i class="sw" style="background:${s.color}"></i>${esc(s.nombre)}</span>`).join("");

  // Motivos de la corrida
  const pm = r.alertas.por_motivo || {};
  const totalAl = Object.values(pm).reduce((a, b) => a + b, 0);
  barrasH($("#chart-motivos-corrida"), MOTIVOS.map((m) => ({
    label: m.nombre, value: pm[m.id] || 0, color: m.color,
    tip: `<div class="t-title">${esc(m.nombre)}</div>${esc(m.regla)}` + filaTip(m.color, "Alertas", fmt(pm[m.id] || 0)),
  })), "Alertas de la corrida por motivo");
  $("#nota-motivos").innerHTML = `${fmt(totalAl)} alertas para ${fmt(nAtq)} ataques` +
    (totalAl === nAtq ? ` <span class="estado ok">✓ una por ataque</span>` : ` <span class="estado bad">✕ no cuadra</span>`) +
    ` · detección → registro p95: ${fmt(r.alertas.latencia_deteccion_a_registro_ms?.p95, 1)} ms · duplicados: ${fmt(r.alertas.duplicados)}`;

  renderHistorial();
}

async function cargarHistorial() {
  const { ok, data } = await api("/api/historial");
  if (ok && Array.isArray(data)) S.historial = data;
}

function renderHistorial() {
  const sel = $("#sel-historial");
  sel.innerHTML = S.historial.map((h) =>
    `<option value="${h.indice}" ${S.reporte?.fecha === h.fecha ? "selected" : ""}>${esc(new Date(h.fecha).toLocaleString("es-CO"))}</option>`).join("");
  sel.classList.toggle("hidden", S.historial.length < 2);
  $("#tabla-historial tbody").innerHTML = S.historial.length ? S.historial.map((h) => `
    <tr>
      <td>${esc(new Date(h.fecha).toLocaleString("es-CO"))}</td>
      <td class="num">${fmt(h.parametros.legitimas)}</td>
      <td class="num">${fmt(h.parametros.ataques)}</td>
      <td class="num">${fmt(h.deteccion_pct, 1)} %</td>
      <td class="num">${fmt(h.falsos_positivos_pct, 1)} %</td>
      <td class="num">${fmt(h.aprobaciones_indebidas)}</td>
      <td class="num">${fmt(h.sobrecosto_p95, 1)} ms</td>
      <td>${h.hipotesis_confirmada ? `<span class="estado ok">✓ Confirmada</span>` : `<span class="estado bad">✕ No confirmada</span>`}</td>
    </tr>`).join("") : `<tr class="empty"><td colspan="8">Sin corridas.</td></tr>`;
}

$("#sel-historial").addEventListener("change", async (ev) => {
  const { ok, data } = await api(`/api/historial/${ev.target.value}`);
  if (ok) { S.reporte = data; renderResultados(data); }
});

$("#btn-descargar").addEventListener("click", () => {
  if (!S.reporte) return;
  const blob = new Blob([JSON.stringify(S.reporte, null, 2)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `resultado-experimento2-${S.reporte.fecha.replace(/[:T]/g, "-")}.json`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
});

// Re-dibuja los gráficos al cambiar el ancho de la ventana.
let _resize;
addEventListener("resize", () => {
  clearTimeout(_resize);
  _resize = setTimeout(() => {
    if (S.tab === "alertas") renderAlertas();
    if (S.tab === "resultados" && S.reporte) renderResultados(S.reporte);
  }, 200);
});

// ================================================================ inicio
function cada(ms, fn) {
  let ocupado = false;
  const tick = async () => {
    if (ocupado) return;
    ocupado = true;
    try { await fn(); } finally { ocupado = false; }
  };
  tick();
  return setInterval(tick, ms);
}

cargarCatalogo();
cargarUsuarios();
cargarHistorial().then(renderHistorial);
cada(1000, pollEstado);
cada(400, pollEventos);
cada(500, pollExperimento);
cada(1500, pollAlertas);
