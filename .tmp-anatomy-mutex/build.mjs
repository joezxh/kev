// Anatomy figure: "How a mutex prevents a race condition" — a token-gated tally press.
// Standalone SVG + live model. Build: `node build.mjs [--light]`.
import { writeFileSync } from "node:fs";
import * as k from "file:///C:/Users/joezxh/.qoder/skills/anatomy/kit/iso-kit.mjs";
import { kitScript } from "file:///C:/Users/joezxh/.qoder/skills/anatomy/scripts/inline-kit.mjs";

const theme = process.argv.includes("--light") ? "light" : "dark";

const WIDTH = 680;
const HEIGHT = 430;

// ---- world layout -------------------------------------------------------
const PLATE = { x: -168, y: -80, w: 336, d: 160, r: 12 };
const PLATE_H = 12;
const FOOT_H = 5;

const TOWER = { x: -26, y: -22, w: 52, d: 44, r: 5 };
const TOWER_TOP = 62;

const REST_A = -120, WAIT_A = -80, DOCK_A = -58, BOLL_A = -50;
const REST_B = 120, WAIT_B = 80, DOCK_B = 58, BOLL_B = 50;

const CARRIAGE = { x: -28, y: -22, w: 56, d: 44, r: 3 };
const RAIL_TOP = 6;
const CARRIAGE_Z = RAIL_TOP;
const CARRIAGE_TOP = CARRIAGE_Z + 7;

const BOLL_H = 44;
const BOLL_UP = 0;      // raised: bars the lane
const BOLL_OPEN = -40;  // retracted into the base: lane free

const BRIDGE_Z = 76;
const TOKEN_X = { a: -34, free: 0, b: 34 };

const P = k.fitProjection(
  [
    ...k.boxCorners(PLATE, -PLATE_H - FOOT_H, 0),
    ...k.boxCorners(TOWER, 0, TOWER_TOP),
    [-BOLL_A - 6, -6, BOLL_H], [BOLL_B + 6, 6, BOLL_H],
    [TOKEN_X.a, 0, BRIDGE_Z + 12], [TOKEN_X.b, 0, BRIDGE_Z + 12],
    [-150, 78, 0], [150, 78, 0],
  ],
  WIDTH, HEIGHT,
  { pad: 28, azimuth: 42 },
);

const at = (pt) => k.iso(pt, P);
const S = (paths, style) => k.solidSvg(paths, style);
const L = (d, style) => k.lineSvg(d, style);
const D = (points, style) => k.dotsSvg(points, style);
const byDepth = (pts) => [...pts].sort((a, b) => k.depthOf([a[0], a[1], 0], P) - k.depthOf([b[0], b[1], 0], P));
const faceNum = (part, transform, size) => `<text class="iso-face-text" data-part="${part}" transform="${transform}" font-size="${size}" text-anchor="middle" data-tone="lit">—</text>`;

// ---- base ---------------------------------------------------------------
function plate() {
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
  // front ruler strip
  const strip = { x: -150, y: PLATE.y + PLATE.d - 18, w: 300, d: 8, r: 1.4 };
  out.push(S(k.slabOf(strip, 0, 0.7, P, 3), { tone: "lo", crease: "none" }));
  const ticks = k.topTicks(strip.x + 6, strip.x + strip.w - 6, 5, 5, strip.y + 1, 0.7, [2.2, 4], P);
  out.push(L(ticks.minor, { tone: "lo" }), L(ticks.major, { tone: "mid" }));
  // engraved label plate
  const label = { x: -46, y: PLATE.y + PLATE.d - 34, w: 92, d: 12, r: 1.4 };
  out.push(S(k.slabOf(label, 0, 1, P, 3, 0.4), { tone: "lo", crease: "faint" }));
  out.push(k.faceTextSvg(k.topMatrix([0, label.y + 6], 1, P, "x"), "TALLY PRESS", { size: 4, tone: "mid", anchor: "middle" }));
  return out.join("");
}

// ---- rails + end stops --------------------------------------------------
function rails() {
  const out = [];
  for (const [xa, xb] of [[-158, -34], [34, 158]]) {
    for (const y of [-14, 14]) {
      out.push(S(k.slabOf({ x: xa, y, w: xb - xa, d: 5, r: 1 }, 0, RAIL_TOP, P, 3, 0.4), { tone: "mid" }));
      out.push(D([at([xa + 6, y + 2.5, RAIL_TOP]), at([xb - 6, y + 2.5, RAIL_TOP])], { size: 0.4 }));
    }
  }
  // outer end stops with a coil
  for (const [x, dir] of [[-158, 1], [158, -1]]) {
    out.push(S(k.slabOf({ x: dir > 0 ? x : x - 8, y: -18, w: 8, d: 36, r: 1.4 }, 0, 16, P, 3, 0.5), { tone: "mid" }));
    out.push(D([at([dir > 0 ? x + 4 : x - 4, -10, 16]), at([dir > 0 ? x + 4 : x - 4, 10, 16])], { size: 0.45 }));
    const coil = k.coil([dir > 0 ? x + 8 : x - 20, 0, 9], [dir > 0 ? x + 20 : x - 8, 0, 9], [dir > 0 ? x + 14 : x - 14, 0], 4, 3, "x", P);
    out.push(L(coil.back, { tone: "lo" }), L(coil.front, { tone: "mid" }));
  }
  return out.join("");
}

// ---- counter tower (the shared variable) --------------------------------
function tower() {
  const out = [];
  out.push(S(k.slabOf({ x: TOWER.x - 4, y: TOWER.y - 4, w: TOWER.w + 8, d: TOWER.d + 8, r: 6 }, 0, 6, P, 8, 0.6), { tone: "mid" }));
  out.push(S(k.slabOf(k.insetPlan(TOWER, 0.6), 6, TOWER_TOP - 6, P, 8, 0.8), { tone: "hi", crease: "lo" }));
  out.push(L(k.planOutline(k.insetPlan(TOWER, 4), TOWER_TOP, P), { tone: "faint" }));
  // two write-port blocks on the side faces
  for (const sx of [-1, 1]) {
    out.push(S(k.slabOf({ x: sx < 0 ? TOWER.x - 1 : TOWER.x + TOWER.w - 5, y: -6, w: 6, d: 12, r: 1.6 }, 26, 12, P, 3, 0.3), { tone: "lo", crease: "faint" }));
  }
  // bezel + cap
  out.push(S(k.cylinder(0, 0, 20, TOWER_TOP, 4, P, 56, 0.6), { tone: "mid" }));
  out.push(S(k.cylinder(0, 0, 17, TOWER_TOP + 4, 3, P, 56, 0.5), { tone: "hi", crease: "lo" }));
  out.push(L(k.ring(0, 0, 15, TOWER_TOP + 7, P, 48), { tone: "lo" }));
  const capScrews = k.corners({ x: -14, y: -14, w: 28, d: 28, r: 2 }, 2);
  out.push(D(capScrews.map(([x, y]) => at([x, y, TOWER_TOP + 7])), { size: 0.5 }));
  // the live count, on the front face where the bridge never covers it
  out.push(faceNum("counter", k.sideMatrix([0, TOWER.y + TOWER.d], 34, P, "left"), 20));
  out.push(k.faceTextSvg(k.sideMatrix([0, TOWER.y + TOWER.d], 52, P, "left"), "COUNT", { size: 4, tone: "mid", anchor: "middle" }));
  return out.join("");
}

// ---- rising bollard gate for one lane -----------------------------------
function bollard(x) {
  const out = [];
  out.push(S(k.cylinder(x, 0, 7, 0, 3, P, 32), { tone: "mid" }));
  out.push(S(k.cylinder(x, 0, 4.4, 2, BOLL_H - 2, P, 28, 0.5), { tone: "hi", crease: "lo" }));
  out.push(L([12, 26].map((z) => k.sideArc(x, 0, 4.4, z, P, 14)).join(""), { tone: "faint" }));
  out.push(S(k.cylinder(x, 0, 5.4, BOLL_H, 2.4, P, 28), { tone: "mid" }));
  out.push(D([at([x, 0, BOLL_H + 2.4])], { size: 0.6, tone: "hi" }));
  return out.join("");
}

// ---- a thread carriage (read window + write stamp) ----------------------
function carriage(isLeft) {
  const dir = isLeft ? 1 : -1;
  const out = [`<path class="iso-halo" d="${k.haloOf(k.insetPlan(CARRIAGE, 3), CARRIAGE_Z, 0.1, P)}" style="filter:blur(4px)"/>`];
  // bushings riding the rails
  for (const y of [-14, 14]) out.push(S(k.cylinder(dir * 16, y, 5, CARRIAGE_Z, 3, P, 20), { tone: "lo", crease: "none" }));
  out.push(S(k.slabOf(CARRIAGE, CARRIAGE_Z, CARRIAGE_TOP - CARRIAGE_Z, P, 5, 0.6), { tone: "mid" }));
  out.push(L(k.lineOnTop([CARRIAGE.x, -18], [CARRIAGE.x + CARRIAGE.w, -18], CARRIAGE_TOP, P), { tone: "faint" }));
  out.push(L(k.lineOnTop([CARRIAGE.x, 18], [CARRIAGE.x + CARRIAGE.w, 18], CARRIAGE_TOP, P), { tone: "faint" }));
  out.push(D([at([-20, -18, CARRIAGE_TOP]), at([20, -18, CARRIAGE_TOP]), at([-20, 18, CARRIAGE_TOP]), at([20, 18, CARRIAGE_TOP])], { size: 0.4 }));
  // read window puck
  const rp = [-10 * dir, 6];
  out.push(S(k.cylinder(rp[0], rp[1], 9, CARRIAGE_TOP, 3, P, 32, 0.4), { tone: "hi", crease: "lo" }));
  out.push(L(k.ring(rp[0], rp[1], 7.4, CARRIAGE_TOP + 3, P, 28), { tone: "lo" }));
  out.push(`<text class="iso-face-text" data-part="read${isLeft ? "A" : "B"}" transform="${k.topMatrix([rp[0], rp[1]], CARRIAGE_TOP + 3, P, "x")}" font-size="8" text-anchor="middle" data-tone="lit">—</text>`);
  out.push(k.faceTextSvg(k.topMatrix([rp[0], rp[1] - 12], CARRIAGE_TOP + 0.2, P, "x"), isLeft ? "THREAD A" : "THREAD B", { size: 2.6, tone: "mid", anchor: "middle" }));
  // knurled handwheel
  const kn = [16 * dir, -14];
  out.push(S(k.cylinder(kn[0], kn[1], 5, CARRIAGE_TOP, 4, P, 24), { tone: "mid" }));
  out.push(L(k.knurl(kn[0], kn[1], 5, CARRIAGE_TOP, CARRIAGE_TOP + 4, 26, P, 0.3), { tone: "lo" }));
  // write stamp bar reaching the tower (local, moved along x by ext)
  const stamp = `<g data-part="stamp${isLeft ? "A" : "B"}" transform="${k.translateAlong(P, [-8, 0, 0])}">` +
    S(k.cylinder(dir * 26, 0, 2.4, 30, 6, P, 20), { tone: "hi", crease: "none" }) +
    S(k.slabOf({ x: 24, y: -3, w: 16, d: 6, r: 1.6 }, 30, 6, P, 3, 0.4), { tone: "mid" }) +
    S(k.slabOf({ x: 38, y: -5, w: 5, d: 10, r: 1.2 }, 28, 10, P, 3, 0.4), { tone: "hi", crease: "lo" }) +
    `</g>`;
  return { body: out.join(""), stamp };
}

// ---- the top bridge + captive token (the mutex) -------------------------
function bridge() {
  const out = [];
  for (const x of [-42, 42]) {
    out.push(S(k.cylinder(x, 0, 3, TOWER_TOP, BRIDGE_Z - TOWER_TOP, P, 24, 0.4), { tone: "mid", crease: "none" }));
    out.push(L(k.sideArc(x, 0, 3, TOWER_TOP + 8, P, 14), { tone: "faint" }));
  }
  out.push(S(k.slabOf({ x: -48, y: -5, w: 96, d: 10, r: 2.4 }, BRIDGE_Z, 5, P, 4, 0.5), { tone: "mid" }));
  const bt = k.topTicks(-40, 40, 8, 4, -4, BRIDGE_Z + 5, [2, 3.4], P);
  out.push(L(bt.minor, { tone: "lo" }), L(bt.major, { tone: "mid" }));
  return out.join("");
}

function token() {
  const out = [];
  const z = BRIDGE_Z + 5;
  out.push(S(k.cylinder(0, 0, 8.5, z, 3, P, 40, 0.5), { tone: "hi", lit: true, crease: "lo" }));
  out.push(L(k.knurl(0, 0, 8.5, z, z + 3, 40, P, 0.3), { tone: "lit" }));
  out.push(S(k.cylinder(0, 0, 6, z + 3, 2.4, P, 32, 0.4), { tone: "hi", lit: true }));
  out.push(L(k.ring(0, 0, 3.4, z + 5.4, P, 24), { tone: "lit" }));
  out.push(L(k.lineOnTop([0, 0], [0, -3.4], z + 5.4, P), { tone: "lit" }));
  out.push(D([at([0, 0, z + 5.4])], { size: 0.7, tone: "lit" }));
  return out.join("");
}

// ---- assemble (painter's order: far lane, tower, near lane) -------------
function render() {
  const a = carriage(true);
  const b = carriage(false);
  const body = [
    plate(),
    rails(),
    `<g data-part="boltA" transform="${k.translateAlong(P, [0, 0, 0])}">${bollard(BOLL_A)}</g>`,
    `<g data-part="carriageA" transform="${k.translateAlong(P, [REST_A, 0, 0])}">${a.body}${a.stamp}</g>`,
    tower(),
    bridge(),
    `<g data-part="boltB" transform="${k.translateAlong(P, [0, 0, 0])}">${bollard(BOLL_B)}</g>`,
    `<g data-part="carriageB" transform="${k.translateAlong(P, [REST_B, 0, 0])}">${b.body}${b.stamp}</g>`,
    `<g data-part="token" transform="${k.translateAlong(P, [TOKEN_X.free, 0, 0])}">${token()}</g>`,
  ];
  return k.figureSvg({
    width: WIDTH,
    height: HEIGHT,
    label:
      "A token-gated tally press. A central counter tower holds the shared count. Two thread carriages ride rails from the left and right; each has a read window showing the value it sampled and a stamp that writes value+1 back. A captive token on a top bridge marks the one thread allowed in, and a rising bollard bars the lane of the thread that does not hold it.",
    body,
  });
}

const svg = render();

// ---- live model ---------------------------------------------------------
const EVENTS = {
  off: [
    { dur: 0.7, ax: REST_A, bx: REST_B, ae: -8, be: -8, alz: BOLL_OPEN, blz: BOLL_OPEN, tx: TOKEN_X.free, ca: 5, ra: null, rb: null, msg: "Mutex OFF · both threads run count = count + 1" },
    { dur: 0.9, ax: DOCK_A, bx: DOCK_B, ra: 5, rb: 5, msg: "Both read the same value, 5" },
    { dur: 0.7, ae: 0, ca: 6, msg: "Thread A writes 5 + 1 = 6" },
    { dur: 0.9, be: 0, ca: 6, msg: "Thread B writes 5 + 1 = 6 — A's increment is lost" },
    { dur: 0.9, ax: REST_A, bx: REST_B, ae: -8, be: -8, msg: "Counter 6 after two writes: one update lost" },
  ],
  on: [
    { dur: 0.7, ax: REST_A, bx: REST_B, ae: -8, be: -8, alz: BOLL_OPEN, blz: BOLL_OPEN, tx: TOKEN_X.free, ca: 5, ra: null, rb: null, msg: "Mutex ON · one token, one thread in the critical section" },
    { dur: 0.8, tx: TOKEN_X.a, blz: BOLL_UP, msg: "Thread A takes the token; a bolt rises across B's lane" },
    { dur: 0.8, ax: DOCK_A, bx: WAIT_B, msg: "A enters; B is stopped short by the bolt" },
    { dur: 0.6, ra: 5, msg: "A reads the count: 5" },
    { dur: 0.7, ae: 0, ca: 6, msg: "A writes 5 + 1 = 6" },
    { dur: 0.8, ax: REST_A, ae: -8, blz: BOLL_OPEN, tx: TOKEN_X.free, bx: REST_B, msg: "A releases the token; the bolt drops" },
    { dur: 0.8, tx: TOKEN_X.b, alz: BOLL_UP, bx: DOCK_B, ax: WAIT_A, msg: "Thread B takes the token; a bolt bars A's lane" },
    { dur: 0.6, rb: 6, msg: "B reads the count: 6" },
    { dur: 0.7, be: 0, ca: 7, msg: "B writes 6 + 1 = 7" },
    { dur: 1.0, bx: REST_B, be: -8, alz: BOLL_OPEN, tx: TOKEN_X.free, msg: "Counter 7 after two writes: nothing lost" },
  ],
};

const live = `
const P = ${JSON.stringify(P)};
const TOKEN_X = ${JSON.stringify(TOKEN_X)};
const EVENTS = ${JSON.stringify(EVENTS)};
const stage = document.querySelector(".iso-stage");
const svg = stage.querySelector("svg");
const q = (n) => svg.querySelector('[data-part="' + n + '"]');
const carriageA = q("carriageA"), carriageB = q("carriageB");
const stampA = q("stampA"), stampB = q("stampB");
const boltA = q("boltA"), boltB = q("boltB");
const token = q("token");
const counterEl = q("counter"), readAEl = q("readA"), readBEl = q("readB");
const readout = document.querySelector("[data-readout]");
const still = matchMedia("(prefers-reduced-motion: reduce)");

let mode = "off";
let cur = { ax: EVENTS.off[0].ax, bx: EVENTS.off[0].bx, ae: -8, be: -8, alz: -40, blz: -40, tx: TOKEN_X.free };
let tgt = Object.assign({}, cur);
let clock = 0, index = 0, frame = 0, last = 0, visible = false, running = true;

function applyEvent() {
  const e = EVENTS[mode][index];
  tgt = Object.assign({}, tgt, { ax: e.ax, bx: e.bx, ae: e.ae, be: e.be, alz: e.alz, blz: e.blz, tx: e.tx });
  if ("ca" in e) counterEl.textContent = String(e.ca);
  if ("ra" in e) readAEl.textContent = e.ra === null ? "—" : String(e.ra);
  if ("rb" in e) readBEl.textContent = e.rb === null ? "—" : String(e.rb);
  const text = e.msg;
  if (readout.textContent !== text) readout.textContent = text;
  stage.setAttribute("aria-valuetext", text);
  stage.setAttribute("aria-valuenow", counterEl.textContent);
}
function setMode(next) {
  mode = next; index = 0; clock = 0;
  counterEl.textContent = "5"; readAEl.textContent = "—"; readBEl.textContent = "—";
  applyEvent();
  if (running) run();
}
function draw() {
  carriageA.setAttribute("transform", translateAlong(P, [cur.ax, 0, 0]));
  carriageB.setAttribute("transform", translateAlong(P, [cur.bx, 0, 0]));
  stampA.setAttribute("transform", translateAlong(P, [cur.ae, 0, 0]));
  stampB.setAttribute("transform", translateAlong(P, [cur.be, 0, 0]));
  boltA.setAttribute("transform", translateAlong(P, [0, 0, cur.alz]));
  boltB.setAttribute("transform", translateAlong(P, [0, 0, cur.blz]));
  token.setAttribute("transform", translateAlong(P, [cur.tx, 0, 0]));
}
function followTo(key, dt) {
  const calm = still.matches;
  cur[key] = calm ? tgt[key] : cur[key] + (tgt[key] - cur[key]) * (1 - Math.exp(-dt / 0.26));
  if (Math.abs(tgt[key] - cur[key]) < 0.01) cur[key] = tgt[key];
}
function tick(now) {
  const dt = last ? Math.min((now - last) / 1000, 1 / 30) : 1 / 60;
  last = now;
  if (running && !still.matches) {
    clock += dt;
    const seq = EVENTS[mode];
    let acc = 0, next = 0;
    for (let i = 0; i < seq.length; i++) { acc += seq[i].dur; if (clock < acc) { next = i; break; } next = (i + 1) % seq.length; }
    if (clock > acc) clock -= acc;
    if (next !== index) { index = next; applyEvent(); }
  }
  for (const key of ["ax", "bx", "ae", "be", "alz", "blz", "tx"]) followTo(key, dt);
  draw();
  frame = visible ? requestAnimationFrame(tick) : 0;
  if (!frame) last = 0;
}
function run() { if (!frame && visible) { last = 0; frame = requestAnimationFrame(tick); } }

new IntersectionObserver((entries) => {
  visible = entries[entries.length - 1].isIntersecting;
  if (visible) run();
}, { rootMargin: "120px 0px" }).observe(stage);

stage.addEventListener("pointerdown", () => setMode(mode === "off" ? "on" : "off"));
stage.addEventListener("keydown", (event) => {
  if (event.key === "m" || event.key === "M") { event.preventDefault(); setMode(mode === "off" ? "on" : "off"); }
  if (event.key === " ") { event.preventDefault(); running = !running; if (running) run(); }
});
applyEvent();
draw();
`;

const body = k.plateHtml({
  fig: "Fig 1",
  title: "Mutex vs race",
  hint: "Click or press M to toggle the lock",
  readout: "Mutex OFF · both threads run count = count + 1",
  keys: [
    { mark: "lit", label: "Captive token + raised bolts: the mutex serialising access" },
    { mark: "raised", label: "Counter tower (shared count) and the two thread carriages" },
  ],
  caption:
    "Two threads each run count = count + 1. With the mutex off, both sample the same value and write it back, so two writes add one — a lost update. With the mutex on, the token and the bollard let only one thread read-modify-write at a time, so the counter lands where it should.",
  body: `<div class="iso-stage" tabindex="0" role="button" aria-label="Mutex and race-condition press. Press M or click to toggle the lock; press space to pause.">${svg}</div>`,
});

const filename = theme === "light" ? "mutex-light.html" : "mutex.html";
writeFileSync(new URL(filename, import.meta.url), k.pageHtml({ title: "How a mutex prevents a race condition", theme, body, script: kitScript() + live }));
console.log("wrote", filename);
