/* 锂电池台 live 层：粒子、指针、风扇、SOC 条、旋钮、巡游与交互。全部读数来自 model.mjs 的同一状态。 */
const D = __DATA__;
const P = D.P;
const NS = "http://www.w3.org/2000/svg";
const TIME_SCALE = 120; // 真实 1 s = 电池 120 s

const stage = document.querySelector(".iso-stage");
const svg = stage.querySelector("svg");
const $ = (sel) => svg.querySelector(sel);
const $$ = (sel) => [...svg.querySelectorAll(sel)];
const readout = document.querySelector("[data-readout]");
const statusEl = document.querySelector("[data-status]");
const reduced = matchMedia("(prefers-reduced-motion: reduce)");
const isoAt = (p) => iso(p, P);

// ---------- 状态 ----------
const st = makeState();
let angle = 0;        // 风扇角速度积分
let fanW = 0;
let voltShown = ocv(st.soc);
let ampShown = 0;
let knobShown = 0.15; // 旋钮指针角（世界 xy 角，π 单位）
let hold = 0;
let statusT = 0;

const PHASE_CN = { CC: "恒流充电", CV: "恒压充电", FULL: "充满", "1C": "放电 1C", IDLE: "电量耗尽" };

function setMode(m) {
  if (st.mode === m) return;
  st.mode = m;
  st.full = false;
  st.empty = false;
  st.i = 0;
  st.phase = m === "charge" ? "CC" : "1C";
  hold = 0;
}

// ---------- 元素构建 ----------
const elIons = $('[data-part="ions"]');
const elIons2 = $('[data-part="ions2"]');
const elElec = $('[data-part="electrons"]');
const elFan = $('[data-part="fan"]');
const elNeedles = $('[data-part="needles"]');
const elKnobMark = $('[data-part="knob-mark"]');
const elLeds = $('[data-part="leds"]');

function dot(parent, r) {
  const c = document.createElementNS(NS, "circle");
  c.setAttribute("r", String(r));
  c.style.fill = "var(--anatomy-lit)";
  c.setAttribute("opacity", "0");
  parent.appendChild(c);
  return c;
}

// 离子：两个间隙 × n 个
const ions = [];
D.ions.gaps.forEach((g, gi) => {
  for (let j = 0; j < D.ions.n; j++) {
    ions.push({
      el: dot(elIons, 1.25),
      g,
      u: (j + gi * 0.37) / D.ions.n,
      y: D.ions.y[0], // 全部坐在剖面平面之前，沿 +y 看进来正好落在通道里
      z: D.ions.z[0] + ((j * 17 + gi * 5) % 5) * 14,
    });
  }
});

// 试样离子：堆叠轴是 y，所以它们沿 y 往返（屏面 1.53 px/单位，而不是 1.03）。
// 这一条通道里只有一个正极在后方，所以充电时六个离子全沿 a→b（同一条通道里不会反向）
const SAMPLE = D.ions.sample;
const sampleIons = SAMPLE.lanes.map(([x, z], i) => ({
  el: dot(elIons2, SAMPLE.r),
  g: { a: SAMPLE.a, b: SAMPLE.b, from: "a" },
  axis: "y",
  x,
  z,
  u: (i * 0.37) % 1,
}));

// 电子：每条电缆沿屏幕折线均布
const DIRS = { "hv.plus": 1, "hv.minus": -1, "drive.a": 1, "drive.b": -1 };
const cables = Object.entries(D.cables).map(([name, pts]) => {
  const seg = [];
  let total = 0;
  for (let i = 1; i < pts.length; i++) {
    const L = Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]);
    seg.push(L);
    total += L;
  }
  // 粒子只是电缆上的一点闪光：疏、小，不能把管线遮成一串珍珠
  const n = Math.max(4, Math.round(total / 26));
  const dotsList = Array.from({ length: n }, () => dot(elElec, 0.85));
  return { name, pts, seg, total, spacing: total / n, dots: dotsList, offs: dotsList.map((_, k) => (k * total) / n) };
});

// 风扇：5 叶 + 毂（每帧重建 d）
const blades = Array.from({ length: D.fan.n }, () => {
  const p = document.createElementNS(NS, "path");
  p.style.fill = "var(--anatomy-hi)";
  p.style.stroke = "var(--anatomy-lo)";
  p.style.strokeWidth = "0.6px";
  elFan.appendChild(p);
  return p;
});
const hub = dot(elFan, 2.2);
hub.style.fill = "var(--anatomy-mid)";

// 指针：两条线（尾 + 身）；针尖默认停在盘面上，所以标 free:"end"
function needle(parent) {
  const g = document.createElementNS(NS, "path");
  g.setAttribute("class", "iso-line");
  g.setAttribute("data-tone", "hi");
  g.setAttribute("data-free", "end");
  parent.appendChild(g);
  return g;
}
const ndV = needle(elNeedles);
const ndA = needle(elNeedles);
for (const [g, name] of [[ndV, "volt"], [ndA, "amp"]]) {
  const o = D.gauges[name].o;
  const c = isoAt(o);
  g.setAttribute("transform-origin", `${c[0]} ${c[1]}`);
}

// 旋钮指针（尖端停在旋钮顶面）
const knp = document.createElementNS(NS, "path");
knp.setAttribute("class", "iso-line");
knp.setAttribute("data-tone", "hi");
knp.setAttribute("data-free", "end");
elKnobMark.appendChild(knp);

// PBD 状态灯
const leds = D.leds.map((p) => {
  const c = dot(elLeds, 1.9);
  const [x, y] = isoAt(p);
  c.setAttribute("cx", String(x));
  c.setAttribute("cy", String(y));
  return c;
});

const socCells = $$("[data-soc]");

// ---------- 每帧 ----------
function bladePath(th) {
  const F = D.fan;
  const skew = 0.34;
  const w = (2 * Math.PI) / F.n;
  const pt = (r, a, y) => isoAt([F.cx + r * Math.cos(a), y, F.cz + r * Math.sin(a)]);
  const q = (a0) => {
    const p1 = pt(F.r0, a0, F.y0), p2 = pt(F.r1, a0 + skew, F.y0), p3 = pt(F.r1, a0 + skew, F.y1), p4 = pt(F.r0, a0, F.y1);
    return `M${p1[0]} ${p1[1]}L${p2[0]} ${p2[1]}L${p3[0]
      } ${p3[1]}L${p4[0]} ${p4[1]}Z`;
  };
  return q(th);
}

function needlePath(spec, cur) {
  const frac = Math.min(1.06, Math.max(-0.06, (cur - spec.min) / (spec.max - spec.min)));
  const beta = (frac * 1.5 - 0.75) * Math.PI;
  const dir = [Math.cos(beta), Math.sin(beta)];
  const tip = isoAt([spec.o[0] + spec.r * dir[0], spec.o[1] + spec.r * dir[1], spec.o[2]]);
  const tail = isoAt([spec.o[0] - spec.r * 0.22 * dir[0], spec.o[1] - spec.r * 0.22 * dir[1], spec.o[2]]);
  const piv = isoAt(spec.o);
  return `M${tail[0]} ${tail[1]}L${piv[0]} ${piv[1]}M${piv[0]} ${piv[1]}L${tip[0]} ${tip[1]}`;
}

const clamp = (v, a, b) => Math.min(b, Math.max(a, v));

function render(dt) {
  const act = Math.min(1, Math.abs(st.i) / 14); // 电流活动包络
  // 离子（剖口电芯 + 试样）
  for (const io of ions.concat(sampleIons)) {
    io.u += Math.abs(st.i) * 0.007 * dt;
    io.u -= Math.floor(io.u);
    const charge = st.mode === "charge";
    const start = charge ? (io.g.from === "a" ? io.g.a : io.g.b) : (io.g.from === "a" ? io.g.b : io.g.a);
    const end = charge ? (io.g.from === "a" ? io.g.b : io.g.a) : (io.g.from === "a" ? io.g.a : io.g.b);
    const edge = Math.min(1, Math.min(io.u, 1 - io.u) * 6); // 进出极板面渐隐
    const v = start + (end - start) * io.u;
    const [x, y] = isoAt(io.axis === "y" ? [io.x, v, io.z] : [v, io.y, io.z]);
    io.el.setAttribute("cx", String(x));
    io.el.setAttribute("cy", String(y));
    io.el.setAttribute("opacity", (act * edge).toFixed(2));
  }
  // 电子
  const pxSpeed = Math.abs(st.i) * 0.9;
  for (const cb of cables) {
    const on = (cb.name.startsWith("hv") ? st.mode === "charge" : st.mode === "discharge") ? act : 0;
    for (let k = 0; k < cb.dots.length; k++) {
      cb.offs[k] = (cb.offs[k] + DIRS[cb.name] * pxSpeed * dt + cb.total) % cb.total;
      let s = cb.offs[k], i = 0;
      while (s > cb.seg[i] && i < cb.seg.length - 1) { s -= cb.seg[i]; i++; }
      const a = cb.pts[i], b = cb.pts[i + 1], f = cb.seg[i] ? s / cb.seg[i] : 0;
      cb.dots[k].setAttribute("cx", String(a[0] + (b[0] - a[0]) * f));
      cb.dots[k].setAttribute("cy", String(a[1] + (b[1] - a[1]) * f));
      cb.dots[k].setAttribute("opacity", on.toFixed(2));
    }
  }
  // 风扇（放电时转动，含惯性）
  const wt = st.mode === "discharge" ? Math.abs(st.i) * 0.032 : 0;
  fanW += (wt - fanW) * (1 - Math.exp(-dt / 0.8));
  angle += fanW * dt;
  blades.forEach((p, k) => p.setAttribute("d", bladePath(angle + (k * 2 * Math.PI) / D.fan.n)));
  const hc = isoAt([D.fan.cx, D.fan.y1, D.fan.cz]);
  hub.setAttribute("cx", String(hc[0]));
  hub.setAttribute("cy", String(hc[1]));
  hub.setAttribute("opacity", (0.5 + 0.5 * Math.min(1, fanW / 2)).toFixed(2));
  // 指针（跟随）
  const fv = 1 - Math.exp(-6 * dt);
  voltShown += (cellVoltage(st) - voltShown) * fv;
  ampShown += (st.i - ampShown) * fv;
  ndV.setAttribute("d", needlePath(D.gauges.volt, voltShown));
  ndA.setAttribute("d", needlePath(D.gauges.amp, ampShown));
  // 旋钮
  const kt = st.mode === "charge" ? 0.15 : -0.55;
  knobShown += (kt - knobShown) * (1 - Math.exp(-8 * dt));
  {
    const o = D.knob.o, b = knobShown * Math.PI;
    const c = isoAt(o);
    const t = isoAt([o[0] + D.knob.r * Math.cos(b), o[1] + D.knob.r * Math.sin(b), o[2]]);
    knp.setAttribute("d", `M${c[0]} ${c[1]}L${t[0]} ${t[1]}`);
  }
  // LED 脉动
  {
    const pulse = 0.35 + 0.65 * (0.5 + 0.5 * Math.sin(performance.now() / 240));
    leds.forEach((l) => l.setAttribute("opacity", (act * pulse).toFixed(2)));
  }
  // SOC 条
  const lit = Math.round(st.soc * socCells.length);
  socCells.forEach((el, i) => el.classList.toggle("on", i < lit));
  // 读数
  readout.textContent = `${PHASE_CN[st.phase]} · ${Math.round(st.soc * 100)}% · ${(cellVoltage(st) * D.cells).toFixed(1)}V · ${st.i >= 0 ? "+" : ""}${st.i.toFixed(0)}A`;
}

// ---------- 巡游：充满→放完→再充，自动循环 ----------
function tick(dtReal) {
  const dt = dtReal * TIME_SCALE;
  step(st, dt);
  if (st.full || st.empty) {
    hold += dtReal;
    if (hold > 2.5) { setMode(st.mode === "charge" ? "discharge" : "charge"); }
  }
  render(dtReal);
  statusT += dtReal;
  if (statusT > 4) { statusT = 0; statusEl.textContent = readout.textContent; }
}

let raf = 0, last = 0, visible = true;
function loop(now) {
  raf = requestAnimationFrame(loop);
  const dt = Math.min(0.05, (now - last) / 1000 || 0.016);
  last = now;
  if (!document.hidden && visible) tick(dt);
}

// ---------- 交互 ----------
stage.addEventListener("click", () => setMode(st.mode === "charge" ? "discharge" : "charge"));
stage.addEventListener("keydown", (e) => {
  if (e.key === " " || e.key === "Enter") { e.preventDefault(); setMode(st.mode === "charge" ? "discharge" : "charge"); }
  else if (e.key === "ArrowLeft") setMode("charge");
  else if (e.key === "ArrowRight") setMode("discharge");
});

new IntersectionObserver((es) => { visible = es[0].isIntersecting; }, { threshold: 0.05 }).observe(stage);

if (reduced.matches) {
  // 一帧静息画面：46% 恒流充电
  st.soc = 0.46; st.phase = "CC"; st.i = CELL.c_charge * CELL.ah;
  voltShown = cellVoltage(st); ampShown = st.i;
  render(0.016);
  for (const cb of cables) for (const d of cb.dots) d.setAttribute("opacity", "0");
} else {
  raf = requestAnimationFrame(loop);
}
