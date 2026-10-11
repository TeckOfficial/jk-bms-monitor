"use strict";
// ══ LANGUAGE ═════════════════════════════════════════════════════
// English by default, Czech when the browser asks for it. Override with
// ?lang=en / ?lang=cs or the button in the header (remembered per browser).
const TEXTS = {
  en: {
    overview: "Overview", cells: "Cells", system: "System",
    connecting: "Connecting…", bms_on: "BMS connected", bms_off: "BMS disconnected",
    reconnect: "Reconnecting in {n} s…", alarm: "⚠ BMS reports an alarm",
    soc_label: "State of charge", capacity: "Capacity", balance: "Balance",
    charging: "▲ Charging", discharging: "▼ Discharging",
    remain: "Remaining in battery", cell_temp: "Cell temperature", cell_diff: "Cell difference",
    peak_today: "Today's peak chg / dis",
    bal_off: "Off", bal_chg: "Chg", bal_dis: "Dis",
    trend: "Trend 24 h", leg_chg: "Chg.", leg_dis: "Dis.", reset: "↺ Reset",
    chart_empty: "Collecting data… (one sample per minute)", last_hours: "last {n} h",
    cells_unit: "cells", temps: "Temperatures", sensor1: "Sensor 1", sensor2: "Sensor 2",
    daily_peaks: "Daily peaks", peak_chg: "Peak chg ▲", peak_dis: "Peak dis ▼", bal_start: "Balance start",
    delta_cells: "Δ between cells", hi_lo: "Highest / lowest", balancer: "Balancer",
    cell_tip: "Cell {n}: {v} V", cell_tip_r: ", wire resistance {r} Ω",
    cell_tip_bad: " — MUCH HIGHER than the others, check the connection",
    device: "Device", model: "Model", serial: "Serial no.", mfg: "Manufactured", checksum_errors: "Checksum errors",
    cap_cycles: "Capacity & cycles", from_bms: "from BMS", nominal: "Nominal capacity", remaining: "Remaining",
    cycled: "Cycled", cycle_count: "Cycle count", runtime: "Running time", mos: "MOSFET chg / dis",
    bms_settings: "BMS settings", bal_from: "Balance from / delta", max_cd: "Max chg / dis",
    cells_n: "Cell count", switches: "Chg / dis / balancer", on: "ON", off: "OFF",
    sockets: "Sockets", sock_title: "Sockets by state of charge",
    sock_hint: "A socket in Auto turns on when the battery reaches its “on” level and off when it falls to its “off” level. In Manual it stays the way you set it.",
    s_on: "On", s_off: "Off", s_unreach: "Unreachable", s_auto: "⚙ Auto", s_manual: "✋ Manual",
    s_btn_on: "TURN ON", s_btn_off: "TURN OFF",
    s_rule: "on at ≥ {a} % · off at ≤ {b} %", s_by_soc: "on by state of charge · ",
    s_stale: "⚠ no data from the BMS, automation is paused", s_manual_note: "manual: the automation leaves it alone",
    s_fail: "✗ did not work: {e}",
  },
  cs: {
    overview: "Přehled", cells: "Články", system: "Systém",
    connecting: "Připojování…", bms_on: "BMS připojen", bms_off: "BMS odpojen",
    reconnect: "Znovu za {n} s…", alarm: "⚠ BMS hlásí chybu",
    soc_label: "Stav nabití", capacity: "Kapacita", balance: "Balance",
    charging: "▲ Nabíjení", discharging: "▼ Vybíjení",
    remain: "Zbývá v baterii", cell_temp: "Teplota článků", cell_diff: "Rozdíl mezi články",
    peak_today: "Dnešní špička nab. / vyb.",
    bal_off: "Vyp", bal_chg: "Nab", bal_dis: "Vyb",
    trend: "Trend 24 h", leg_chg: "Nab.", leg_dis: "Vyb.", reset: "↺ Reset",
    chart_empty: "Sbírám data… (vzorek každou minutu)", last_hours: "posledních {n} h",
    cells_unit: "článků", temps: "Teploty", sensor1: "Senzor 1", sensor2: "Senzor 2",
    daily_peaks: "Denní špičky", peak_chg: "Peak nab. ▲", peak_dis: "Peak vyb. ▼", bal_start: "Balance start",
    delta_cells: "Δ mezi články", hi_lo: "Nejvyšší / nejnižší", balancer: "Balancér",
    cell_tip: "Článek {n}: {v} V", cell_tip_r: ", odpor vodiče {r} Ω",
    cell_tip_bad: " — VÝRAZNĚ VYŠŠÍ než ostatní, zkontroluj spoj",
    device: "Zařízení", model: "Model", serial: "Sériové č.", mfg: "Výroba", checksum_errors: "Chyby přenosu",
    cap_cycles: "Kapacita & cykly", from_bms: "z BMS", nominal: "Jmenovitá kapacita", remaining: "Zbývá",
    cycled: "Nacyklováno", cycle_count: "Počet cyklů", runtime: "Doba běhu", mos: "MOSFET nab. / vyb.",
    bms_settings: "Nastavení BMS", bal_from: "Balance od / delta", max_cd: "Max nab. / vyb.",
    cells_n: "Počet článků", switches: "Nab. / vyb. / balancér", on: "ZAP", off: "VYP",
    sockets: "Zásuvky", sock_title: "Zásuvky podle nabití baterie",
    sock_hint: "Zásuvka v režimu Auto se zapne, když baterie dosáhne úrovně pro zapnutí, a vypne, když klesne na úroveň pro vypnutí. V režimu Manuál zůstane tak, jak ji nastavíš.",
    s_on: "Zapnuto", s_off: "Vypnuto", s_unreach: "Nedostupná", s_auto: "⚙ Auto", s_manual: "✋ Manuál",
    s_btn_on: "ZAPNOUT", s_btn_off: "VYPNOUT",
    s_rule: "zapne od {a} % · vypne pod {b} %", s_by_soc: "zapnuto podle nabití · ",
    s_stale: "⚠ z BMS nechodí data, automatika čeká", s_manual_note: "ručně: automatika na ni nesahá",
    s_fail: "✗ nepovedlo se: {e}",
  },
};
function pickLang(){
  let want = new URLSearchParams(location.search).get("lang");
  try{
    if(want) localStorage.setItem("jkbms-lang", want);
    else want = localStorage.getItem("jkbms-lang");
  }catch(e){}
  want = (want || navigator.language || "en").slice(0, 2).toLowerCase();
  return TEXTS[want] ? want : "en";
}
const LANG = pickLang();
// t("reconnect", {n: 4}) -> "Reconnecting in 4 s…"; unknown keys fall back to English, then to the key
function t(key, vars){
  let s = TEXTS[LANG][key] ?? TEXTS.en[key] ?? key;
  for(const k in (vars || {})) s = s.replace("{" + k + "}", vars[k]);
  return s;
}
function applyTexts(){
  document.documentElement.lang = LANG;
  document.querySelectorAll("[data-t]").forEach(el => { el.textContent = t(el.dataset.t); });
  const btn = document.getElementById("lang-btn");
  btn.textContent = LANG.toUpperCase();
  btn.addEventListener("click", () => {
    const names = Object.keys(TEXTS), next = names[(names.indexOf(LANG) + 1) % names.length];
    try{ localStorage.setItem("jkbms-lang", next); }catch(e){}
    location.href = location.pathname + "?lang=" + next + location.hash;
  });
}

// ══ TABS ═════════════════════════════════════════════════════════
// One list drives both navigations (bottom bar on phones, tabs on wide screens).
const TABS = [
  {id:"overview", icon:'<path d="M3 10.5 12 3l9 7.5V21H3z"/>'},
  {id:"cells",    icon:'<rect x="3" y="5" width="4" height="14" rx="1"/><rect x="10" y="5" width="4" height="14" rx="1"/><rect x="17" y="5" width="4" height="14" rx="1"/>'},
  {id:"system",   icon:'<line x1="4" y1="6" x2="20" y2="6"/><circle cx="9" cy="6" r="2"/><line x1="4" y1="12" x2="20" y2="12"/><circle cx="15" cy="12" r="2"/><line x1="4" y1="18" x2="20" y2="18"/><circle cx="8" cy="18" r="2"/>'},
];
const SOCKETS_TAB = {id:"sockets", icon:'<path d="M9 2v6M15 2v6"/><path d="M6 8h12v3a6 6 0 0 1-12 0z"/><path d="M12 17v5"/>'};
let socketsShown = false;      // the Sockets tab appears once the server says sockets are configured
const wantedTab = (location.hash || "").slice(1);
function tabs(){ return socketsShown ? [TABS[0], TABS[1], SOCKETS_TAB, TABS[2]] : TABS; }
let curTab = "overview";

function svgIcon(inner){
  return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
       + 'stroke-linecap="round" stroke-linejoin="round">' + inner + '</svg>';
}
function buildNav(){
  document.getElementById("tabs-top").innerHTML = tabs().map(tab =>
    `<button class="tab" data-tab-btn="${tab.id}">${svgIcon(tab.icon)}<span>${t(tab.id)}</span></button>`).join("");
  document.getElementById("tabs-bottom").innerHTML = tabs().map(tab =>
    `<button class="tbtn" data-tab-btn="${tab.id}">${svgIcon(tab.icon)}<span>${t(tab.id)}</span><span class="tdot"></span></button>`).join("");
  document.querySelectorAll("[data-tab-btn]").forEach(b =>
    b.addEventListener("click", () => showTab(b.dataset.tabBtn)));
}
function showTab(id){
  if(!tabs().some(tab => tab.id === id)) id = "overview";
  curTab = id;
  document.querySelectorAll(".tabpane").forEach(p => p.classList.toggle("on", p.dataset.tab === id));
  document.querySelectorAll("[data-tab-btn]").forEach(b => b.classList.toggle("on", b.dataset.tabBtn === id));
  if(location.hash.slice(1) !== id) history.replaceState(null, "", "#" + id);
  window.scrollTo(0, 0);
  // Hidden tabs are not repainted, so catch up from the last known state.
  // The chart also needs a visible canvas: while display:none its parent has no width.
  renderAll();
  if(id === "overview") _drawChart();
}

// ══ WEBSOCKET ════════════════════════════════════════════════════
// The server sends only the top-level keys that changed; the full state lives here.
let ws = null, wsDelay = 1000;
let state = {}, target = {};

function connectWS(){
  ws = new WebSocket((location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/ws");
  ws.onopen = () => { wsDelay = 1000; renderConn(state); };
  ws.onmessage = handleMsg;
  ws.onclose = () => {
    setConn(false, t("reconnect", {n: Math.round(wsDelay/1000)}));
    setTimeout(() => { wsDelay = Math.min(wsDelay*2, 30000); connectWS(); }, wsDelay);
  };
  ws.onerror = () => ws.close();
}
function setConn(on, txt){
  setCls(document.getElementById("conn-dot"), "dot " + (on ? "on" : "off"));
  const el = document.getElementById("conn-text");
  if(el && el.textContent !== txt) el.textContent = txt;
}

// ══ SMALL HELPERS ════════════════════════════════════════════════
// All of them touch the DOM only when the value really changed; otherwise the
// 60 fps animation loop would force needless repaints (it shows on a phone battery).
function setN(id, v, dec, suf=""){
  const el = document.getElementById(id); if(!el) return;
  const s = (v !== undefined && v !== null && !isNaN(v)) ? v.toFixed(dec)+suf : "--";
  if(el.textContent !== s) el.textContent = s;
}
function setT(id, v, suf=""){
  const el = document.getElementById(id); if(!el) return;
  const s = (v != null && v !== "") ? v+suf : "--";
  if(el.textContent !== s) el.textContent = s;
}
function setCls(el, cls){ if(el && el.className !== cls) el.className = cls; }
function setW(el, pct){
  if(!el) return;
  const s = Math.min(Math.max(pct, 0), 100) + "%";
  if(el.style.width !== s) el.style.width = s;
}
function setBar(id, v, max){ setW(document.getElementById(id), v/max*100); }
function socColor(v){ return v>70?"#34d399" : v>30?"#0ea5e9" : v>15?"#fb923c" : "#f87171"; }

// ══ SMOOTH MOTION OF THE MAIN NUMBERS ════════════════════════════
const S = {totalV:0, cur:0, pow:0, soc:0, mosT:0, t1:0, t2:0};
let animDirty = true;          // the loop goes to sleep once the numbers reach their targets

function animate(){
  requestAnimationFrame(animate);
  const s = target.summary;
  if(!s || !animDirty) return;

  const sp = 0.12;
  const tv = s.total_voltage||0, tc = s.current||0, tp = s.power||0, ts = s.soc||0;
  const tm = s.mos_temp||0, t1 = s.temp1||0, t2 = s.temp2||0;
  const gap = Math.abs(S.totalV-tv)+Math.abs(S.cur-tc)+Math.abs(S.pow-tp)
            + Math.abs(S.soc-ts)+Math.abs(S.mosT-tm)+Math.abs(S.t1-t1)+Math.abs(S.t2-t2);
  if(gap < 0.02){
    S.totalV=tv; S.cur=tc; S.pow=tp; S.soc=ts; S.mosT=tm; S.t1=t1; S.t2=t2;
    animDirty = false;
  } else {
    const lerp = (a,b) => a+(b-a)*sp;
    S.totalV=lerp(S.totalV,tv); S.cur=lerp(S.cur,tc); S.pow=lerp(S.pow,tp);
    S.soc=lerp(S.soc,ts); S.mosT=lerp(S.mosT,tm); S.t1=lerp(S.t1,t1); S.t2=lerp(S.t2,t2);
  }
  paintLive();
}

function paintLive(){
  setN("total-v", S.totalV, 2);
  setN("current",  Math.abs(S.cur), 1);
  setN("power",    Math.abs(S.pow), 0);
  setN("soc",      S.soc, 0);
  setN("mos-temp", S.mosT, 1, " °C");
  setN("temp1",    S.t1, 1, " °C");
  setN("temp2",    S.t2, 1, " °C");
  const dir = S.cur >= 0 ? "chg" : "dis";
  setCls(document.getElementById("pwr-val"), "pwr-val "+dir);
  setCls(document.getElementById("current-pill"), "pill "+dir);
  setCls(document.getElementById("pwr-dir"), "pwr-dir "+dir);
  const ps = document.getElementById("pwr-stage");
  if(ps) ps.style.setProperty("--pwr-glow", dir==="chg" ? "#34d399" : "#fb923c");
  paintGauge(S.soc);
  setBar("mos-bar", S.mosT, 80); setBar("t1-bar", S.t1, 60); setBar("t2-bar", S.t2, 60);
}

const GAUGE_CIRC = 2*Math.PI*76;
function paintGauge(soc){
  const gf = document.getElementById("g-fill"); if(!gf) return;
  const off = (GAUGE_CIRC*(1-soc/100)).toFixed(1);
  if(gf.style.strokeDashoffset !== off){
    gf.style.strokeDasharray  = GAUGE_CIRC;
    gf.style.strokeDashoffset = off;
  }
  const c = socColor(soc);
  if(gf.style.stroke !== c) gf.style.stroke = c;
}

// ══ FIRST LOAD (so the gauge does not sweep up from zero) ════════
async function seedInitial(){
  try{
    const r = await fetch("/api/status"); if(!r.ok) return;
    const d = await r.json();
    state = d; target = d;
    const s = d.summary || {};
    if(s.soc !== undefined){
      S.soc = s.soc; S.totalV = s.total_voltage||0; S.cur = s.current||0;
      S.pow = s.power||0; S.mosT = s.mos_temp||0; S.t1 = s.temp1||0; S.t2 = s.temp2||0;
      const gf = document.getElementById("g-fill");
      if(gf){ gf.style.transition = "none"; paintGauge(S.soc); setTimeout(()=>gf.style.transition="", 50); }
      paintLive();
    }
    renderAll();
  }catch(e){ console.warn("seed:", e); }
}

// ══ RENDERING ════════════════════════════════════════════════════
function handleMsg(e){
  let patch; try{ patch = JSON.parse(e.data); }catch{ return; }
  Object.assign(state, patch);       // the server sends whole keys, overwriting is enough
  target = state;
  animDirty = true;
  render(patch);
}

// `patch` says what changed. The cell grid is rebuilt only when its data
// changed AND its tab is visible. renderAll() forces everything (after a tab switch).
function render(patch){
  const has = k => k in patch;
  if(has("connected")) renderConn(state);
  if(has("summary"))   renderSummary(state);
  if(has("peaks"))     renderPeaks(state.peaks);
  if(has("device") || has("checksum_errors")) renderDevice(state);
  if(has("settings"))  renderSettings(state.settings);
  if((has("cells") || has("resistances")) && curTab === "cells")
    renderCells(state.cells, state.resistances);
  if(has("last_update")) renderStamp(state.last_update);
  if(has("sockets")) renderSockets(state.sockets);
  if(has("demo")) document.getElementById("demo-badge").hidden = !state.demo;
}
function renderAll(){ render(state); }

function renderConn(d){ setConn(!!d.connected, t(d.connected ? "bms_on" : "bms_off")); }
function renderStamp(iso){
  const el = document.getElementById("last-update");
  if(el && iso) el.textContent = new Date(iso).toLocaleString(LANG === "cs" ? "cs-CZ" : undefined);
}
function renderSummary(d){
  const s = d.summary; if(!s) return;
  const eb = document.getElementById("error-banner");
  if(eb) eb.classList.toggle("show", !!s.alarm);

  setT("sum-v", s.sum_cells); setT("avg-v", s.avg_voltage); setT("delta", s.delta_mv);
  setT("cell-delta", s.delta_mv != null ? s.delta_mv : null, " mV");
  setT("hero-delta",  s.delta_mv  != null ? s.delta_mv : null, " mV");
  setT("hero-remain", s.remain_ah != null ? s.remain_ah.toFixed(0) : null, " Ah");
  setT("hero-temp",   s.temp1 != null ? Math.max(s.temp1, s.temp2 ?? s.temp1).toFixed(1) : null, " °C");
  if(s.current !== undefined) setT("pwr-dir", t(s.current >= 0 ? "charging" : "discharging"));
  if(s.balance_action !== undefined){
    const b = t({0:"bal_off", 1:"bal_chg", 2:"bal_dis"}[s.balance_action] || "?");
    setT("balance", b); setT("cell-balance", b);
  }
  if(s.max_cell_idx != null && s.min_cell_idx != null && s.max_cell_idx >= 0)
    setT("cell-hilo", "C" + (s.max_cell_idx+1) + " / C" + (s.min_cell_idx+1));

  setT("bat-nominal", s.nominal_ah != null ? s.nominal_ah.toFixed(0) : null, " Ah");
  setT("bat-remain",  s.remain_ah  != null ? s.remain_ah.toFixed(1)  : null, " Ah");
  setT("bat-cycled",  s.cycled_ah  != null ? s.cycled_ah.toFixed(0)  : null, " Ah");
  setT("bat-cycles",  s.cycles     != null ? s.cycles : null, " ×");
  setT("bat-soh",     (s.soh != null && s.soh <= 100) ? s.soh : null, " %");
  if(s.runtime_s != null){
    const dy = Math.floor(s.runtime_s/86400), hr = Math.floor((s.runtime_s%86400)/3600);
    setT("bat-runtime", dy + " d " + hr + " h");
  }
  if(s.mos_charge != null){
    const f = b => t(b ? "on" : "off");
    setT("bat-mos", f(s.mos_charge) + " / " + f(s.mos_discharge));
  }
  // The capacity in the ring comes from the live frame: it arrives all the
  // time, while the settings frame arrives once after connecting.
  if(s.nominal_ah != null) setT("capacity", s.nominal_ah.toFixed(0), " Ah");
}
function renderPeaks(p){
  if(!p) return;
  setT("max-charge",    p.charge_a    > 0 ? p.charge_a.toFixed(1)    : null, " A");
  setT("max-discharge", p.discharge_a > 0 ? p.discharge_a.toFixed(1) : null, " A");
  setT("hero-peak", (p.charge_a > 0 || p.discharge_a > 0)
    ? p.charge_a.toFixed(0) + " / " + p.discharge_a.toFixed(0) : null, " A");
}
function renderDevice(d){
  setT("dev-errors", d.checksum_errors != null ? d.checksum_errors : null);
  const dev = d.device;
  if(!dev || !dev.name) return;
  setT("dev-model", dev.name); setT("dev-serial", dev.serial);
  setT("dev-hw", (dev.hw_version||"--") + " / " + (dev.sw_version||"--"));
  setT("dev-date", dev.mfg_date);
}
function renderSettings(c){
  if(!c || c.cell_ovp === undefined) return;
  const f = b => t(b ? "on" : "off");
  setT("set-ovpuvp", c.cell_ovp.toFixed(3) + " / " + c.cell_uvp.toFixed(3), " V");
  if(c.balance_start_v != null){
    setT("set-baldet", c.balance_start_v.toFixed(3) + " V / " + c.balance_delta_mv + " mV");
    setT("set-bal", c.balance_start_v.toFixed(3), " V");
  }
  setT("set-maxcd", c.max_charge_a.toFixed(0) + " / " + c.max_discharge_a.toFixed(0), " A");
  setT("set-cap", c.capacity_ah, " Ah");
  setT("set-cells", c.cell_count, " ×");
  if(c.charge_switch != null)
    setT("set-switches", f(c.charge_switch)+" / "+f(c.discharge_switch)+" / "+f(c.balancer_switch));
  if(state.summary && state.summary.nominal_ah == null) setT("capacity", c.capacity_ah, " Ah");
}

// ── Cells: the grid is built once, then only the numbers change ──
let _cellN = 0, _cellNodes = [];
function renderCells(cells, R){
  if(!cells || !cells.length) return;
  R = R || [];
  const grid = document.getElementById("cells");
  if(!grid) return;
  if(cells.length !== _cellN){
    grid.innerHTML = cells.map((_, i) =>
      `<div class="ci"><span class="cin">C${i+1}</span><span class="ci-tag"></span>`
      + `<span class="civ">--</span><span class="ci-r"></span></div>`).join("");
    _cellNodes = Array.from(grid.children).map(el => ({
      root: el, tag: el.children[1], val: el.children[2], res: el.children[3],
    }));
    _cellN = cells.length;
    setT("cell-count", cells.length);
  }
  const mx = Math.max(...cells), mn = Math.min(...cells), rng = (mx-mn) || 0.001;
  // A "bad connection" is judged RELATIVE to the median: an absolute limit
  // cannot work, the resistance depends on the length and gauge of the balance wires.
  let rMed = 0;
  if(R.length > 2){ const srt = [...R].sort((a,b) => a-b); rMed = srt[Math.floor(srt.length/2)]; }

  cells.forEach((v, i) => {
    const n = _cellNodes[i]; if(!n) return;
    const isMax = Math.abs(v-mx) < 0.0005;
    const isMin = Math.abs(v-mn) < 0.0005 && mx !== mn;
    const pct = (v-mn)/rng;
    const color = isMax ? "#34d399" : isMin ? "#fb923c" : `hsl(${200-pct*15},65%,${52+pct*12}%)`;
    const bclr  = isMax ? "rgba(52,211,153,.3)" : isMin ? "rgba(251,146,60,.3)" : "var(--brd)";
    const txt = v.toFixed(3);
    if(n.val.textContent !== txt) n.val.textContent = txt;
    if(n.val.style.color !== color) n.val.style.color = color;
    if(n.root.style.borderColor !== bclr) n.root.style.borderColor = bclr;
    n.root.style.setProperty("--cic", color);
    const tagTxt = isMax ? "MAX" : isMin ? "MIN" : "";
    if(n.tag.textContent !== tagTxt){
      n.tag.textContent = tagTxt;
      n.tag.className = "ci-tag" + (isMax ? " hi" : isMin ? " lo" : "");
    }
    const r = R[i];
    const badR = r != null && rMed > 0 && r > rMed*2.5;
    const rTxt = r != null ? r.toFixed(3) + "Ω" : "";
    if(n.res.textContent !== rTxt){
      n.res.textContent = rTxt;
      n.res.className = "ci-r" + (badR ? " bad" : "");
    }
    const ttl = t("cell_tip", {n: i+1, v: txt})
      + (r != null ? t("cell_tip_r", {r: r.toFixed(3)}) + (badR ? t("cell_tip_bad") : "") : "");
    if(n.root.title !== ttl) n.root.title = ttl;
  });
}

// ══ SOCKETS (optional, see jkbms/sockets.py) ═════════════════════
const SOCK_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
                + 'stroke-linejoin="round"><path d="M12 3v9"/><path d="M6.4 6.6a8 8 0 1 0 11.2 0"/></svg>';
function socketCard(d){
  return `<div class="card scard" data-sock="${d.id}">
    <div class="stitle-row">
      <div class="sorb off">${SOCK_ICON}</div>
      <div style="flex:1;min-width:0"><div class="sname"></div><div class="sstate off">--</div><div class="sreason"></div></div>
    </div>
    <div class="mode-toggle">
      <button class="mode-btn" data-act="auto">${t("s_auto")}</button>
      <button class="mode-btn" data-act="manual">${t("s_manual")}</button>
    </div>
    <div class="man-btns">
      <button class="man-btn on-btn" data-act="on">${t("s_btn_on")}</button>
      <button class="man-btn off-btn" data-act="off">${t("s_btn_off")}</button>
    </div>
  </div>`;
}
function paintSocket(d){
  const card = document.querySelector(`[data-sock="${d.id}"]`); if(!card) return;
  const manual = d.mode === "manual", on = d.on === true;
  setCls(card, "card scard" + (manual ? " manual-mode" : ""));
  setCls(card.querySelector(".sorb"), "sorb " + (on ? "on" : "off") + (manual ? " man" : ""));
  const name = card.querySelector(".sname"); if(name.textContent !== d.name) name.textContent = d.name;
  const st = card.querySelector(".sstate");
  const txt = !d.connected ? t("s_unreach") : on ? t("s_on") : t("s_off");
  if(st.textContent !== txt) st.textContent = txt;
  setCls(st, "sstate " + (!d.connected ? "off" : manual && on ? "man" : on ? "on" : "off"));
  const why = card.querySelector(".sreason");
  if(!why.dataset.error){
    const rule = t("s_rule", {a: d.on_soc, b: d.off_soc});
    const note = manual ? t("s_manual_note") : d.bms_stale ? t("s_stale") : (d.reason === "soc" ? t("s_by_soc") : "") + rule;
    if(why.textContent !== note) why.textContent = note;
    setCls(why, "sreason");
  }
  setCls(card.querySelector('[data-act="auto"]'), "mode-btn" + (manual ? "" : " active-auto"));
  setCls(card.querySelector('[data-act="manual"]'), "mode-btn" + (manual ? " active-man" : ""));
  setCls(card.querySelector(".man-btns"), "man-btns" + (manual ? " show" : ""));
}
function renderSockets(sk){
  const enabled = !!(sk && sk.enabled);
  if(enabled !== socketsShown){
    socketsShown = enabled;
    buildNav();
    showTab(enabled && wantedTab === "sockets" ? "sockets" : curTab);
  }
  if(!enabled) return;
  const row = document.getElementById("sockets-row"), ids = sk.devices.map(d => d.id).join(",");
  if(row.dataset.ids !== ids){ row.dataset.ids = ids; row.innerHTML = sk.devices.map(socketCard).join(""); }
  sk.devices.forEach(paintSocket);
}
async function socketAct(id, act){
  const why = document.querySelector(`[data-sock="${id}"] .sreason`);
  const isMode = act === "auto" || act === "manual";
  try{
    const r = await fetch("/api/sockets/" + id + (isMode ? "/mode" : "/" + act), isMode
      ? {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({mode: act})}
      : {method: "POST"});
    const j = await r.json();
    if(!r.ok) throw new Error(j.error || ("HTTP " + r.status));
    delete why.dataset.error;
    const list = (state.sockets && state.sockets.devices) || [];
    const k = list.findIndex(d => d.id === id);
    if(k >= 0) list[k] = j.socket;
    renderSockets(state.sockets);
  }catch(e){
    why.dataset.error = "1";
    why.textContent = t("s_fail", {e: e.message});
    setCls(why, "sreason bad");
    setTimeout(() => { delete why.dataset.error; renderSockets(state.sockets); }, 6000);
  }
}
function initSockets(){
  document.getElementById("sockets-row").addEventListener("click", e => {
    const btn = e.target.closest("[data-act]"), card = e.target.closest("[data-sock]");
    if(btn && card) socketAct(card.dataset.sock, btn.dataset.act);
  });
}

// ══ START (called from index.html once chart.js is loaded too) ═══
function start(){
  applyTexts();
  initSockets();
  buildNav();
  showTab((location.hash || "#overview").slice(1));
  window.addEventListener("hashchange", () => showTab((location.hash || "#overview").slice(1)));
  seedInitial();
  animate();
  connectWS();
  loadHistory();
  setInterval(loadHistory, 60000);
  window.addEventListener("resize", () => { if(curTab === "overview") _drawChart(); });
}
