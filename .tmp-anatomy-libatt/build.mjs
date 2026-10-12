// Anatomy figure: EV lithium-ion cell — how it charges and discharges.
// Standalone SVG + live model. Build: `node build.mjs [--light]`.
import { writeFileSync } from "node:fs";
import * as k from "file:///C:/Users/joezxh/.qoder/skills/anatomy/kit/iso-kit.mjs";
import { kitScript } from "file:///C:/Users/joezxh/.qoder/skills/anatomy/scripts/inline-kit.mjs";

const theme = process.argv.includes("--light") ? "light" : "dark";
const WIDTH = 690;
const HEIGHT = 470;

// ---- world layout -------------------------------------------------------
const PLATE = { x: -172, y: -86, w: 344, d: 172, r: 12 };
const PLATE_H = 12, FOOT_H = 5;

const CAT_COL = { x: -100, y: -28, w: 6, d: 56, r: 1 };
const CAT_BLK = { x: -94, y: -28, w: 34, d: 56, r: 2 };
const AN_COL = { x: 94, y: -28, w: 6, d: 56, r: 1 };
const GRAPHITE = { x: 60, y: -28, w: 34, d: 56, r: 1 };
const GRAPH_Z = [12, 20, 28, 36, 44, 52];
const CHAN = { x: -58, y: -28, w: 116, d: 56, r: 2 };
const SEP_X = 0;

const BUS_Z = 98, BUS_TOP = 102;
const RISER = { y: -3, w: 6, d: 6 };
const CHG = { x: -62, y: -10, w: 24, d: 20, r: 2 };
const MOT = { x: 38, y: -10, w: 26, d: 20, r: 2 };
const MOTOR = { cx: 51, cy: -11, cz: 109, r: 7 };
const CHG_C = [-50, 0, BUS_TOP + 14];

const DIAL = [0, 58], DIAL_R = 14, DIAL_Z = 24;
const ION_Z = 30, ELEC_Z = 100;

const P = k.fitProjection(
  [
    ...k.boxCorners(PLATE, -PLATE_H - FOOT_H, 0),
    [-102, -28, 66], [100, 28, 66],
    [-102, -4, BUS_TOP], [100, 4, BUS_TOP],
    [CHG.x, -10, BUS_TOP + 16], [MOT.x + MOT.w, 10, BUS_TOP + 16],
    [DIAL[0] - DIAL_R, DIAL[1] + DIAL_R, DIAL_Z], [DIAL[0] + DIAL_R, DIAL[1] - DIAL_R, DIAL_Z],
    [SEP_X, 0, 60],
  ],
  WIDTH, HEIGHT, { pad: 26, azimuth: 42 },
);

const at = (pt) => k.iso(pt, P);
const S = (paths, style) => k.solidSvg(paths, style);
const L = (d, style) => k.lineSvg(d, style);
const D = (points, style) => k.dotsSvg(points, style);
const byDepth = (pts) => [...pts].sort((a, b) => k.depthOf([a[0], a[1], 0], P) - k.depthOf([b[0], b[1], 0], P));
const plate = (plan, z, h, tone, bevel = 0.6, steps = 6) => S(k.slabOf(plan, z, h, P, steps, bevel), { tone, crease: "lo" });

// ---- base ---------------------------------------------------------------
function base() {
  const out = [`<path class="iso-halo" d="${k.haloOf(PLATE, -PLATE_H - FOOT_H, PLATE_H, P)}"/>`];
  for (const [x, y] of byDepth(k.corners(PLATE, 26))) {
    out.push(S(k.cylinder(x, y, 8, -PLATE_H - FOOT_H, 1.6, P, 28), { tone: "lo" }));
    out.push(S(k.cylinder(x, y, 6, -PLATE_H - FOOT_H + 1.6, FOOT_H - 1.6, P, 28), { tone: "mid" }));
  }
  out.push(S(k.slabOf(PLATE, -PLATE_H, PLATE_H, P, 10, 1.6), { tone: "mid" }));
  out.push(L(k.planOutline(k.insetPlan(PLATE, 6), 0, P), { tone: "lo" }));
  const screws = k.corners(PLATE, 12);
  out.push(L(screws.map(([x, y]) => k.ring(x, y, 2.4, 0, P, 16)).join(""), { tone: "lo" }));
  out.push(D(screws.map(([x, y]) => at([x, y, 0])), { size: 0.5 }));
  const strip = { x: -150, y: PLATE.y + PLATE.d - 16, w: 300, d: 8, r: 1.4 };
  out.push(S(k.slabOf(strip, 0, 0.7, P, 3), { tone: "lo", crease: "none" }));
  const t = k.topTicks(strip.x + 6, strip.x + strip.w - 6, 5, 5, strip.y + 1, 0.7, [2.2, 4], P);
  out.push(L(t.minor, { tone: "lo" }), L(t.major, { tone: "mid" }));
  const label = { x: -52, y: PLATE.y + PLATE.d - 34, w: 104, d: 12, r: 1.4 };
  out.push(S(k.slabOf(label, 0, 1, P, 3, 0.4), { tone: "lo", crease: "faint" }));
  out.push(k.faceTextSvg(k.topMatrix([0, label.y + 6], 1, P, "x"), "LI-ION CELL", { size: 4, tone: "mid", anchor: "middle" }));
  return out.join("");
}

// ---- cathode (LiCoO2) ---------------------------------------------------
function cathode() {
  const out = [plate(CAT_COL, 0, 66, "mid", 0.4, 3), plate(CAT_BLK, 8, 52, "hi", 0.8, 5)];
  for (const z of [18, 30, 42, 54]) out.push(L(k.sideSeam(CAT_BLK, z, P, 5), { tone: "faint" }));
  out.push(k.faceTextSvg(k.topMatrix([CAT_BLK.x + 16, -18], 60, P, "x"), "LiCoO2", { size: 3.4, tone: "mid", anchor: "middle" }));
  out.push(`<g data-part="catIons">${D([], {})}</g>`);
  return out.join("");
}

// ---- anode (graphite stack) + SOC ruler ---------------------------------
function anode() {
  const out = [plate(AN_COL, 0, 66, "mid", 0.4, 3)];
  for (const z of GRAPH_Z) out.push(plate(GRAPHITE, z, 4, "hi", 0.4, 3));
  out.push(k.faceTextSvg(k.topMatrix([GRAPHITE.x + 16, -18], GRAPH_Z[GRAPH_Z.length - 1] + 4, P, "x"), "GRAPHITE", { size: 3.2, tone: "mid", anchor: "middle" }));
  out.push(`<g data-part="anIons">${D([], {})}</g>`);
  return out.join("");
}

// ---- electrolyte channel + separator ------------------------------------
function channel() {
  const out = [S(k.slabOf(CHAN, 0, 1.5, P, 4), { tone: "lo", crease: "none", flat: true })];
  for (const y of [-30, 27]) out.push(plate({ x: -58, y, w: 116, d: 3, r: 1 }, 0, 9, "mid", 0.3, 3));
  // separator: perforations where Li+ crosses (the sheet itself is implied by the holes)
  const holes = [];
  for (let z = 8; z <= 54; z += 6) for (const y of [-20, -8, 4, 16]) holes.push(at([0, y, z]));
  out.push(D(holes, { size: 0.5, tone: "lo" }));
  out.push(`<g data-part="ions">${D([], {})}</g>`);
  return out.join("");
}

// ---- risers, bus, charger, switch, motor --------------------------------
function circuit() {
  const out = [];
  for (const x of [-97, 97]) out.push(plate({ x, y: RISER.y, w: RISER.w, d: RISER.d, r: 1 }, 66, BUS_Z - 66, "mid", 0.3, 3));
  out.push(plate({ x: -100, y: -4, w: 200, d: 8, r: 2 }, BUS_Z, BUS_TOP - BUS_Z, "mid", 0.5, 4));
  out.push(L(k.lineOnTop([-96, -4], [96, -4], BUS_TOP, P), { tone: "faint" }));
  out.push(D([at([-96, 0, BUS_TOP]), at([96, 0, BUS_TOP])], { size: 0.5 }));
  // electrons ride the bus
  out.push(`<g data-part="electrons">${D([], {})}</g>`);
  // charger
  out.push(plate(CHG, BUS_TOP, 14, "mid", 0.6, 4));
  out.push(S(k.cylinder(CHG_C[0], CHG_C[1], 5, BUS_TOP + 14, 3, P, 24, 0.4), { tone: "hi", crease: "lo" }));
  out.push(L(k.ring(CHG_C[0], CHG_C[1], 5, BUS_TOP + 17, P, 24), { tone: "lo" }));
  out.push(D([at([CHG_C[0], CHG_C[1], BUS_TOP + 17])], { size: 0.6, tone: "hi" }));
  out.push(`<path data-part="crank" class="iso-line" data-tone="lit" d="${crankPath(0)}"/>`);
  out.push(k.faceTextSvg(k.topMatrix([CHG.x + 12, 8], BUS_TOP + 14, P, "x"), "CHARGER", { size: 2.8, tone: "mid", anchor: "middle" }));
  // switch post + lever
  out.push(S(k.cylinder(0, 0, 3.4, BUS_TOP, 8, P, 20), { tone: "mid" }));
  out.push(`<path data-part="lever" class="iso-line" data-tone="lit" d="${leverPath("idle")}"/>`);
  // motor / load
  out.push(plate(MOT, BUS_TOP, 14, "mid", 0.6, 4));
  out.push(`<g data-part="wheel">${wheelPath(0)}</g>`);
  out.push(k.faceTextSvg(k.topMatrix([MOT.x + 13, 8], BUS_TOP + 14, P, "x"), "LOAD", { size: 2.8, tone: "mid", anchor: "middle" }));
  return out.join("");
}

// ---- voltage dial (front, top face) -------------------------------------
function dial() {
  const out = [];
  out.push(S(k.cylinder(DIAL[0], DIAL[1], 11, 0, DIAL_Z, P, 32, 0.5), { tone: "mid" }));
  out.push(L(k.sideArc(DIAL[0], DIAL[1], 11, 12, P, 16), { tone: "faint" }));
  out.push(S(k.cylinder(DIAL[0], DIAL[1], DIAL_R, DIAL_Z, 4, P, 56, 0.6), { tone: "hi", crease: "lo" }));
  out.push(L(k.ring(DIAL[0], DIAL[1], DIAL_R - 2.4, DIAL_Z + 4, P, 48), { tone: "lo" }));
  const ticks = k.radialTicks(DIAL[0], DIAL[1], DIAL_R - 3.2, 24, 4, DIAL_Z + 4, [1.4, 3], P, Math.PI * 0.75, Math.PI * 1.5);
  out.push(L(ticks.minor, { tone: "lo" }), L(ticks.major, { tone: "mid" }));
  out.push(k.faceTextSvg(k.topMatrix([DIAL[0], DIAL[1] + 8], DIAL_Z + 4, P, "x"), "VOLTS", { size: 2.8, tone: "mid", anchor: "middle" }));
  out.push(`<path data-part="needle" class="iso-line" data-tone="lit" data-free="start" d="${needlePath(3.7)}" style="stroke-width:1.1"/>`);
  out.push(D([at([DIAL[0], DIAL[1], DIAL_Z + 4])], { size: 0.7, tone: "hi" }));
  return out.join("");
}

// ---- dynamic path builders (shared with live via toString) --------------
function needlePath(v) {
  const t = Math.max(0, Math.min(1, (v - 3.0) / 1.2));
  const a = Math.PI * 0.75 + t * Math.PI * 1.5;
  const cx = DIAL[0], cy = DIAL[1];
  return k.lineOnTop([cx - Math.cos(a) * 3, cy - Math.sin(a) * 3], [cx + Math.cos(a) * (DIAL_R - 3), cy + Math.sin(a) * (DIAL_R - 3)], DIAL_Z + 4.2, P);
}
function crankPath(angle) {
  const [cx, cy, cz] = CHG_C;
  return k.lineOnTop([cx, cy], [cx + Math.cos(angle) * 5, cy + Math.sin(angle) * 5], cz + 3, P);
}
function leverPath(mode) {
  const a = mode === "charge" ? Math.PI : mode === "discharge" ? 0 : Math.PI / 2;
  return k.lineOnTop([0, 0], [Math.cos(a) * 9, Math.sin(a) * 9], BUS_TOP + 8, P);
}
function wheelPath(angle) {
  const { cx, cy, cz, r } = MOTOR;
  const pt = (a, rr) => at([cx + Math.cos(a) * rr, cy, cz + Math.sin(a) * rr]);
  let d = "";
  for (let i = 0; i < 5; i++) { const a = angle + (i / 5) * Math.PI * 2; const p = pt(a, r); d += `M${pt(0, 0).join(" ")}L${p.join(" ")}`; }
  const rim = [];
  for (let i = 0; i <= 20; i++) rim.push(pt(angle + (i / 20) * Math.PI * 2, r));
  return `<path class="iso-line" data-tone="hi" d="${d}"/>` + `<path class="iso-line" data-tone="lo" d="M${rim.map((p) => p.join(" ")).join("L")}Z" fill="none"/>`;
}

// ---- assemble -----------------------------------------------------------
function render() {
  return k.figureSvg({
    width: WIDTH, height: HEIGHT,
    label:
      "A lithium-ion cell as a bench instrument. A LiCoO2 cathode block and a graphite anode stack stand on a base, separated by an electrolyte channel with a perforated separator. A top bus carries the external circuit through a charger and a load motor, picked by a switch. Lit lithium ions stream across the channel and lit electrons stream along the bus; a voltage dial and an anode state-of-charge ruler read the same model. Charging drives ions and electrons one way and fills the anode; discharging reverses them and spins the motor.",
    body: [
      base(),
      cathode(),
      anode(),
      channel(),
      circuit(),
      dial(),
    ],
  });
}

const svg = render();

// ---- live model ---------------------------------------------------------
const live = `
const P = ${JSON.stringify(P)};
const DIAL = ${JSON.stringify(DIAL)}, DIAL_R = ${DIAL_R}, DIAL_Z = ${DIAL_Z};
const CHG_C = ${JSON.stringify(CHG_C)};
const MOTOR = ${JSON.stringify(MOTOR)};
const GRAPH_Z = ${JSON.stringify(GRAPH_Z)};
const ION_Z = ${ION_Z}, ELEC_Z = ${ELEC_Z};
const V_MIN = 3.0, V_MAX = 4.2;
const stage = document.querySelector(".iso-stage");
const svg = stage.querySelector("svg");
const q = (n) => svg.querySelector('[data-part="' + n + '"]');
const ionsEl = q("ions"), elecEl = q("electrons"), catEl = q("catIons"), anEl = q("anIons");
const needleEl = q("needle"), crankEl = q("crank"), leverEl = q("lever"), wheelEl = q("wheel");
const readout = document.querySelector("[data-readout]");
const still = matchMedia("(prefers-reduced-motion: reduce)");

const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
const voltage = (soc, mode) => clamp(V_MIN + (V_MAX - V_MIN) * soc + (mode === "charge" ? 0.12 : mode === "discharge" ? -0.12 : 0), V_MIN, V_MAX);

function needlePath(v) { const t = clamp((v - 3.0) / 1.2, 0, 1); const a = Math.PI * 0.75 + t * Math.PI * 1.5; return lineOnTop([DIAL[0] - Math.cos(a) * 3, DIAL[1] - Math.sin(a) * 3], [DIAL[0] + Math.cos(a) * (DIAL_R - 3), DIAL[1] + Math.sin(a) * (DIAL_R - 3)], DIAL_Z + 4.2, P); }
function crankPath(angle) { const [cx, cy, cz] = CHG_C; return lineOnTop([cx, cy], [cx + Math.cos(angle) * 5, cy + Math.sin(angle) * 5], cz + 3, P); }
function leverPath(mode) { const a = mode === "charge" ? Math.PI : mode === "discharge" ? 0 : Math.PI / 2; return lineOnTop([0, 0], [Math.cos(a) * 9, Math.sin(a) * 9], ${BUS_TOP} + 8, P); }
function wheelPath(angle) {
  const { cx, cy, cz, r } = MOTOR; const pt = (a, rr) => iso([cx + Math.cos(a) * rr, cy, cz + Math.sin(a) * rr], P);
  let d = ""; for (let i = 0; i < 5; i++) { const a = angle + (i / 5) * Math.PI * 2; d += "M" + pt(0, 0).join(" ") + "L" + pt(a, r).join(" "); }
  const rim = []; for (let i = 0; i <= 20; i++) rim.push(pt(angle + (i / 20) * Math.PI * 2, r));
  return '<path class="iso-line" data-tone="hi" d="' + d + '"/>' + '<path class="iso-line" data-tone="lo" d="M' + rim.map((p) => p.join(" ")).join("L") + 'Z" fill="none"/>';
}

let mode = "charge", soc = 0.2, targetSoc = 0.2;
let ionPhase = [], elecPhase = [], crank = 0, wheel = 0;
for (let i = 0; i < 9; i++) ionPhase.push(i / 9);
for (let i = 0; i < 7; i++) elecPhase.push(i / 7);
let frame = 0, last = 0, visible = false, running = true, tourClock = 0;

function dir() { return mode === "charge" ? 1 : mode === "discharge" ? -1 : 0; }
function setMode(next) {
  mode = next;
  targetSoc = next === "charge" ? 1 : next === "discharge" ? 0 : soc;
  const text = next === "charge" ? "Charging · ions & e− → anode"
    : next === "discharge" ? "Discharging · ions & e− → cathode"
    : "Idle · no current flows";
  if (readout.textContent !== text) readout.textContent = text;
  stage.setAttribute("aria-valuetext", text);
  if (running) run();
}
function setSoc(v) { soc = clamp(v, 0, 1); targetSoc = soc; if (still.matches) draw(); }

function resident(el, count, max, positions) {
  const pts = []; for (let i = 0; i < count; i++) pts.push(iso(positions[i], P));
  el.innerHTML = dotsSvg(pts, { size: 2, tone: "lit" });
}
const catPos = []; for (let i = 0; i < 6; i++) catPos.push([-78, -18 + (i % 3) * 18, 20 + Math.floor(i / 3) * 20]);
const anPos = []; for (let i = 0; i < 6; i++) anPos.push([76, -18 + (i % 3) * 18, GRAPH_Z[Math.floor(i / 3) * 2] + 8]);

function draw() {
  const d = dir();
  const ionPts = []; for (const p of ionPhase) ionPts.push(iso([-54 + p * 108, -8 + (Math.round(p * 8) % 3) * 8, ION_Z], P));
  ionsEl.innerHTML = d === 0 ? "" : dotsSvg(ionPts, { size: 2.3, tone: "lit" });
  const ePts = []; for (const p of elecPhase) ePts.push(iso([-96 + p * 192, 0, ELEC_Z], P));
  elecEl.innerHTML = d === 0 ? "" : dotsSvg(ePts, { size: 1.3, tone: "hi" });
  const v = voltage(soc, mode);
  needleEl.setAttribute("d", needlePath(v));
  crankEl.setAttribute("d", crankPath(crank));
  wheelEl.innerHTML = wheelPath(wheel);
  leverEl.setAttribute("d", leverPath(mode));
  resident(anEl, Math.round(soc * 6), 6, anPos);
  resident(catEl, Math.round((1 - soc) * 6), 6, catPos);
  stage.setAttribute("aria-valuenow", Math.round(soc * 100));
}
function tick(now) {
  const dt = last ? Math.min((now - last) / 1000, 1 / 30) : 1 / 60;
  last = now;
  const d = dir();
  if (running && !still.matches) {
    for (let i = 0; i < ionPhase.length; i++) { ionPhase[i] += d * dt * 0.28; if (ionPhase[i] > 1) ionPhase[i] -= 1; if (ionPhase[i] < 0) ionPhase[i] += 1; }
    for (let i = 0; i < elecPhase.length; i++) { elecPhase[i] += d * dt * 0.5; if (elecPhase[i] > 1) elecPhase[i] -= 1; if (elecPhase[i] < 0) elecPhase[i] += 1; }
    if (mode === "charge") crank += dt * 3.2;
    if (mode === "discharge") wheel += dt * 3.6;
    if (mode !== "idle") { soc = clamp(soc + d * dt * 0.06, 0, 1); if (soc === targetSoc) { tourClock += dt; if (tourClock > 0.8) { tourClock = 0; setMode(mode === "charge" ? "discharge" : "charge"); } } }
  }
  draw();
  frame = visible ? requestAnimationFrame(tick) : 0;
  if (!frame) last = 0;
}
function run() { if (!frame && visible) { last = 0; frame = requestAnimationFrame(tick); } }

new IntersectionObserver((entries) => { visible = entries[entries.length - 1].isIntersecting; if (visible) run(); }, { rootMargin: "120px 0px" }).observe(stage);

stage.addEventListener("pointerdown", () => setMode(mode === "idle" ? "charge" : mode === "charge" ? "discharge" : "idle"));
stage.addEventListener("keydown", (event) => {
  const key = event.key.toLowerCase();
  if (key === "c") { event.preventDefault(); setMode("charge"); }
  else if (key === "d") { event.preventDefault(); setMode("discharge"); }
  else if (key === "i") { event.preventDefault(); setMode("idle"); }
  else if (event.key === " ") { event.preventDefault(); running = !running; if (running) run(); }
  else if (event.key === "ArrowUp") { event.preventDefault(); setSoc(soc + 0.05); }
  else if (event.key === "ArrowDown") { event.preventDefault(); setSoc(soc - 0.05); }
});
setMode("charge");
draw();
`;

const body = k.plateHtml({
  fig: "Fig 2",
  title: "Li-ion charge / discharge",
  hint: "Click or press C / D / I",
  readout: "Charging · ions & e− → anode",
  keys: [
    { mark: "lit", label: "Lithium ions across the electrolyte, electrons along the circuit" },
    { mark: "raised", label: "LiCoO₂ cathode, graphite anode, charger, load motor, voltage dial" },
  ],
  caption:
    "A lithium-ion cell. Charging uses the charger to pull electrons off the LiCoO₂ cathode and push them through the circuit into the graphite anode, while Li+ ions cross the electrolyte to meet them — the anode fills and the voltage climbs to 4.2 V. Discharging reverses both: ions leave the anode and return to the cathode, electrons take the circuit through the load and spin the motor, and the voltage falls toward 3.0 V. Energy is stored and released by shuttling ions between the two electrodes, never by consuming them.",
  body: `<div class="iso-stage" tabindex="0" role="button" aria-label="Lithium-ion cell charge and discharge. Press C to charge, D to discharge, I for idle, up and down arrows to set the state of charge.">${svg}</div>`,
});

const filename = theme === "light" ? "libatt-light.html" : "libatt.html";
writeFileSync(new URL(filename, import.meta.url), k.pageHtml({ title: "EV lithium-ion battery: charge and discharge", theme, body, script: kitScript() + live }));
console.log("wrote", filename);
