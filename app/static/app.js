/* Gastos — interfaz móvil (PWA). Sin dependencias ni build: HTML + JS plano. */
"use strict";

// ------------------------------------------------------------------ utilidades
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const clp = (n) => (n < 0 ? "-$" : "$") + Math.abs(Math.round(n || 0)).toLocaleString("es-CL");
const pct = (x) => Math.round((x || 0) * 100) + "%";
const MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
const etiquetaMes = (p) => `${MESES[+p.slice(5) - 1]}-${p.slice(2, 4)}`;
const sumaMeses = (p, n) => { const i = +p.slice(0, 4) * 12 + +p.slice(5) - 1 + n; return `${String(Math.floor(i / 12)).padStart(4, "0")}-${String((i % 12) + 1).padStart(2, "0")}`; };
const hoyISO = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; };
const store = {
  get: (k) => { try { return localStorage.getItem(k); } catch { return null; } },
  set: (k, v) => { try { localStorage.setItem(k, v); } catch { /* modo privado */ } },
};

const estado = { tab: "agregar", periodo: hoyISO().slice(0, 7), op: null, seccion: null };

async function api(ruta, { method = "GET", body } = {}) {
  const headers = {};
  const t = store.get("token");
  if (t) headers.Authorization = "Bearer " + t;
  if (body) headers["Content-Type"] = "application/json";
  const r = await fetch("/api" + ruta, { method, headers, body: body ? JSON.stringify(body) : undefined });
  if (r.status === 401) {
    const nuevo = prompt("Token de acceso (APP_TOKEN del servidor):");
    if (nuevo) { store.set("token", nuevo.trim()); location.reload(); }
    throw new Error("Falta el token de acceso");
  }
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || "Error " + r.status);
  return j;
}

let toastT;
function toast(msg, ms = 3200) {
  const t = $("#toast");
  t.textContent = msg; t.hidden = false;
  clearTimeout(toastT); toastT = setTimeout(() => (t.hidden = true), ms);
}
const falla = (e) => toast("⚠️ " + e.message, 4500);

// ------------------------------------------------------------------ hoja modal genérica (formularios)
function opcionesSelect(lista, actual, vacio) {
  return (vacio !== undefined ? `<option value="">${esc(vacio)}</option>` : "") +
    lista.map((o) => `<option ${o === actual ? "selected" : ""}>${esc(o)}</option>`).join("");
}

function campoHTML([k, tipo, etq, soloNuevo], v, nuevo) {
  const op = estado.op, id = "c_" + k;
  let ctl;
  if (tipo === "cat") ctl = `<select id="${id}">${opcionesSelect(op.categorias, v, "—")}</select>`;
  else if (tipo === "tarjeta") ctl = `<select id="${id}">${opcionesSelect(op.tarjetas, v, "—")}</select>`;
  else if (tipo === "tipo") ctl = `<select id="${id}">${opcionesSelect(op.tipos, v || "Personal")}</select>`;
  else if (tipo === "bool") ctl = `<input id="${id}" type="checkbox" ${v === undefined || v ? "checked" : ""}>`;
  else if (tipo === "periodo") ctl = `<input id="${id}" type="month" value="${esc(v || "")}" ${soloNuevo && !nuevo ? "disabled" : ""}>`;
  else if (tipo === "fecha") ctl = `<input id="${id}" type="date" value="${esc(v || hoyISO())}">`;
  else if (tipo === "pct") ctl = `<input id="${id}" type="number" step="0.05" min="0" max="1" inputmode="decimal" value="${v ?? ""}" placeholder="auto">`;
  else if (tipo === "num") ctl = `<input id="${id}" type="text" inputmode="decimal" value="${esc(v ?? "")}">`;
  else ctl = `<input id="${id}" type="text" value="${esc(v ?? "")}">`;
  return `<label for="${id}">${esc(etq)}</label>${ctl}`;
}

function leerCampos(campos) {
  const o = {};
  for (const [k, tipo] of campos) {
    const el = $("#c_" + k);
    if (!el || el.disabled) continue;
    o[k] = tipo === "bool" ? (el.checked ? 1 : 0) : el.value;
  }
  return o;
}

function abrirHoja({ titulo, campos, valores = {}, nuevo = false, onGuardar, onBorrar }) {
  $("#hoja-titulo").textContent = titulo;
  $("#hoja-form").innerHTML = campos.map((c) => campoHTML(c, valores[c[0]], nuevo)).join("") +
    `<button class="btn" type="submit">Guardar</button>` +
    (onBorrar ? `<button class="btn peligro" type="button" id="hoja-borrar">Eliminar</button>` : "") +
    `<button class="btn sec" type="button" data-cerrar>Cancelar</button>`;
  $("#hoja").hidden = false;
  $("#hoja-form").onsubmit = async (e) => {
    e.preventDefault();
    try { await onGuardar(leerCampos(campos)); cerrarHoja(); } catch (err) { falla(err); }
  };
  if (onBorrar) $("#hoja-borrar").onclick = async () => {
    if (!confirm("¿Eliminar?")) return;
    try { await onBorrar(); cerrarHoja(); } catch (err) { falla(err); }
  };
}
const cerrarHoja = () => { $("#hoja").hidden = true; };
document.addEventListener("click", (e) => { if (e.target.closest("[data-cerrar]")) cerrarHoja(); });

// ------------------------------------------------------------------ Agregar (registro rápido)
const f = { monto: "", descripcion: "", categoria: "", tarjeta: "", tipo: "Personal", fecha: hoyISO() };
let ultimaTarjeta = store.get("ultima_tarjeta") || "";
let tocado = { categoria: false, tarjeta: false, tipo: false };

function montoNumero(txt) {
  const t = String(txt).replace(/[$\s]/g, "");
  if (!/^[\d.,]+$/.test(t)) return null;
  const n = parseFloat(t.replace(/\./g, "").replace(",", "."));
  return Number.isFinite(n) ? n : null;
}

function pintarChips() {
  const op = estado.op;
  $("#chips-cat").innerHTML = op.categorias.map((c) => `<button type="button" class="chip ${f.categoria === c ? "sel" : ""}" data-cat="${esc(c)}">${esc(c)}</button>`).join("");
  $("#chips-tar").innerHTML = op.tarjetas.map((c) => `<button type="button" class="chip ${f.tarjeta === c ? "sel" : ""}" data-tar="${esc(c)}">${esc(c)}</button>`).join("");
  $$("#seg-tipo button").forEach((b) => b.classList.toggle("sel", b.dataset.tipo === f.tipo));
  const n = montoNumero(f.monto);
  const p = f.tipo === "Compartido" ? op.porc_ruben : 1;
  $("#tu-parte").textContent = n === null ? (f.monto ? "se calcula al guardar" : "") : (p < 1 ? `Tu parte (${pct(p)}): ${clp(n * p)}` : "");
}

async function vistaAgregar() {
  const op = estado.op;
  if (!f.tarjeta && ultimaTarjeta && op.tarjetas.includes(ultimaTarjeta)) f.tarjeta = ultimaTarjeta;
  $("#vista").innerHTML = `
    <form id="form-agregar" autocomplete="off">
      <div class="card">
        <input id="f-monto" class="monto" inputmode="decimal" placeholder="$ 0" value="${esc(f.monto)}" aria-label="Monto">
        <div id="tu-parte" class="tu-parte"></div>
        <label for="f-desc">Descripción</label>
        <input id="f-desc" list="lista-desc" placeholder="Ej. Jumbo, Café…" value="${esc(f.descripcion)}">
        <datalist id="lista-desc"></datalist>
      </div>
      <div class="card"><h3>Categoría</h3><div class="chips" id="chips-cat"></div></div>
      <div class="card"><h3>Tarjeta</h3><div class="chips" id="chips-tar"></div></div>
      <div class="card">
        <h3>Tipo</h3>
        <div class="seg" id="seg-tipo">${op.tipos.map((t) => `<button type="button" data-tipo="${t}">${t}${t === "Compartido" ? " (" + pct(op.porc_ruben) + ")" : ""}</button>`).join("")}</div>
        <label for="f-fecha">Fecha</label><input id="f-fecha" type="date" value="${esc(f.fecha)}">
      </div>
      <button class="btn" type="submit" id="btn-guardar">Guardar gasto</button>
    </form>`;
  pintarChips();
  api("/movimientos?periodo=" + estado.periodo).then((j) => {
    const vistos = [...new Set(j.movimientos.map((m) => m.descripcion).filter(Boolean))].slice(0, 40);
    $("#lista-desc").innerHTML = vistos.map((d) => `<option value="${esc(d)}">`).join("");
  }).catch(() => {});

  $("#f-monto").oninput = (e) => { f.monto = e.target.value; pintarChips(); };
  $("#f-fecha").onchange = (e) => (f.fecha = e.target.value);
  let deb;
  $("#f-desc").oninput = (e) => {
    f.descripcion = e.target.value;
    clearTimeout(deb);
    deb = setTimeout(async () => {
      if (f.descripcion.trim().length < 2) return;
      try {
        const s = await api("/sugerir?descripcion=" + encodeURIComponent(f.descripcion));
        if (s.categoria && !tocado.categoria) f.categoria = s.categoria;
        if (s.tarjeta && !tocado.tarjeta) f.tarjeta = s.tarjeta;
        if (s.tipo && !tocado.tipo) f.tipo = s.tipo;
        pintarChips();
      } catch { /* sugerencia opcional */ }
    }, 250);
  };
  $("#chips-cat").onclick = (e) => { const b = e.target.closest("[data-cat]"); if (b) { f.categoria = f.categoria === b.dataset.cat ? "" : b.dataset.cat; tocado.categoria = true; pintarChips(); } };
  $("#chips-tar").onclick = (e) => { const b = e.target.closest("[data-tar]"); if (b) { f.tarjeta = f.tarjeta === b.dataset.tar ? "" : b.dataset.tar; tocado.tarjeta = true; pintarChips(); } };
  $("#seg-tipo").onclick = (e) => { const b = e.target.closest("[data-tipo]"); if (b) { f.tipo = b.dataset.tipo; tocado.tipo = true; pintarChips(); } };
  $("#form-agregar").onsubmit = guardarGasto;
}

async function guardarGasto(e) {
  e.preventDefault();
  if (!f.monto.trim()) return toast("Ingresa el monto");
  if (!f.categoria && !confirm("Sin categoría el gasto no cuenta en el presupuesto. ¿Guardar igual?")) return;
  const btn = $("#btn-guardar"); btn.disabled = true;
  try {
    const j = await api("/movimientos", { method: "POST", body: { ...f } });
    const m = j.movimiento;
    if (m.tarjeta) { ultimaTarjeta = m.tarjeta; store.set("ultima_tarjeta", m.tarjeta); }
    let msg = `✓ ${m.descripcion || m.categoria || "Gasto"} ${clp(m.monto)}`;
    try {
      const d = await api("/dashboard?periodo=" + m.periodo);
      const c = d.categorias.find((x) => x.categoria === m.categoria);
      if (c && c.presupuesto) msg += c.disponible >= 0 ? ` · ${m.categoria}: quedan ${clp(c.disponible)}` : ` · ${m.categoria}: pasado por ${clp(-c.disponible)}`;
    } catch { /* resumen opcional */ }
    Object.assign(f, { monto: "", descripcion: "", categoria: "", tipo: "Personal", fecha: hoyISO() });
    tocado = { categoria: false, tarjeta: false, tipo: false };
    await vistaAgregar(); toast(msg);
  } catch (err) { falla(err); } finally { const b = $("#btn-guardar"); if (b) b.disabled = false; }
}

// ------------------------------------------------------------------ Resumen (Dashboard)
function claseUso(x) { return x > 1 ? "mal" : x >= 0.9 ? "aviso" : ""; }

async function vistaResumen() {
  $("#vista").innerHTML = `<div class="vacio">Cargando…</div>`;
  const d = await api("/dashboard?periodo=" + estado.periodo);
  const alerta = d.sin_categoria > 0 ? `<div class="aviso-caja">Hay ${clp(d.sin_categoria)} en movimientos sin categoría. No cuentan en el presupuesto: asígnalos en Movimientos.</div>` : "";
  $("#vista").innerHTML = `${alerta}
    <div class="card"><div class="grid2">
      <div class="kpi"><small>Ingreso</small><b>${clp(d.ingreso)}</b></div>
      <div class="kpi"><small>Ahorro objetivo</small><b>${clp(d.ahorro_objetivo)}</b></div>
      <div class="kpi ${d.ahorro_real >= d.ahorro_objetivo ? "ok" : "mal"}"><small>Ahorro real</small><b>${clp(d.ahorro_real)}</b></div>
      <div class="kpi"><small>Disponible</small><b>${clp(d.disponible)}</b></div>
      <div class="kpi"><small>Tasa de ahorro (meta ${pct(d.meta_ahorro)})</small><b>${(d.tasa_ahorro * 100).toFixed(1)}%</b></div>
      <div class="kpi"><small>Cuotas del mes</small><b>${clp(d.cuotas_mensuales)}</b></div>
      <div class="kpi"><small>Saldo deudas/cuotas</small><b>${clp(d.saldo_deudas)}</b></div>
      <div class="kpi"><small>Saldo cuenta (Débito)</small><b>${clp(d.saldo_cuenta)}</b></div>
    </div></div>
    <div class="card"><h3>Presupuesto vs real</h3>
      ${d.categorias.map((c) => `
        <div class="cat">
          <div class="l1"><b>${esc(c.categoria)}</b><span>${clp(c.real)} <small>/ ${clp(c.presupuesto)}</small></span></div>
          <div class="barra"><i class="${claseUso(c.pct_usado)}" style="width:${Math.min(100, c.pct_usado * 100)}%"></i></div>
          <small style="color:var(--tx2)">${c.disponible >= 0 ? "Disponible " + clp(c.disponible) : "Pasado por " + clp(-c.disponible)} · ${pct(c.pct_usado)}</small>
        </div>`).join("")}
      <div class="fila"><b>Total disponible</b><b class="der">${clp(d.total_disponible)}</b></div>
    </div>
    <div class="card"><h3>Facturación por tarjeta</h3>
      ${d.tarjetas.map((t) => `<div class="fila"><div class="izq"><b>${esc(t.tarjeta)}</b><small>mov. ${clp(t.movimientos)}${t.fijos ? " · fijos " + clp(t.fijos) : ""}${t.suscripciones ? " · subs " + clp(t.suscripciones) : ""}${t.cuotas ? " · cuotas " + clp(t.cuotas) : ""}${t.otros_cargos ? " · otros " + clp(t.otros_cargos) : ""}</small></div><b class="der">${clp(t.total)}</b></div>`).join("") || '<div class="vacio">Sin tarjetas de crédito configuradas</div>'}
    </div>`;
}

// ------------------------------------------------------------------ Movimientos
const CAMPOS_MOV = [["fecha", "fecha", "Fecha"], ["descripcion", "text", "Descripción"], ["monto", "num", "Monto pagado (acepta 33550-101)"],
  ["categoria", "cat", "Categoría"], ["tipo", "tipo", "Tipo"], ["pct", "pct", "% mío (vacío = automático)"], ["tarjeta", "tarjeta", "Tarjeta"],
  ["mi_gasto", "num", "Mi gasto manual (opcional)"], ["nota", "text", "Nota"]];

async function vistaMovs() {
  $("#vista").innerHTML = `<div class="vacio">Cargando…</div>`;
  const j = await api("/movimientos?periodo=" + estado.periodo);
  const pintar = (q) => {
    const k = q.trim().toLowerCase();
    const lista = j.movimientos.filter((m) => !k || `${m.descripcion} ${m.categoria} ${m.tarjeta}`.toLowerCase().includes(k));
    $("#lista-movs").innerHTML = lista.map((m) => `
      <button class="fila tap" data-id="${m.id}">
        <div class="izq"><b>${esc(m.descripcion || "(sin descripción)")}</b>
          <small>${m.fecha.slice(8)}/${m.fecha.slice(5, 7)} · ${m.categoria ? esc(m.categoria) : '<span class="etq mal">sin categoría</span>'} · ${esc(m.tarjeta || "—")}${m.tipo === "Compartido" ? " · " + pct(m.pct) : ""}</small></div>
        <div class="der"><b>${clp(m.mi_gasto)}</b>${m.mi_gasto !== m.monto ? `<br><small>pagado ${clp(m.monto)}</small>` : ""}</div>
      </button>`).join("") || '<div class="vacio">Sin movimientos</div>';
  };
  $("#vista").innerHTML = `<div class="card"><div class="fila"><span>Mi gasto del mes</span><b class="der">${clp(j.total_mi_gasto)}</b></div></div>
    <input class="buscar" id="buscar" type="search" placeholder="Buscar descripción, categoría, tarjeta…">
    <div class="card" id="lista-movs"></div>`;
  pintar("");
  $("#buscar").oninput = (e) => pintar(e.target.value);
  $("#lista-movs").onclick = (e) => {
    const b = e.target.closest("[data-id]"); if (!b) return;
    const m = j.movimientos.find((x) => x.id === +b.dataset.id);
    abrirHoja({
      titulo: "Editar movimiento", campos: CAMPOS_MOV,
      valores: { ...m, monto: m.monto_expr || m.monto, mi_gasto: m.mi_gasto_manual ? m.mi_gasto : "" },
      onGuardar: async (v) => { const j2 = await api("/movimientos/" + m.id, { method: "PUT", body: v }); toast(j2.avisos[0] || "Guardado ✓"); vistaMovs(); },
      onBorrar: async () => { await api("/movimientos/" + m.id, { method: "DELETE" }); toast("Eliminado"); vistaMovs(); },
    });
  };
}

// ------------------------------------------------------------------ Más: ajustes y tablas auxiliares
const SECCIONES = {
  fijos: { titulo: "Gastos fijos", campos: [["concepto", "text", "Concepto"], ["monto", "num", "Monto pagado"], ["categoria", "cat", "Categoría"], ["tipo", "tipo", "Tipo"], ["pct", "num", "% mío (1 = 100%, 0.6 = 60%)"], ["tarjeta", "tarjeta", "Tarjeta (si se carga a una)"], ["desde", "periodo", "Desde"], ["hasta", "periodo", "Hasta"], ["activo", "bool", "Activo"]],
    fila: (r) => [r.concepto, `${r.categoria || "—"} · ${pct(r.pct)}`, clp(r.monto * r.pct)] },
  suscripciones: { titulo: "Suscripciones", campos: [["nombre", "text", "Nombre"], ["monto", "num", "Monto mensual"], ["tarjeta", "tarjeta", "Tarjeta"], ["desde", "periodo", "Desde"], ["hasta", "periodo", "Hasta"], ["activo", "bool", "Activa"]],
    fila: (r) => [r.nombre, r.activo ? esc(r.tarjeta || "—") : "pausada", clp(r.monto)] },
  cuotas_planes: { titulo: "Cuotas y deudas", campos: [["compra", "text", "Compra"], ["monto_total", "num", "Monto total"], ["cuota_mensual", "num", "Cuota mensual"], ["total_cuotas", "num", "Total de cuotas"], ["periodo_ref", "periodo", "Mes de referencia"], ["cuota_ref", "num", "N° de cuota en ese mes"], ["tarjeta", "tarjeta", "Tarjeta"], ["activo", "bool", "Activa"]],
    fila: (r) => [r.compra, `${r.total_cuotas} cuotas · ref. ${etiquetaMes(r.periodo_ref)} = cuota ${r.cuota_ref}`, clp(r.cuota_mensual)] },
  cargos_tarjeta: { titulo: "Otros cargos a tarjeta", campos: [["periodo", "periodo", "Mes"], ["tarjeta", "tarjeta", "Tarjeta"], ["descripcion", "text", "Descripción"], ["monto", "num", "Monto"]],
    fila: (r) => [r.descripcion || "(sin detalle)", `${etiquetaMes(r.periodo)} · ${r.tarjeta}`, clp(r.monto)] },
  depto_items: { titulo: "Gastos del depto (base del presupuesto)", campos: [["concepto", "text", "Concepto"], ["monto", "num", "Monto"], ["compartido", "bool", "Compartido (aplica % mío)"]],
    fila: (r) => [r.concepto, r.compartido ? "compartido" : "personal", clp(r.monto)] },
  categorias: { titulo: "Categorías y presupuesto", campos: [["nombre", "text", "Nombre"], ["presupuesto", "num", "Presupuesto mensual"], ["aplica_pct", "bool", "Multiplicar por % mío"], ["orden", "num", "Orden"], ["activa", "bool", "Activa"]],
    fila: (r) => [r.nombre, r.aplica_pct ? "× % mío" : "", clp(r.presupuesto)] },
  tarjetas: { titulo: "Tarjetas y medios de pago", campos: [["nombre", "text", "Nombre"], ["es_credito", "bool", "Es crédito (aparece en facturación)"], ["orden", "num", "Orden"]],
    fila: (r) => [r.nombre, r.es_credito ? "crédito" : "", ""] },
  periodos: { titulo: "Meses: ahorro, ingreso y saldo", campos: [["periodo", "periodo", "Mes", true], ["ahorro_objetivo", "num", "Ahorro objetivo"], ["ingreso", "num", "Ingreso (vacío = general)"], ["saldo_inicial_cuenta", "num", "Saldo inicial cuenta"]],
    fila: (r) => [etiquetaMes(r.periodo), r.saldo_inicial_cuenta ? "saldo ini. " + clp(r.saldo_inicial_cuenta) : "", clp(r.ahorro_objetivo || 0)] },
};

async function vistaMas() {
  if (estado.seccion) return vistaSeccion(estado.seccion);
  const cfg = await api("/config");
  $("#vista").innerHTML = `
    <div class="card"><h3>Ajustes generales</h3>
      <label for="a-ing">Ingreso mensual</label><input id="a-ing" inputmode="decimal" value="${cfg.ingreso}">
      <label for="a-pct">% mío en gastos compartidos (0.6 = 60%)</label><input id="a-pct" inputmode="decimal" value="${cfg.porc_ruben}">
      <button class="btn" id="a-guardar">Guardar ajustes</button></div>
    <div class="card"><h3>Datos</h3>${Object.entries(SECCIONES).map(([k, s]) => `<button class="fila tap" data-sec="${k}"><span>${s.titulo}</span><span class="der">›</span></button>`).join("")}</div>
    <div class="card"><h3>Acceso</h3><small style="color:var(--tx2)">Token: ${store.get("token") ? "guardado en este iPhone" : "no configurado"}</small>
      <button class="btn sec" id="a-token">Cambiar token</button></div>`;
  $("#a-guardar").onclick = async () => { try { await api("/config", { method: "PUT", body: { ingreso: $("#a-ing").value, porc_ruben: $("#a-pct").value } }); estado.op = await api("/opciones"); toast("Ajustes guardados ✓"); } catch (e) { falla(e); } };
  $("#a-token").onclick = () => { const t = prompt("Token de acceso:", store.get("token") || ""); if (t !== null) { store.set("token", t.trim()); toast("Token actualizado"); vistaMas(); } };
  $$("[data-sec]").forEach((b) => (b.onclick = () => { estado.seccion = b.dataset.sec; vistaMas(); }));
}

async function vistaSeccion(clave) {
  const s = SECCIONES[clave];
  const filas = await api("/r/" + clave);
  const pk = clave === "tarjetas" ? "nombre" : clave === "periodos" ? "periodo" : "id";
  $("#titulo").textContent = s.titulo;
  $("#vista").innerHTML = `<button class="chip" id="volver">‹ Volver</button><div style="height:10px"></div>
    <div class="card" id="lista-sec">${filas.map((r) => { const [a, b, c] = s.fila(r); return `<button class="fila tap" data-k="${esc(r[pk])}"><div class="izq"><b>${esc(a)}</b><small>${esc(b)}</small></div><b class="der">${esc(c)}</b></button>`; }).join("") || '<div class="vacio">Vacío</div>'}</div>
    <button class="btn" id="nuevo">+ Agregar</button>`;
  const recargar = async () => { estado.op = await api("/opciones"); vistaSeccion(clave); };
  $("#volver").onclick = () => { estado.seccion = null; $("#titulo").textContent = "Más"; vistaMas(); };
  $("#nuevo").onclick = () => abrirHoja({ titulo: "Nuevo", campos: s.campos, nuevo: true, onGuardar: async (v) => { await api("/r/" + clave, { method: "POST", body: v }); await recargar(); } });
  $("#lista-sec").onclick = (e) => {
    const b = e.target.closest("[data-k]"); if (!b) return;
    const r = filas.find((x) => String(x[pk]) === b.dataset.k);
    abrirHoja({ titulo: "Editar", campos: s.campos, valores: r,
      onGuardar: async (v) => { await api(`/r/${clave}/${encodeURIComponent(r[pk])}`, { method: "PUT", body: v }); await recargar(); },
      onBorrar: async () => { await api(`/r/${clave}/${encodeURIComponent(r[pk])}`, { method: "DELETE" }); await recargar(); } });
  };
}

// ------------------------------------------------------------------ navegación
const TITULOS = { agregar: "Agregar", resumen: "Resumen", movs: "Movimientos", mas: "Más" };

async function mostrar() {
  $("#titulo").textContent = TITULOS[estado.tab];
  $("#selector-mes").hidden = !(estado.tab === "resumen" || estado.tab === "movs");
  $("#mes-label").textContent = etiquetaMes(estado.periodo);
  $$("#tabs button").forEach((b) => b.classList.toggle("activo", b.dataset.tab === estado.tab));
  try {
    if (estado.tab === "agregar") await vistaAgregar();
    else if (estado.tab === "resumen") await vistaResumen();
    else if (estado.tab === "movs") await vistaMovs();
    else await vistaMas();
  } catch (e) { $("#vista").innerHTML = `<div class="vacio">No se pudo cargar.<br>${esc(e.message)}</div>`; }
}

$("#tabs").onclick = (e) => { const b = e.target.closest("[data-tab]"); if (b) { estado.tab = b.dataset.tab; estado.seccion = null; mostrar(); } };
$("#mes-prev").onclick = () => { estado.periodo = sumaMeses(estado.periodo, -1); mostrar(); };
$("#mes-next").onclick = () => { estado.periodo = sumaMeses(estado.periodo, 1); mostrar(); };

(async function iniciar() {
  try { estado.op = await api("/opciones"); } catch (e) { $("#vista").innerHTML = `<div class="vacio">No se pudo conectar.<br>${esc(e.message)}</div>`; return; }
  await mostrar();
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => {});
})();
