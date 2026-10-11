"use strict";
// ══ TREND CHART ══════════════════════════════════════════════════
// The chart window is kept in time (ms), not in sample indexes, and eases
// towards its target: the wheel zooms at the cursor, dragging pans with inertia
// and a soft bounce at the edges, two fingers pinch, a double click zooms in / resets.
//
// Identifiers are Czech. A short glossary: okno = window, kresli = draw, tik = animation tick,
// tah = drag, prsty = fingers, kotva = anchor, odhal = reveal, hotovo = ready/done,
// posun = pan, stisk = pinch, prejezd = scrub, klid = reduced motion, krok = step,
// hruby/jemny = coarse/fine, venku = outside, pres = overshoot, pust = release.
let _hData = [], _tip = null;
const GR = {f0:0, f1:0, c0:0, c1:0, d0:0, d1:0, v:0, tau:90, tah:null, prsty:{}, raf:0, cas:0,
            pMax:50, pCil:50, kx:null, odhal:1, W:0, H:0, dpr:0, hotovo:false};
const GR_MIN = 10*60e3;                         // smallest window: 10 minutes
const GR_PAD = {top:14, right:52, bottom:30, left:44};
const GR_KROKY = [1,2,5,10,15,30,60,120,180,360,720];       // minutes between time labels
let GR_KLID = false;
try{ GR_KLID = matchMedia("(prefers-reduced-motion: reduce)").matches; }catch(e){}
const _mezi = (x,a,b) => x < a ? a : x > b ? b : x;
const _hm = ms => { const d = new Date(ms); return String(d.getHours()).padStart(2,"0")+":"+String(d.getMinutes()).padStart(2,"0"); };
function _grPriblizeno(){ return GR.c1-GR.c0 < (GR.f1-GR.f0)*.985; }
function _grIndex(t){                           // first sample with time >= t (binary search)
  let a = 0, b = _hData.length;
  while(a < b){ const s = (a+b) >> 1; if(_hData[s].ms < t) a = s+1; else b = s; }
  return a;
}
function _grHezky(v){                           // rounds the power range up to 1, 2 or 5 × 10^n
  const m = Math.pow(10, Math.floor(Math.log10(v))), x = v/m;
  return (x <= 1 ? 1 : x <= 2 ? 2 : x <= 5 ? 5 : 10)*m;
}
function _rangeLabel(){
  const el = document.getElementById("chart-range"), rst = document.getElementById("chart-reset");
  if(!el || !_hData.length) return;
  // describe the full range by its length; "14:35 – 14:43" would be confusing for 24 hours
  const txt = _grPriblizeno() ? _hm(GR.c0)+" – "+_hm(GR.c1) : t("last_hours", {n: Math.round((GR.f1-GR.f0)/3600e3)});
  if(el.textContent !== txt) el.textContent = txt;
  if(rst) rst.style.display = _grPriblizeno() ? "block" : "none";
}
function chartReset(){ _grOkno(GR.f0, GR.f1, 170); }

// ---- one frame ----
function _grKresli(){
  const canvas = document.getElementById("trend-chart"), empty = document.getElementById("chart-empty");
  if(!canvas) return;
  if(_hData.length < 2 || !GR.hotovo){ if(empty) empty.style.display = "flex"; canvas.style.display = "none"; return; }
  if(empty) empty.style.display = "none";
  canvas.style.display = "block";
  const rect = canvas.parentElement.getBoundingClientRect();
  const W = rect.width || 400, H = rect.height || 240;
  if(W < 10) return;                      // the tab is hidden, nothing to draw
  const dpr = window.devicePixelRatio || 1;
  if(W !== GR.W || H !== GR.H || dpr !== GR.dpr){            // the canvas is resized only when its size changes
    GR.W = W; GR.H = H; GR.dpr = dpr;
    canvas.width = Math.round(W*dpr); canvas.height = Math.round(H*dpr);
    canvas.style.width = W+"px"; canvas.style.height = H+"px";
  }
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr,0,0,dpr,0,0); ctx.clearRect(0,0,W,H);
  const PAD = GR_PAD, pw = W-PAD.left-PAD.right, ph = H-PAD.top-PAD.bottom, span = GR.d1-GR.d0;
  const xOf = t => PAD.left+(t-GR.d0)/span*pw;
  const ySoc = v => PAD.top+ph-(v/100)*ph;
  const yPow = v => PAD.top+ph/2-(v/GR.pMax)*(ph/2);
  // visible samples plus one on each side, so the line reaches the edges
  const i0 = Math.max(0, _grIndex(GR.d0)-1), i1 = Math.min(_hData.length-1, _grIndex(GR.d1));

  ctx.font = "10px IBM Plex Mono,monospace";
  ctx.strokeStyle="#162040"; ctx.lineWidth=1; ctx.setLineDash([3,4]);
  ctx.beginPath(); ctx.moveTo(PAD.left,yPow(0)); ctx.lineTo(PAD.left+pw,yPow(0)); ctx.stroke();
  ctx.setLineDash([]);
  ctx.textBaseline="middle"; ctx.textAlign="right";
  [0,25,50,75,100].forEach(v=>{
    const y=ySoc(v); ctx.strokeStyle="#0d1530"; ctx.lineWidth=1;
    ctx.beginPath(); ctx.moveTo(PAD.left,y); ctx.lineTo(PAD.left+pw,y); ctx.stroke();
    ctx.fillStyle="#8a9cc0"; ctx.fillText(v+"%",PAD.left-5,y);
  });
  // power axis: labels belong to the target range and glide into place with the scale
  ctx.textAlign="left"; ctx.fillStyle="#5f7299";
  [-1,-.5,0,.5,1].forEach(k=>{
    const v=k*GR.pCil, y=yPow(v); if(y<PAD.top-2||y>PAD.top+ph+2) return;
    ctx.fillText(Math.round(v)+"W",PAD.left+pw+5,y);
  });
  // time axis: the finer step fades in as room for it appears
  let kx = GR_KROKY.length-1;
  for(let i=0;i<GR_KROKY.length;i++){ if(GR_KROKY[i]*60e3/span*pw >= 62){ kx = i; break; } }
  const hruby = GR_KROKY[kx], jemny = kx > 0 ? GR_KROKY[kx-1] : null;
  const aj = jemny ? _mezi((jemny*60e3/span*pw-40)/22, 0, 1) : 0, krok = aj > 0 ? jemny : hruby;
  const pul = new Date(GR.d0); pul.setHours(0,0,0,0);
  const odPulnoci = Math.ceil((GR.d0-pul.getTime())/(krok*60e3));
  ctx.textAlign="center"; ctx.textBaseline="top";
  for(let j=odPulnoci, n=0; n<60; j++, n++){
    const t = pul.getTime()+j*krok*60e3; if(t > GR.d1) break;
    const x = xOf(t), hl = (j*krok) % hruby === 0;
    if(x < PAD.left+14 || x > PAD.left+pw-14) continue;
    ctx.globalAlpha = hl ? 1 : aj; ctx.fillStyle="#8a9cc0";
    ctx.fillText(_hm(t), x, PAD.top+ph+5);
  }
  ctx.globalAlpha = 1;

  // curves clipped to the plot area (on the first draw they are revealed from the left)
  ctx.save(); ctx.beginPath(); ctx.rect(PAD.left, PAD.top-3, pw*GR.odhal, ph+6); ctx.clip();
  const X = [], S = [], P = [];
  for(let i=i0;i<=i1;i++){ const d=_hData[i]; X.push(xOf(d.ms)); S.push(ySoc(d.soc)); P.push(yPow(d.power)); }
  const n = X.length, y0 = yPow(0);
  if(n > 1){
    const sg=ctx.createLinearGradient(0,PAD.top,0,PAD.top+ph);
    sg.addColorStop(0,"rgba(14,165,233,.2)"); sg.addColorStop(1,"rgba(14,165,233,.02)");
    ctx.fillStyle=sg; ctx.beginPath(); ctx.moveTo(X[0],S[0]);
    for(let i=1;i<n;i++) ctx.lineTo(X[i],S[i]);
    ctx.lineTo(X[n-1],PAD.top+ph); ctx.lineTo(X[0],PAD.top+ph); ctx.closePath(); ctx.fill();
    ctx.strokeStyle="#0ea5e9"; ctx.lineWidth=2; ctx.lineJoin="round";
    ctx.beginPath(); ctx.moveTo(X[0],S[0]);
    for(let i=1;i<n;i++) ctx.lineTo(X[i],S[i]);
    ctx.stroke();
    const pg=ctx.createLinearGradient(0,PAD.top,0,y0);
    pg.addColorStop(0,"rgba(52,211,153,.2)"); pg.addColorStop(1,"rgba(52,211,153,.02)");
    ctx.fillStyle=pg; ctx.beginPath(); ctx.moveTo(X[0],y0);
    for(let i=0;i<n;i++) ctx.lineTo(X[i],Math.min(P[i],y0));
    ctx.lineTo(X[n-1],y0); ctx.closePath(); ctx.fill();
    const po=ctx.createLinearGradient(0,y0,0,PAD.top+ph);
    po.addColorStop(0,"rgba(251,146,60,.02)"); po.addColorStop(1,"rgba(251,146,60,.2)");
    ctx.fillStyle=po; ctx.beginPath(); ctx.moveTo(X[0],y0);
    for(let i=0;i<n;i++) ctx.lineTo(X[i],Math.max(P[i],y0));
    ctx.lineTo(X[n-1],y0); ctx.closePath(); ctx.fill();
    // power line: green while charging, orange while discharging; two paths instead of hundreds
    ctx.lineWidth=2; ctx.lineJoin="round"; ctx.lineCap="round";
    for(const kladna of [true,false]){
      ctx.strokeStyle = kladna ? "#34d399" : "#fb923c"; ctx.beginPath();
      for(let i=1;i<n;i++){
        const d0=_hData[i0+i-1], d1=_hData[i0+i];
        if(((d0.power+d1.power)/2 >= 0) !== kladna) continue;
        ctx.moveTo(X[i-1],P[i-1]); ctx.lineTo(X[i],P[i]);
      }
      ctx.stroke();
    }
  }
  ctx.restore();
  ctx.strokeStyle="#162040"; ctx.lineWidth=1; ctx.strokeRect(PAD.left,PAD.top,pw,ph);

  // marker under the cursor or finger
  let idx = -1;
  if(GR.kx != null && !(GR.tah && GR.tah.typ !== "prejezd") && GR.kx >= PAD.left-4 && GR.kx <= PAD.left+pw+4){
    const t = GR.d0+(GR.kx-PAD.left)/pw*span, j = _grIndex(t);
    idx = j <= 0 ? 0 : j >= _hData.length ? _hData.length-1 : (t-_hData[j-1].ms < _hData[j].ms-t ? j-1 : j);
  }
  if(idx >= 0){
    const d = _hData[idx], x = xOf(d.ms);
    if(x >= PAD.left-1 && x <= PAD.left+pw+1){
      ctx.strokeStyle="rgba(200,213,240,.35)"; ctx.lineWidth=1;
      ctx.beginPath(); ctx.moveTo(x,PAD.top); ctx.lineTo(x,PAD.top+ph); ctx.stroke();
      [[ySoc(d.soc),"#0ea5e9"],[yPow(d.power),d.power>=0?"#34d399":"#fb923c"]].forEach(b=>{
        ctx.fillStyle=b[1]; ctx.strokeStyle="#090d1a"; ctx.lineWidth=2;
        ctx.beginPath(); ctx.arc(x,b[0],4,0,Math.PI*2); ctx.fill(); ctx.stroke();
      });
      _showTip(d, x, W);
    }else if(_tip) _tip.style.display="none";
  }else if(_tip) _tip.style.display="none";
  _rangeLabel();
}
// drawn only on the Overview tab; also called on tab switch and resize
function _drawChart(){ _grKresli(); _grStart(); }

function _initTip(){
  const canvas=document.getElementById("trend-chart");
  if(!canvas||_tip) return;
  _tip=document.createElement("div");
  _tip.style.cssText="position:absolute;pointer-events:none;background:rgba(9,13,26,.96);"
    +"border:1px solid #162040;border-radius:8px;padding:7px 11px;"
    +"font:11px/1.7 'IBM Plex Mono',monospace;color:#c8d5f0;white-space:nowrap;"
    +"display:none;z-index:20;transform:translateX(-50%);max-width:210px";
  canvas.parentElement.appendChild(_tip);
}
function _showTip(d, x, W){
  if(!_tip) return;
  const pw=d.power>=0?`<span style="color:#34d399">+${d.power.toFixed(0)} W</span>`
                     :`<span style="color:#fb923c">${d.power.toFixed(0)} W</span>`;
  const h=`<b>${_hm(d.ms)}</b>  SOC ${d.soc}%<br>${pw}  ${d.voltage.toFixed(2)} V`;
  if(_tip._h !== h){ _tip.innerHTML=h; _tip._h=h; }
  const left=_mezi(x, GR_PAD.left+80, W-GR_PAD.right-80);
  _tip.style.display="block"; _tip.style.left=left+"px"; _tip.style.top="2px";
}

// ---- motion: easing to the target, inertia, return from the edge ----
function _grTik(ted){
  const g = GR, dt = g.cas ? Math.min(64, ted-g.cas) : 16; g.cas = ted;
  let hotovo = true; const s = g.c1-g.c0;
  if(!g.tah){
    if(g.v){                                            // inertia after release
      g.c0 += g.v*dt; g.c1 += g.v*dt;
      const venku = g.c0 < g.f0 || g.c1 > g.f1;
      g.v *= Math.exp(-dt/(venku ? 70 : 320));
      if(Math.abs(g.v) < s/Math.max(g.W,100)*.012) g.v = 0; else hotovo = false;
    }
    const pres = g.c0 < g.f0 ? g.f0-g.c0 : g.c1 > g.f1 ? g.f1-g.c1 : 0;     // return from the edge
    if(pres){
      const krok = Math.abs(pres) < s*.0004 ? pres : pres*(1-Math.exp(-dt/110));
      g.c0 += krok; g.c1 += krok; hotovo = false;
    }
  }
  // dragging past the edge is shown only partly (rubber band)
  const pres2 = g.c0 < g.f0 ? g.f0-g.c0 : g.c1 > g.f1 ? g.f1-g.c1 : 0;
  const t0 = g.c0+pres2*.62, t1 = g.c1+pres2*.62;
  if(g.tah || GR_KLID){ g.d0 = t0; g.d1 = t1; }
  else{
    const k = 1-Math.exp(-dt/g.tau);
    g.d0 += (t0-g.d0)*k; g.d1 += (t1-g.d1)*k;
    if(Math.abs(t0-g.d0)+Math.abs(t1-g.d1) < s*.0006){ g.d0 = t0; g.d1 = t1; g.tau = 90; } else hotovo = false;
  }
  // power scale follows what is visible
  let mx = 50;
  for(let i=Math.max(0,_grIndex(g.d0)-1), e=Math.min(_hData.length-1,_grIndex(g.d1)); i<=e; i++){
    const a = Math.abs(_hData[i].power); if(a > mx) mx = a;
  }
  g.pCil = _grHezky(mx*1.04);
  const kp = GR_KLID ? 1 : 1-Math.exp(-dt/180);
  g.pMax += (g.pCil-g.pMax)*kp;
  if(Math.abs(g.pCil-g.pMax) < g.pCil*.003) g.pMax = g.pCil; else hotovo = false;
  if(g.odhal < 1){ g.odhal = GR_KLID ? 1 : Math.min(1, g.odhal+dt/800); hotovo = false; }
  if(curTab === "overview") _grKresli();
  if(g.tah) hotovo = false;
  g.raf = hotovo ? 0 : requestAnimationFrame(_grTik);
  if(hotovo) g.cas = 0;
}
function _grStart(){ if(GR.hotovo && !GR.raf){ GR.cas = 0; GR.raf = requestAnimationFrame(_grTik); } }
function _grOkno(c0, c1, tau){                  // glide to a window, kept inside the data
  const plny = GR.f1-GR.f0, s = _mezi(c1-c0, Math.min(GR_MIN, plny), plny), stred = (c0+c1)/2;
  c0 = _mezi(stred-s/2, GR.f0, GR.f1-s);
  GR.c0 = c0; GR.c1 = c0+s; GR.v = 0; if(tau) GR.tau = tau;
  _grStart();
}
function _grZoom(tKotva, nasob, tau){           // zoom around the time tKotva
  const plny = GR.f1-GR.f0, s0 = GR.c1-GR.c0, s = _mezi(s0*nasob, Math.min(GR_MIN, plny), plny), f = (tKotva-GR.c0)/s0;
  const c0 = _mezi(tKotva-f*s, GR.f0, GR.f1-s);
  GR.c0 = c0; GR.c1 = c0+s; GR.v = 0; if(tau) GR.tau = tau;
  _grStart();
}
// new data: if you look at everything or at the end, the window moves with time
function _grData(){
  const prvni = !GR.hotovo, f0 = _hData[0].ms, f1 = _hData[_hData.length-1].ms;
  if(prvni){
    GR.f0 = f0; GR.f1 = f1; GR.c0 = GR.d0 = f0; GR.c1 = GR.d1 = f1;
    GR.hotovo = true; GR.odhal = (GR_KLID || document.hidden) ? 1 : 0;
    let mx = 50; _hData.forEach(d => { const a = Math.abs(d.power); if(a > mx) mx = a; });
    GR.pMax = GR.pCil = _grHezky(mx*1.04);
  }else{
    const s = GR.c1-GR.c0, plne = !_grPriblizeno(), naKonci = GR.f1-GR.c1 < 90e3;
    GR.f0 = f0; GR.f1 = f1;
    if(!GR.tah){
      if(plne){ GR.c0 = f0; GR.c1 = f1; }
      else if(naKonci){ GR.c1 = f1; GR.c0 = f1-s; }
      else if(GR.c0 < f0){ GR.c0 = f0; GR.c1 = Math.min(f1, f0+s); }
    }
  }
}

function _initInteract(){
  const canvas=document.getElementById("trend-chart");
  if(!canvas||canvas._inited) return;
  canvas._inited=true;
  const g = GR; let kolNaposled = 0, kolNase = false, klep = {cas:0, x:0};
  const xy = e => e.clientX-canvas.getBoundingClientRect().left;
  const pw = () => Math.max(50, g.W-GR_PAD.left-GR_PAD.right);
  const casNa = x => g.d0+(x-GR_PAD.left)/pw()*(g.d1-g.d0);
  const casCil = x => g.c0+(x-GR_PAD.left)/pw()*(g.c1-g.c0);      // in the target window: wheel steps add up without drifting
  const prepni = x => { if(_grPriblizeno()) _grOkno(g.f0, g.f1, 150); else _grZoom(casCil(x), .25, 150); };

  // the wheel zooms only when the gesture started over the chart, so the chart does not steal page scrolling
  window.addEventListener("wheel", e => {
    const ted = performance.now();
    if(ted-kolNaposled > 300) kolNase = canvas.contains(e.target);
    kolNaposled = ted;
  }, {capture:true, passive:true});
  canvas.addEventListener("wheel", e => {
    if(!g.hotovo || !kolNase) return;
    const jed = e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? 120 : 1, dx = e.deltaX*jed, dy = e.deltaY*jed;
    if(Math.abs(dx) > Math.abs(dy) || e.shiftKey){              // horizontal wheel or Shift = pan
      if(!_grPriblizeno()) return;
      e.preventDefault();
      const posun = (Math.abs(dx) > Math.abs(dy) ? dx : dy)/pw()*(g.c1-g.c0);
      _grOkno(g.c0+posun, g.c1+posun, 90);
      return;
    }
    if(dy > 0 && !_grPriblizeno()) return;                      // everything is visible already: let the page scroll
    e.preventDefault();
    _grZoom(casCil(xy(e)), Math.exp(dy*(e.ctrlKey ? .01 : .0016)), 90);
  }, {passive:false});

  canvas.addEventListener("pointerdown", e => {
    if(!g.hotovo || (e.pointerType === "mouse" && e.button !== 0)) return;
    const x = xy(e); g.prsty[e.pointerId] = x;
    try{ canvas.setPointerCapture(e.pointerId); }catch(err){}
    const ids = Object.keys(g.prsty);
    g.v = 0;
    // a direct drag continues from what is on screen right now (even mid-ease)
    if(ids.length === 2 || e.pointerType !== "touch" || _grPriblizeno()){ g.c0 = g.d0; g.c1 = g.d1; }
    if(ids.length === 2){
      const a = g.prsty[ids[0]], b = g.prsty[ids[1]];
      g.tah = {typ:"stisk", d0:Math.max(20, Math.abs(a-b)), s0:g.c1-g.c0, kotva:casNa((a+b)/2)};
      g.kx = null;
    }else if(e.pointerType !== "touch" || _grPriblizeno()){
      g.tah = {typ:"posun", id:e.pointerId, x0:x, c0:g.c0, c1:g.c1, stopa:[[performance.now(), x]], hnul:false, kdy:performance.now()};
      canvas.classList.add("tahne");
    }else{
      g.tah = {typ:"prejezd", id:e.pointerId, x0:x, hnul:false, kdy:performance.now()};
      g.kx = x;
    }
    _grStart();
  });
  canvas.addEventListener("pointermove", e => {
    if(!g.hotovo) return;
    const x = xy(e), t = g.tah;
    if(e.pointerId in g.prsty) g.prsty[e.pointerId] = x;
    if(!t){ if(e.pointerType === "mouse"){ g.kx = x; _grStart(); } return; }
    if(t.typ === "stisk"){
      const ids = Object.keys(g.prsty); if(ids.length < 2) return;
      const a = g.prsty[ids[0]], b = g.prsty[ids[1]], plny = g.f1-g.f0;
      const s = _mezi(t.s0*t.d0/Math.max(20, Math.abs(a-b)), Math.min(GR_MIN, plny), plny);
      g.c0 = t.kotva-((a+b)/2-GR_PAD.left)/pw()*s; g.c1 = g.c0+s;
    }else if(t.typ === "posun" && e.pointerId === t.id){
      const dx = x-t.x0; if(Math.abs(dx) > 4) t.hnul = true;
      const dt = -dx/pw()*(t.c1-t.c0);
      g.c0 = t.c0+dt; g.c1 = t.c1+dt;
      t.stopa.push([performance.now(), x]); if(t.stopa.length > 8) t.stopa.shift();
    }else if(t.typ === "prejezd" && e.pointerId === t.id){
      if(Math.abs(x-t.x0) > 4) t.hnul = true;
      g.kx = x;
    }
    _grStart();
  });
  const pust = e => {
    const t = g.tah, x = g.prsty[e.pointerId];
    delete g.prsty[e.pointerId];
    try{ canvas.releasePointerCapture(e.pointerId); }catch(err){}
    if(!t) return;
    const ted = performance.now(), zbyva = Object.keys(g.prsty);
    if(t.typ === "stisk"){                                      // one finger stayed down: continue as a pan
      if(zbyva.length === 1){ const z = g.prsty[zbyva[0]]; g.tah = {typ:"posun", id:+zbyva[0], x0:z, c0:g.c0, c1:g.c1, stopa:[[ted, z]], hnul:true, kdy:ted}; }
      else g.tah = null;
      _grStart(); return;
    }
    if(e.pointerId !== t.id) return;
    g.tah = null; canvas.classList.remove("tahne");
    if(t.typ === "posun" && t.hnul && e.type !== "pointercancel"){
      const st = t.stopa.filter(q => ted-q[0] < 110);
      if(st.length > 1){
        const vpx = (st[st.length-1][1]-st[0][1])/Math.max(1, st[st.length-1][0]-st[0][0]);
        if(Math.abs(vpx) > .05) g.v = -vpx/pw()*(g.c1-g.c0);
      }
    }
    const klepnuti = !t.hnul && ted-t.kdy < 320 && e.type !== "pointercancel";
    const schovej = () => setTimeout(() => { if(!g.tah){ g.kx = null; _grStart(); } }, 2600);
    if(e.pointerType === "touch"){
      if(klepnuti){
        if(ted-klep.cas < 340 && x != null && Math.abs(x-klep.x) < 34){ prepni(x); klep.cas = 0; g.kx = null; }
        else{ klep = {cas:ted, x:x == null ? 0 : x}; g.kx = x == null ? null : x; schovej(); }
      }else if(t.typ === "prejezd") schovej();
      else g.kx = null;
    }else if(x != null) g.kx = x;
    _grStart();
  };
  canvas.addEventListener("pointerup", pust);
  canvas.addEventListener("pointercancel", pust);
  canvas.addEventListener("pointerleave", e => { if(e.pointerType === "mouse" && !g.tah){ g.kx = null; _grStart(); } });
  canvas.addEventListener("dblclick", e => { if(g.hotovo){ e.preventDefault(); prepni(xy(e)); } });
}

// History is fetched INCREMENTALLY. Fetching all ~1440 samples (~120 kB)
// every minute would be about 170 MB a day for one open tab,
// which is noticeable on mobile data.
const HIST_MAX = 1440;
let _lastT = "";
async function loadHistory(){
  try{
    const url = _lastT ? "/api/history?since=" + encodeURIComponent(_lastT) : "/api/history";
    const r = await fetch(url); if(!r.ok) return;
    const d = await r.json();
    const items = d.items || [];
    items.forEach(x => { x.ms = new Date(x.t).getTime(); });     // sample time in ms for the chart axis
    if(d.full) _hData = items;
    else if(items.length) _hData = _hData.concat(items);
    else return;                                    // nothing new, do not redraw
    if(_hData.length > HIST_MAX) _hData = _hData.slice(-HIST_MAX);
    if(_hData.length < 2) return;
    _lastT = _hData[_hData.length-1].t;
    // If the user zoomed in, their window stays; otherwise it moves with time.
    _grData();
    _initTip(); _initInteract();
    if(curTab === "overview") _drawChart();
  }catch(e){ console.error(e); }
}
