/*
 * 锂电池台 — 新能源电动汽车用锂电池充放电原理与过程 (Hero, SVG-only)
 * 工作台上一组六只方壳电芯串联成模块：最前一只在观众侧剖开，露出正极板/隔膜/负极板叠层，
 * Li+ 离子在极板间隙间穿梭；右后直流充电柜与右前驱动电机经母线箱(PBD)和电缆挂接；
 * 支架两只表盘读电压与电流， knobs 选充电/放电。粒子、指针、风扇、SOC 条都由 model.mjs 驱动。
 * node build.mjs            -> 写 liion-bench.html（并写 light 版）
 * node build.mjs --audit    -> 跑几何审计； --quick 只跑静止态深度排序
 */
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import * as k from "file:///C:/Users/joezxh/.qoder/skills/anatomy/kit/iso-kit.mjs";
import * as G from "file:///C:/Users/joezxh/.qoder/skills/anatomy/kit/lathe.mjs";
import { tubePieces, tubeSvg } from "file:///C:/Users/joezxh/.qoder/skills/anatomy/kit/tube.mjs";
import * as A from "file:///C:/Users/joezxh/.qoder/skills/anatomy/kit/audit.mjs";
import { kitScript } from "file:///C:/Users/joezxh/.qoder/skills/anatomy/scripts/inline-kit.mjs";
import { CELL, ocv } from "./model.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const THEME = process.argv.includes("--light") ? "light" : "dark";

const WIDTH = 640;
const HEIGHT = 560;
const AZIMUTH = 146;
const ELEVATION = 27;

// ---------- 世界坐标 ----------
const PLATE = { x: -172, y: -74, w: 344, d: 148, r: 10 };
const PLATE_H = 10;
const FOOT_H = 6;

const TRAY = { x: -62, y: -34, w: 116, d: 70, r: 3 };
const WALL = 4;
const CELL_W = 15;
const CELL_PITCH = 18.6;
const CELL_H = 76;
const CELLS = 6;
const cellX = (i) => -58 + CELL_PITCH * i;

const CHG = { x: 120, y: -66, w: 38, d: 32, h: 106 };
const PBD = { x: 54, y: -24, w: 10, d: 32, z0: 22, z1: 66 };
const BLK = { x: 54.4, y: -12, w: 7.6, d: 7, z0: 66, z1: 93.5 };
const STRAP = { x: -55.7, y: -9.9, w: 117.2, d: 3.8, z0: 93.5, z1: 94.7 };
const BRIDGE = { x: 43.9, y: -10.6, w: 9.5, d: 5.2, z0: 89.5, z1: 91 };
const RISER_L = { x: -55.9, y: -9.9, w: 2.8, d: 3.8, z0: 89.5, z1: 93.5 };
const MOTOR = { cx: 111, cz: 22, r: 18, y0: 4, y1: 40 };
const MBOX = { x: 104, y: 16, w: 14, d: 20, z0: 40, z1: 56 };

const GAUGE = {
  post: [[12, 44], [36, 44]],
  base: { x: 4, y: 40, w: 40, d: 8, r: 2 },
  z: 56, R: 11, H: 4.5,
};
const G_V = { at: [12, 44], z: GAUGE.z + GAUGE.H };
const G_A = { at: [36, 44], z: GAUGE.z + GAUGE.H };

const KNOB = { at: [-80, 46] };

const P = k.fitProjection(
  [
    ...k.boxCorners(PLATE, -PLATE_H - FOOT_H, 0),
    [CHG.x, CHG.y, CHG.h + 8], [CHG.x + CHG.w, CHG.y, CHG.h + 8], [CHG.x + CHG.w, CHG.y + CHG.d, CHG.h + 8],
    [STRAP.x, STRAP.y, STRAP.z1], [STRAP.x + STRAP.w, STRAP.y + STRAP.d, STRAP.z1],
    [MOTOR.cx - 12, 47.4, MOTOR.cz + 12], [MOTOR.cx + 12, 47.4, MOTOR.cz - 12],
    [G_A.at[0] + GAUGE.R + 3, G_A.at[1] + GAUGE.R + 3, G_A.z + 1],
    [KNOB.at[0] - 9, KNOB.at[1] + 9, 7], [PLATE.x, PLATE.y + PLATE.d, 0], [PLATE.x + PLATE.w, PLATE.y, 0],
  ],
  WIDTH, HEIGHT, { pad: 30, azimuth: AZIMUTH, elevation: ELEVATION },
);
const V = G.viewOf(P);
const KS = G.scaleOf(P);

const at = (p) => k.iso(p, P);
const S = (paths, style) => k.solidSvg(paths, style);
const Ln = (d, style) => k.lineSvg(d, style);
const Dots = (points, style) => k.dotsSvg(points, style);
const path3 = (points, closed = false) => k.pathOf(points.map(at), closed);
const f2 = (v) => Math.round(v * 100) / 100;
const byDepth = (points) => [...points].sort((a, b) => k.depthOf([a[0], a[1], 0], P) - k.depthOf([b[0], b[1], 0], P));
const keyAt = (p) => G.dot3(p, V);

// ---------- 记录器 ----------
const R = A.recorder(P);
const record = R.solid;
function put(name, ref, svg, shapes = [], { bias = 0, ...rest } = {}) {
  return R.put({ name, at: ref, bias, svg, shapes, piece: "scene", ...rest });
}

function box(name, [x0, y0, z0], [x1, y1, z1], { tone = "mid", r = 0.4, steps = 2, bevel = 0, crease, lit, inner = "", extra = "", bias = 0, piece = "scene", owner } = {}) {
  const plan = { x: x0, y: y0, w: x1 - x0, d: y1 - y0, r };
  const shape = record(A.slab(plan, z0, z1 - z0, { name, ...(owner ? { owner } : {}) }, steps));
  put(name, [(x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2],
    S(k.slabOf(plan, z0, z1 - z0, P, steps, bevel), { tone, crease, lit, inner }) + extra, [shape], { bias, piece });
  return shape;
}
function slab(name, plan, z, h, opts = {}) {
  return box(name, [plan.x, plan.y, z], [plan.x + plan.w, plan.y + plan.d, z + h], opts);
}
const YF = G.frameOf([0, MOTOR.cz * 0, MOTOR.cz * 0], [0, 1, 0], [1, 0, 0], [0, 0, 1]); // y 轴回转框架（原点逐次 add 到 o）
function frameY(atXZ) { return G.frameOf([atXZ[0], 0, atXZ[1]], [0, 1, 0], [1, 0, 0], [0, 0, 1]); }
const ZF = G.frameOf([0, 0, 0], [0, 0, 1], [1, 0, 0], [0, 1, 0]);
function frameZ(o) { return G.frameOf([o[0], o[1], 0], [0, 0, 1], [1, 0, 0], [0, 1, 0]); }

function turned(name, F, profile, { tone = "mid", bevel = 0, smooth, steps, rims, inner = "", extra = "", bias = 0, owner, lit } = {}) {
  const opts = { bevel, ...(smooth !== undefined ? { smooth } : {}), ...(steps ? { steps } : {}), ...(rims ? { rims } : {}) };
  const paths = G.solidOf(profile, F, P, opts);
  const mid = (profile[0][0] + profile[profile.length - 1][0]) / 2;
  const shape = record(A.solid(F, profile, { name, owner }));
  put(name, G.add3(G.add3(F.o, G.mul3(F.a, mid)), G.mul3(F.u, 0)), S(paths, { tone, inner, lit }) + extra, [shape], { bias });
  return shape;
}
function post(name, cx, cy, z0, z1, r, opts = {}) {
  const shape = record(A.cylinder(cx, cy, r, z0, z1 - z0, { name, ...(opts.owner ? { owner: opts.owner } : {}) }));
  put(name, [cx, cy, (z0 + z1) / 2], S(k.cylinder(cx, cy, r, z0, z1 - z0, P, opts.steps ?? 20, opts.bevel ?? 0), { tone: opts.tone ?? "mid", inner: opts.inner ?? "", lit: opts.lit }), [shape], { bias: opts.bias ?? 0 });
  return shape;
}
function port(name, center, axis, r, y0, y1, opts = {}) {
  const F = axis === "y" ? frameY([center[0], center[2]]) : null;
  const a = axis === "y" ? [0, 1, 0] : null;
  const o = axis === "y" ? [center[0], y0, center[2]] : null;
  const Fr = G.frameOf(o, a, [1, 0, 0], [0, 0, 1]);
  const shape = record(A.disc(Fr, 0, y1 - y0, r, { name, owner: opts.owner, ...(opts.cut ? { seated: true, cut: opts.cut } : {}) }));
  put(name, [center[0], (y0 + y1) / 2, center[2]], S(G.disc(0, y1 - y0, r, Fr, P, { steps: 20, bevel: 0.2 }), { tone: opts.tone ?? "mid" }), [shape], { bias: opts.bias ?? 0.05 });
  return shape;
}
// 沿 x 轴的凸台端口（用于 x=常数的墙面）
function portX(name, center, r, x0, x1, opts = {}) {
  const F = G.frameOf([x0, center[1], center[2]], [1, 0, 0], [0, 1, 0], [0, 0, 1]);
  const shape = record(A.disc(F, 0, x1 - x0, r, { name, owner: opts.owner, ...(opts.cut ? { seated: true, cut: opts.cut } : {}) }));
  put(name, [(x0 + x1) / 2, center[1], center[2]], S(G.disc(0, x1 - x0, r, F, P, { steps: 20, bevel: 0.2 }), { tone: opts.tone ?? "mid" }), [shape], { bias: opts.bias ?? 0.05 });
  return shape;
}
function stud(name, cx, cy, z0, z1, r, opts = {}) {
  const shape = record(A.cylinder(cx, cy, r, z0, z1 - z0, { name, owner: opts.owner }));
  put(name, [cx, cy, (z0 + z1) / 2], S(k.cylinder(cx, cy, r, z0, z1 - z0, P, 16), { tone: opts.tone ?? "mid" }), [shape], { bias: opts.bias ?? 0.05 });
}

const CABLES = [];
// Catmull-Rom 采样：电缆是一条大半径的空间曲线，而不是折线——折点缓转会被相机压成
// 一个比管宽还小的屏半径（audit 的 folds / self-overlap），样条把转弯摊开成长弧。
function spline(pts, per = 14) {
  const p = [pts[0], ...pts, pts[pts.length - 1]];
  const out = [];
  for (let i = 1; i < p.length - 2; i++) {
    const [a, b, c, d] = [p[i - 1], p[i], p[i + 1], p[i + 2]];
    for (let s = 0; s < per; s++) {
      const t = s / per, t2 = t * t, t3 = t2 * t;
      out.push([0, 1, 2].map((j) => 0.5 * (2 * b[j] + (-a[j] + c[j]) * t + (2 * a[j] - 5 * b[j] + 4 * c[j] - d[j]) * t2 + (-a[j] + 3 * b[j] - 3 * c[j] + d[j]) * t3)));
    }
  }
  out.push([...pts[pts.length - 1]]);
  return out;
}
function cable(name, points, r = 0.9, { tone = "mid", bend = 3, maxLength = 12, bias = 0.05, gaps = [], rings, touch = [], bundle, shells = [false, false], smooth = false } = {}) {
  const route = smooth ? points : G.fillet(points, Math.max(bend, r * 2.6), 10, { P, tube: r });
  const total = G.pathLength(route);
  const SHELL = Math.max(1.8, r * 2.4);
  // gaps 是「挖掉的弧长区间」：套环占了端口外侧那一段，管体从套环外口起画
  const GAPS = [...gaps, ...(shells[0] ? [[0, SHELL + 0.05]] : []), ...(shells[1] ? [[total - SHELL - 0.05, total]] : [])];
  R.route(name, route, r, { gaps: GAPS, limp: true, touch, bundle, piece: "scene", rims: shells.map((on) => (on ? r * 0.85 : r)) });
  CABLES.push(name);
  tubePieces(route, r, P, { maxLength, spacing: Math.max(0.6, Math.min(1.6, r)), gaps: GAPS, ...(rings ? { rings } : {}) }).forEach((piece, index) =>
    put(`${name}:${index}`, piece.mid, tubeSvg(piece, { tone }), [A.tube(piece.points, piece.radii)], { bias, route: name, chunk: index, attrs: ` data-route="${name}" data-chunk="${index}"` }),
  );
  // 端口套环（arcade 式）：立在端口 mouth 外侧，管体从环口伸入
  [0, 1].forEach((index) => {
    if (!shells[index]) return;
    const end = index ? route[route.length - 1] : route[0];
    const tangent = G.tangentAlong(route, index ? total : 0);
    const F = G.frameAlong(end, tangent);
    const [s0, s1] = index ? [-SHELL, -0.05] : [0.05, SHELL];
    const shape = record(A.disc(F, s0, s1, r * 1.2, { name: `${name}.shell${index}`, owner: name }));
    put(`${name}.shell${index}`, G.add3(end, G.mul3(tangent, (s0 + s1) / 2)), S(G.disc(s0, s1, r * 1.2, F, P, { steps: 20, bevel: 0.2 }), { tone: "mid" }), [shape], { bias: bias + 0.1 });
  });
  return route;
}

// =====================================================================
// 1. 工作台
// =====================================================================
const back = [];
back.push(`<path class="iso-halo" d="${k.haloOf(PLATE, -PLATE_H - FOOT_H, PLATE_H, P)}"/>`);
for (const [x, y] of byDepth(k.corners(PLATE, 24))) {
  back.push(S(k.cylinder(x, y, 7, -PLATE_H - FOOT_H, 1.6, P, 28), { tone: "lo" }));
  back.push(S(k.cylinder(x, y, 5.4, -PLATE_H - FOOT_H + 1.6, FOOT_H - 1.6, P, 28), { tone: "mid" }));
}
back.push(S(k.slabOf(PLATE, -PLATE_H, PLATE_H, P, 8, 1.6), { tone: "mid", inner: Ln(k.sideSeam(PLATE, -4, P, 8), { tone: "faint" }) }));
back.push(Ln(k.planOutline(k.insetPlan(PLATE, 5), 0, P), { tone: "lo" }));
// 台面铣出的 T 型槽：托盘与试样就是用螺栓拧进这些槽里的（槽线两端落在内圈刻线上）
for (const sy of [-52, -26, 0, 26, 52])
  back.push(Ln(path3([[-167, sy - 0.9, 0], [167, sy - 0.9, 0]]) + path3([[-167, sy + 0.9, 0], [167, sy + 0.9, 0]]), { tone: "faint" }));
const plateScrews = k.corners(PLATE, 11);
back.push(Ln(plateScrews.map(([x, y]) => k.ring(x, y, 2.2, 0, P, 16)).join(""), { tone: "lo" }));
back.push(Dots(plateScrews.map(([x, y]) => at([x, y, 0])), { size: 0.5 }));
record(A.slab(PLATE, -PLATE_H, PLATE_H, { name: "stand.plate", ground: true }, 8));
const STRIP = { x: -150, y: PLATE.y + PLATE.d - 13, w: 96, d: 6, r: 1 };
back.push(S(k.slabOf(STRIP, 0, 0.6, P, 3), { tone: "lo", crease: "none" }));
const stripTicks = k.topTicks(STRIP.x + 4, STRIP.x + STRIP.w - 4, 4, 5, STRIP.y, 0.6, [1.8, 3.4], P);
back.push(Ln(stripTicks.minor, { tone: "lo" }), Ln(stripTicks.major, { tone: "mid" }));

// =====================================================================
// 2. 模组托盘与冷却板
// =====================================================================
slab("tray.cool", { x: -57.5, y: -29.5, w: 107, d: 61, r: 2 }, 0, 3, { tone: "lo", r: 2, steps: 3, inner: "" });
slab("tray.endL", { x: TRAY.x, y: TRAY.y, w: WALL, d: TRAY.d, r: 1.5 }, 0, 24, { tone: "mid", r: 1.5, steps: 3, inner: Ln(k.sideSeam({ x: TRAY.x, y: TRAY.y, w: WALL, d: TRAY.d, r: 1.5 }, 16, P, 3), { tone: "faint" }) });
slab("tray.endR", { x: TRAY.x + TRAY.w - WALL, y: TRAY.y, w: WALL, d: TRAY.d, r: 1.5 }, 0, 24, { tone: "mid", r: 1.5, steps: 3 });
slab("tray.back", { x: TRAY.x + WALL, y: TRAY.y, w: TRAY.w - 2 * WALL, d: WALL, r: 1.2 }, 0, 72, { tone: "mid", r: 1.2, steps: 3 });
slab("tray.front", { x: TRAY.x + WALL, y: TRAY.y + TRAY.d - WALL, w: TRAY.w - 2 * WALL, d: WALL, r: 1.2 }, 0, 14, { tone: "mid", r: 1.2, steps: 3 });
// 托盘前壁上的模块铭牌（三枛刻线代替文字）+ 四角螺钉
{
  const nm = { x: -22, y: 32, w: 26, d: 0.55, r: 0.5 };
  slab("tray.plate", nm, 2.4, 8, {
    tone: "lo", r: 0.5, steps: 2, owner: "tray.front",
    extra: Ln(path3([[-19, 32.55, 8], [1, 32.55, 8]]) + path3([[-19, 32.55, 6.2], [1, 32.55, 6.2]]) + path3([[-17, 32.55, 4.4], [-3, 32.55, 4.4]]), { tone: "mid", free: true })
      + Dots([[-20, 32.6, 9.4], [2, 32.6, 9.4], [-20, 32.6, 3.4], [2, 32.6, 3.4]].map(([x, y, z]) => at([x, y, z])), { size: 0.4, tone: "lo" }),
  });
}
// 冷却板接头（托盘前脸两个凸台：口上一道内环，不是一整块亮斑）
for (const px of [-46, 34]) {
  port(`tray.coolport${px}`, [px, 0, 8], "y", 1.9, 36, 38.4, { tone: "mid" });
  const ring = path3(Array.from({ length: 20 }, (_, i) => {
    const a = (i / 20) * 2 * Math.PI;
    return [px + 1.3 * Math.cos(a), 38.45, 8 + 1.3 * Math.sin(a)];
  }), true);
  R.items.find((it) => it.name === `tray.coolport${px}`).svg += Ln(ring, { tone: "hi" });
}
// 从控板 BMU：平贴在托盘左端壁外面上（真实模组里它就是装在端板上、采集每只电芯极柱电压与温度）
{
  box("bms.board", [-63.4, -14, 4], [-62, 14, 20], { tone: "mid", r: 0.6, steps: 2, owner: "tray.endL", bevel: 0.3 });
  // 三枛印字刻线 + 一排贴片元件 + 四角螺钉（都在板面 x = -63.45 上）
  const XF = -63.45;
  const lab = [10.5, 8.8, 7.1].map((z, i) => path3([[XF, -10 - i, z], [XF, 8 - i * 2, z]])).join("");
  const smd = Dots(Array.from({ length: 5 }, (_, i) => at([XF, -9 + i * 4.5, 12.6])), { size: 0.42, tone: "lo" });
  const scr = Dots([[-12, 5.6], [12, 5.6], [-12, 18.6], [12, 18.6]].map(([y, z]) => at([XF, y, z])), { size: 0.45, tone: "mid" });
  R.items.find((it) => it.name === "bms.board").svg += Ln(lab, { tone: "faint", free: true }) + smd + scr;
  for (const [cy0, cy1] of [[-11, -4], [3, 11]])
    box(`bms.conn${cy0}`, [-65.4, cy0, 14], [-63.4, cy1, 18], { tone: "hi", r: 0.5, steps: 2, owner: "bms.board", bevel: 0.3, extra: Dots(Array.from({ length: 4 }, (_, i) => at([-65.45, cy0 + 1.4 + i * 1.9, 16.4])), { size: 0.5, tone: "lo" }) });
}

// =====================================================================
// 2b. 极芯试样（工作台左前：与剖口电芯同一叠层，转 90° 面向观众、放大约 4 倍）
//     堆叠轴取 y（屏面 1.53 px/单位，x 只有 1.03），并让负极片向右错开 12，
//     这样离子通道左侧留出一条视线不被前板压住的带（向相机 Δx=-1.483Δy）
// =====================================================================
{
  const base = { x: -166, y: -18, w: 60, d: 34, r: 2 };
  slab("sam.base", base, 0, 4, { tone: "lo", r: 2, steps: 3, inner: Ln(k.sideSeam(base, 2.2, P, 3), { tone: "faint" }), extra: Dots(k.corners(base, 3.4).map(([x, y]) => at([x, y, 4])), { size: 0.6, tone: "mid" }) });
  // 后板 = 正极（亮边），前板 = 负极（暗边）；两片相隔 18 个单位的电解液通道
  const cat = { x: -162, y: -14, w: 34, d: 6, r: 0.4 };
  const ano = { x: -150, y: 4, w: 34, d: 6, r: 0.4 };
  slab("sam.cathode", cat, 4, 32, { tone: "hi", r: 0.4, steps: 2, inner: Ln(k.sideSeam(cat, 30, P, 2), { tone: "faint" }) });
  slab("sam.anode", ano, 4, 32, { tone: "mid", r: 0.4, steps: 2, inner: Ln(k.sideSeam(ano, 30, P, 2), { tone: "faint" }) });
  // 多孔涂层点阵：只落在各自面向观众的 +y 面上（画在极片自己的 svg 里，
  // 被前板挡住的那一段会由前板的实面自然盖掉，不需要人工算可见带）
  const coat = (xs, yf, zs, tone) => Dots(
    xs.flatMap((x, i) => zs.map((z, j) => at([x + (j % 2) * 1.4, yf, z + (i % 2) * 2.6]))),
    { size: 0.62, tone });
  R.items.find((it) => it.name === "sam.cathode").svg += coat([-161, -158, -155, -152], -7.5, [9, 15, 21, 27, 33], "lo");
  R.items.find((it) => it.name === "sam.anode").svg += coat([-147, -141.4, -135.8, -130.2, -124.6, -119], 10.5, [10, 17, 24, 31], "lo");
  // 夹具压板：各顶住一条极片的 −x 面（共面接触，不互穿）
  slab("sam.clamp-p", { x: -166, y: -14, w: 4, d: 6, r: 0.5 }, 4, 12, { tone: "mid", r: 0.5, steps: 2, owner: "sam.base" });
  slab("sam.clamp-n", { x: -154, y: 4, w: 4, d: 6, r: 0.5 }, 4, 12, { tone: "mid", r: 0.5, steps: 2, owner: "sam.base" });
  // 隔膜：比极片重叠区向左多伸出 8 个单位（真实叠片就是如此，膜要包住负极边缘），
  // 伸出的那一段正好面向观众，离子那条带落在它上面，Li⁺ 看起来就是从膜孔里穿过
  const sep = { x: -158, y: -2.4, w: 30, d: 0.8, r: 0.2 };
  slab("sam.sep", sep, 4, 32, { tone: "hi", r: 0.2, steps: 2 });
  R.items.find((it) => it.name === "sam.sep").svg += Dots(
    [-156, -150, -144, -138, -134].flatMap((x, i) => [12, 20, 28].map((z, j) => at([x + (j % 2) * 1.6, -1.55, z + (i % 2) * 2.4]))),
    { size: 0.55, tone: "lo" });
  // 极耳柱（从两条极片顶面伸出，试样未接线：端子帽封住）
  for (const [nm, px, py, own] of [["p", -146, -11, "sam.cathode"], ["n", -134, 7, "sam.anode"]]) {
    post(`sam.post-${nm}`, px, py, 36, 42, 1.6, { tone: "hi", owner: own });
    put(`sam.cap-${nm}`, [px, py, 42.6], S(k.cylinder(px, py, 2.4, 42, 1.2, P, 20, 0.25), { tone: "hi", crease: "lo" }), [record(A.cylinder(px, py, 2.4, 42, 1.2, { name: `sam.cap-${nm}`, owner: `sam.post-${nm}` }))], { bias: 0.06 });
  }
}

// =====================================================================
// 3. 六只方壳电芯（0 号剖开）
// =====================================================================
const POST_L = (i) => cellX(i) + 3.5;   // 每只左 = +，右 = −（串联同朝向）
const POST_R = (i) => cellX(i) + 11.5;
const POST_Y = -8;
function cellCap(i, skipBody) {
  const cx = cellX(i);
  // 顶盖
  if (!skipBody) {
    slab(`cell${i}.body`, { x: cx, y: -28, w: CELL_W, d: 26, r: 0.8 }, 3, CELL_H - 3, { tone: "hi", r: 0.8, steps: 2, crease: "lo", bevel: 0.6, inner: Ln(k.sideSeam({ x: cx, y: -28, w: CELL_W, d: 26, r: 0.8 }, 42, P, 2), { tone: "faint" }) });
  }
  slab(`cell${i}.lid`, { x: cx + 0.8, y: -27.2, w: CELL_W - 1.6, d: 24.4, r: 0.6 }, 80, 2, { tone: "hi", crease: "lo" });
  // 防爆阀（后区）
  post(`cell${i}.vent`, cx + 7.5, -21, 82, 83.4, 3, { tone: "hi", steps: 24, bias: 0.08 });
  // 两极柱 + 帽
  for (const [px, tag] of [[POST_L(i), "p"], [POST_R(i), "n"]]) {
    post(`cell${i}.${tag}-post`, px, POST_Y, 82, 88, 1.9, { tone: "hi" });
    put(`cell${i}.${tag}-cap`, [px, POST_Y, 88.75], S(k.cylinder(px, POST_Y, 2.8, 88, 1.5, P, 24, 0.3), { tone: "hi", crease: "lo" }), [record(A.cylinder(px, POST_Y, 2.8, 88, 1.5, { name: `cell${i}.${tag}-cap` }))], { bias: 0.06 });
  }
}
for (let i = 1; i < CELLS; i++) cellCap(i);

// ---- 0 号剖开电芯：壳体四壁 + 底 + 顶盖 + 内部叠层 ----
{
  const cx = cellX(0); // -58..-43, y -28..-2, z 4..80，+y 前面板剖开
  const T = 1.4;
  slab("cell0.wall-back", { x: cx + T, y: -28, w: CELL_W - 2 * T, d: T, r: 0.4 }, 3, CELL_H - 3, { tone: "hi", r: 0.4, steps: 2 });
  // 近侧（−x）壁被剖掉只剩一段矮座：相机在 (−x, +y, +z)，整壁会挡死极片剖面，
  // 矮座的顶面就是壳壁的切断面（1.4 厚的铝壳断面）
  slab("cell0.wall-left", { x: cx, y: -28, w: T, d: 25.2, r: 0.4 }, 3, 17, { tone: "hi", r: 0.4, steps: 2 });
  slab("cell0.wall-right", { x: cx + CELL_W - T, y: -28, w: T, d: 25.2, r: 0.4 }, 3, CELL_H - 3, { tone: "hi", r: 0.4, steps: 2 });
  slab("cell0.floor", { x: cx + 1.8, y: -26.2, w: CELL_W - 3.6, d: 23.6, r: 0.4 }, 3, 1.2, { tone: "lo", r: 0.4, steps: 2 });
  slab("cell0.lid", { x: cx + 0.8, y: -27.2, w: CELL_W - 1.6, d: 24.4, r: 0.6 }, 80, 2, { tone: "hi", crease: "lo" });
  post("cell0.vent", cx + 7.5, -21, 82, 83.4, 3, { tone: "hi", steps: 24 });
  post("cell0.p-post", POST_L(0), POST_Y, 82, 88, 1.9, { tone: "hi" });
  put("cell0.p-cap", [POST_L(0), POST_Y, 88.75], S(k.cylinder(POST_L(0), POST_Y, 2.8, 88, 1.5, P, 24, 0.3), { tone: "hi", crease: "lo" }), [record(A.cylinder(POST_L(0), POST_Y, 2.8, 88, 1.5, { name: "cell0.p-cap" }))], { bias: 0.06 });
  post("cell0.n-post", POST_R(0), POST_Y, 82, 88, 1.9, { tone: "hi" });
  put("cell0.n-cap", [POST_R(0), POST_Y, 88.75], S(k.cylinder(POST_R(0), POST_Y, 2.8, 88, 1.5, P, 24, 0.3), { tone: "hi", crease: "lo" }), [record(A.cylinder(POST_R(0), POST_Y, 2.8, 88, 1.5, { name: "cell0.n-cap" }))], { bias: 0.06 });
  // 内壁底槽（绝缘托盘，极板坐在它上面）
  slab("cell0.sump", { x: cx + 1.4, y: -25.2, w: CELL_W - 2.8, d: 21.6, r: 0.4 }, 4.1, 1.1, { tone: "lo", r: 0.4, steps: 2, owner: "cell0.floor" });

  // 极板叠层顶到汇流轨，极柱坐顶盖（rail 78..80 与 lid 80..82 平齐相接）
  // 极板叠层（示意 3 片 C/A/C，实际数百片）：x 起 -55.4，厚 1.6，间距 4.8 → 两个 3.2 宽离子间隙
  // 剖面在 y = -16.5：前一半极芯被切掉，露出三条极片断面与两条通道（相机沿 +y 看进来）
  const plateY = [-25, -16.5];
  const PL = 1.6;
  for (let j = 0; j < 3; j++) {
    const px = -55.4 + 4.8 * j;
    const isC = j !== 1;
    const nm = isC ? `cell0.cathode${j === 0 ? 0 : 1}` : "cell0.anode0";
    slab(nm, { x: px, y: plateY[0], w: PL, d: plateY[1] - plateY[0], r: 0.25 }, 5.2, 70.8, { tone: isC ? "hi" : "lo", r: 0.25, steps: 2, crease: "lo" });
    // 极耳（板顶 → 轨底）：剖面以后的后区两条汇流轨都保留，前区的被切去
    const tabY = isC ? [-23.4, -21.6] : [-18.6, -16.8];
    slab(`${nm}.tab`, { x: px + 0.3, y: tabY[0], w: 1.0, d: tabY[1] - tabY[0], r: 0.2 }, 76, 2, { tone: isC ? "hi" : "mid", r: 0.2, steps: 2 });
  }
  // 隔膜：剖面平面上贴在各极片表面的薄层（立纹 + 膜孔点），Li+ 从它中间穿过
  {
    const faces = [-53.8, -50.6, -49.0, -45.8];
    const sepShape = record(A.box([-53.95, -16.5, 10], [-45.65, -16.35, 76], { name: "cell0.seps", owner: "cell0.anode0" }));
    put("cell0.seps", [-49.8, -16.42, 43],
      Ln(faces.map((sx) => path3([[sx, -16.42, 10], [sx, -16.42, 76]])).join(""), { tone: "faint" }) +
      Dots(faces.flatMap((sx) => Array.from({ length: 6 }, (_, i) => at([sx, -16.4, 15 + i * 10.5]))), { size: 0.32, tone: "lo" }),
      [sepShape], { bias: 0.3 });
  }
  // 极耳轨（都在后区，顶面与盖板底面平齐）：后 = +，前一条 = −
  slab("cell0.rail-p", { x: -56, y: -23.6, w: 11.2, d: 2, r: 0.5 }, 78, 2, { tone: "hi", r: 0.5, steps: 2 });
  slab("cell0.rail-n", { x: -56, y: -19.8, w: 11.2, d: 2, r: 0.5 }, 78, 2, { tone: "hi", r: 0.5, steps: 2 });
}

// 串联母线条（相邻 − 与 + 极柱帽之间）
for (let i = 0; i < CELLS - 1; i++) {
  const x0 = POST_R(i) - 2.6;
  const x1 = POST_L(i + 1) + 2.6;
  slab(`bus${i}`, { x: x0, y: -10.6, w: x1 - x0, d: 5.2, r: 0.8 }, 89.5, 1.5, { tone: "mid", r: 0.8, steps: 2, extra: Dots([at([POST_R(i), POST_Y, 91]), at([POST_L(i + 1), POST_Y, 91])], { size: 0.45 }) });
}
// 0 号左极柱（模组总 +）立柱 → 汇流带
slab("term.riser", RISER_L, RISER_L.z0, RISER_L.z1 - RISER_L.z0, { tone: "mid", r: 0.4, steps: 2 });
// − 桥条（5 号右极柱 → 端子块）
slab("term.bridge", BRIDGE, BRIDGE.z0, BRIDGE.z1 - BRIDGE.z0, { tone: "mid", r: 0.8, steps: 2, owner: "blk.body", extra: Dots([at([POST_R(5), POST_Y, 91]), at([BRIDGE.x + BRIDGE.w - 1.4, POST_Y, 91])], { size: 0.45 }) });

// =====================================================================
// 4. 右端：母线箱 PBD + 端子块
// =====================================================================
slab("pbd.body", PBD, PBD.z0, PBD.z1 - PBD.z0, { tone: "mid", r: 1.2, steps: 3, bevel: 0.8, inner: Ln(k.sideSeam(PBD, 58, P, 3), { tone: "faint" }) });
slab("pbd.cover", { x: PBD.x + 2.6, y: -20, w: 4.4, d: 6, r: 0.6 }, 66, 1.4, { tone: "hi", r: 0.6, steps: 2 });
slab("pbd.fuse", { x: 60.6, y: 2.4, w: 3, d: 3, r: 0.6 }, 66, 1.8, { tone: "hi", r: 0.6, steps: 2 });
slab("blk.body", BLK, BLK.z0, BLK.z1 - BLK.z0, { tone: "mid", r: 0.8, steps: 2, bevel: 0.5, inner: Ln(k.sideSeam(BLK, 80, P, 2), { tone: "faint" }), extra: Dots([at([55.8, -4.95, 84]), at([60.6, -4.95, 84])], { size: 0.45, tone: "hi" }) });
// 汇流带（模组总 + 到端子塔的跨接线）：坐端子块顶面，端子塔坐它
slab("blk.strap", STRAP, STRAP.z0, STRAP.z1 - STRAP.z0, { tone: "hi", r: 0.8, steps: 2, bevel: 0.3, owner: "blk.body" });
// 端子塔（+ 输出）与 − 端子块前脸元件
{
  const towerSlab = slab("blk.tower", { x: 56.4, y: -9.7, w: 4, d: 3.4, r: 0.6 }, 94.5, 3.7, { tone: "mid", r: 0.6, steps: 2, bevel: 0.4, extra: Dots([at([56.35, -9.4, 96.4]), at([56.35, -6.6, 96.4]), at([56.35, -8, 95.2]), at([56.35, -8, 97.6])], { size: 0.45, tone: "hi" }) });
  var towerPort = port("blk.towerport", [58.4, -6.3, 96.4], "y", 1.8, -6.3, -3.7, { tone: "hi", owner: "blk.tower", cut: towerSlab });
}
var blkPort = port("blk.port", [56, -5, 80], "y", 2.0, -5, -2.4, { tone: "hi", owner: "blk.body" });
for (const bx of [55.8, 60.6]) port(`blk.bolt${bx}`, [bx, -5, 70], "y", 0.7, -5, -3.6, { tone: "hi", owner: "blk.body" });
// PBD 状态灯（+y 可见面，随工作模式脉动）
for (const [lx, lz, tag] of [[57.4, 60, "a"], [60.6, 60, "b"]]) {
  port(`pbd.led${tag}`, [lx, 8, lz], "y", 0.95, 8, 10.4, { tone: "hi", owner: "pbd.body" });
}
// 驱动电路端口（PBD +y 面两枚，朝电机一侧）
var pbdPortA = port("pbd.port.a", [57, 8, 36], "y", 1.6, 8, 10.6, { tone: "hi", owner: "pbd.body" });
var pbdPortB = port("pbd.port.b", [61.5, 8, 52], "y", 1.6, 8, 10.6, { tone: "hi", owner: "pbd.body" });

// =====================================================================
// 5. 充电柜
// =====================================================================
// 侧面散热百叶（左 face x=120，法线 −x 可见）——直接作为柜壳上的刻线
const ventSvg = (() => {
  const slats = [];
  for (let s = 0; s < 4; s++) {
    const za = 26 + s * 7;
    slats.push(path3([[120, -58, za], [120, -42, za]], false) + path3([[120, -58, za], [120, -58, za + 2.6]]) + path3([[120, -42, za], [120, -42, za + 2.6]]) + path3([[120, -58, za + 2.6], [120, -42, za + 2.6]]));
  }
  return Ln(slats.join(""), { tone: "lo" });
})();
slab("chg.body", CHG, 0.15, CHG.h - 0.15, { tone: "mid", r: 1.6, steps: 4, bevel: 1, extra: ventSvg });
slab("chg.skirt", { x: CHG.x, y: CHG.y, w: CHG.w, d: CHG.d, r: 2 }, 0, 4.5, { tone: "lo", r: 2, steps: 4, owner: "chg.body" });
slab("chg.top", { x: CHG.x + 1.2, y: CHG.y + 1.2, w: CHG.w - 2.4, d: CHG.d - 2.4, r: 1.2 }, CHG.h, 1.6, { tone: "hi", r: 1.2, steps: 3 });
// 提手
for (const hx of [CHG.x + 8, CHG.x + CHG.w - 8]) post(`chg.standoff${hx}`, hx, -50, CHG.h + 1.6, CHG.h + 5.4, 1.3, { tone: "mid" });
slab("chg.handle", { x: CHG.x + 6, y: -51.3, w: CHG.w - 12, d: 2.6, r: 1.2 }, CHG.h + 5.4, 2, { tone: "mid", r: 1.2, steps: 2, bevel: 0.4 });
// 铭牌（凸出的薄板 + 三枛刻线，代替文字）
{
  const zc = 96;
  slab("chg.plate", { x: CHG.x + 9, y: -34, w: 18, d: 0.55, r: 0.5 }, zc, 9, {
    tone: "lo", r: 0.5, steps: 2,
    extra: Ln(path3([[CHG.x + 11, -33.45, zc + 6.4], [CHG.x + 25, -33.45, zc + 6.4]]) + path3([[CHG.x + 11, -33.45, zc + 4.6], [CHG.x + 25, -33.45, zc + 4.6]]) + path3([[CHG.x + 12.5, -33.45, zc + 2.8], [CHG.x + 23.5, -33.45, zc + 2.8]]), { tone: "mid", free: true }),
  });
}
// 屏幕玻璃板（贴在前脸的深色面板 + 三条刻度线）
{
  slab("chg.glass", { x: 125.5, y: -34, w: 25, d: 0.55, r: 0.5 }, 70.5, 14.5, {
    tone: "lo", r: 0.5, steps: 2, bevel: 0.3,
    extra: Ln(path3([[128, -33.45, 82], [148.5, -33.45, 82]]) + path3([[128, -33.45, 78.4], [144, -33.45, 78.4]]) + path3([[128, -33.45, 74.8], [146.5, -33.45, 74.8]]), { tone: "mid", free: true }),
  });
}
// SOC 五格（前脸竖排，data-soc 由 live 点亮）
{
  const segs = [];
  const socSvg = [];
  for (let s = 0; s < 5; s++) {
    const za = 42 + s * 5.2;
    segs.push({ y: -33.55, z: [za, za + 4.2], x: [141.5, 147.5] });
    const q = path3([[141.5, -33.55, za], [147.5, -33.55, za], [147.5, -33.55, za + 4.2], [141.5, -33.55, za + 4.2]], true);
    socSvg.push(`<path class="lib-soc" data-soc="${s}" d="${q}"/>`);
  }
  const socShape = record(A.box([140.6, -34.05, 41.2], [148.4, -33.5, 68], { name: "chg.socbar", owner: "chg.body" }));
  put("chg.socbar", [144.5, -33.5, 59.4], Ln(path3([[140.6, -33.55, 41.2], [148.4, -33.55, 41.2], [148.4, -33.55, 68], [140.6, -33.55, 68]], true), { tone: "lo" }) + socSvg.join(""), [socShape], { bias: 0.3 });
}
// 充电柜电缆端口（前脸下部两枚，朝母线箱一侧；DC 输出端子）
const chgBodyShape = R.items.find((it) => it.name === "chg.body").shapes[0];
var chgPort1 = port("chg.port1", [126, -34, 90], "y", 2.1, -34, -31.4, { tone: "hi", owner: "chg.body", cut: chgBodyShape });
var chgPort2 = port("chg.port2", [135, -34, 90], "y", 2.1, -34, -31.4, { tone: "hi", owner: "chg.body", cut: chgBodyShape });
//  knurled 调钮（前面板，面向观众，沿 +y 轴凸出；滚花与指针刻线属于钮本身）
{
  const F = G.frameOf([127.5, -34, 26], [0, 1, 0], [1, 0, 0], [0, 0, 1]);
  turned("chg.knob", F, [[0, 4.6], [2.6, 4.6], [2.6, 3.9], [0, 3.9]], {
    tone: "mid", bevel: 0.3,
    extra: k.fadedSvg(G.ribsOf(F, 0.2, 2.4, 4.6, 22, P, { fade: [0.1, 0.5] }), { tone: "lo" })
      + Ln(path3([[127.5, -31.35, 26], [127.5, -31.35, 28.8]]), { tone: "hi", free: "end" }),
  });
}

// =====================================================================
// 6. 驱动电机
// =====================================================================
{
  const F = frameY([MOTOR.cx, MOTOR.cz]);
  turned("mot.bell0", F, [[2, 16], [2, 18.6], [4, 18.6], [4, 18]], { tone: "mid" });
  slab("mot.skid", { x: 99, y: 6, w: 24, d: 30, r: 1 }, 0, 4, {
    tone: "lo", r: 1, steps: 3,
    inner: Ln(k.planOutline(k.insetPlan({ x: 99, y: 6, w: 24, d: 30, r: 1 }, 2.5), 4, P, 3), { tone: "faint" }),
    extra: Dots([[102.5, 9.5], [119.5, 9.5], [102.5, 32.5], [119.5, 32.5]].map(([sx, sy]) => at([sx, sy, 4])), { size: 0.5, tone: "lo" }),
  });
  // 散热筋（机身表面立纹，仅可见侧成组渐隐）+ 后端吊环：都是机身上的细节
  // seams:true 让每根筋的两端落在机身两端的环线上，而不是停在裸面中间
  const ribs = G.ribsOf(F, 6, 38, 18.05, 26, P, { fade: [0.1, 0.5], seams: true });
  const eyeSvg = Ln(k.ring(MOTOR.cx, 8, 2.4, 41.5, P, 16) + path3([[MOTOR.cx - 0.5, 8, 38], [MOTOR.cx - 0.5, 8, 41.5]]) + path3([[MOTOR.cx + 0.5, 8, 38], [MOTOR.cx + 0.5, 8, 41.5]]), { tone: "lo" });
  const body = turned("mot.body", F, [[4, 18], [40, 18]], { tone: "mid", extra: k.fadedSvg(ribs, { tone: "lo" }) + eyeSvg });
  turned("mot.bell1", F, [[40, 18], [40, 19], [42, 19], [42, 16]], { tone: "mid" });
  turned("mot.cap", F, [[42, 16], [42.8, 16]], { tone: "hi" });
  turned("mot.hub", F, [[42.8, 3], [45.2, 3]], { tone: "hi" });
  turned("mot.nut", F, [[45.2, 2.4], [46.2, 2.4]], { tone: "hi", steps: 6 });
  turned("mot.guard", F, [[46.2, 10.6], [46.2, 11.8], [47.2, 11.8], [47.2, 10.6]], { tone: "mid" });
  // 接线盒（顶面在机身之上，−x 侧面两枚电缆入口，朝母线箱一侧）
  const boxShape = slab("mot.box", MBOX, MBOX.z0, MBOX.z1 - MBOX.z0, { tone: "mid", r: 0.8, steps: 2, bevel: 0.5, inner: Ln(k.sideSeam(MBOX, 49.5, P, 2), { tone: "faint" }) });
  var gland1 = portX("mot.gland1", [104, 30, 46], 1.5, 101.4, 104, { tone: "mid", owner: "mot.box", cut: boxShape });
  var gland2 = portX("mot.gland2", [104, 23, 53], 1.5, 101.4, 104, { tone: "mid", owner: "mot.box", cut: boxShape });
}

// =====================================================================
// 7. 仪表架（两只表盘）与模式旋钮
// =====================================================================
{
  slab("gauge.base", GAUGE.base, 0, 3, { tone: "mid", r: 2, steps: 3, extra: Dots(k.corners(GAUGE.base, 2.4).map(([x, y]) => at([x, y, 3])), { size: 0.4, tone: "lo" }) });
  for (const [px, py] of GAUGE.post) {
    post(`gauge.post${px}`, px, py, 3, GAUGE.z, 2, { tone: "mid", inner: Ln(k.sideArc(px, py, 2, 14, P, 14), { tone: "faint" }) + Ln(k.sideArc(px, py, 2, 44, P, 14), { tone: "faint" }) });
  }
  // 表体：筒壳 / 前缘环 / 面盘（同 dial-indicator），指针装在面盘上方
  for (const [g, tag] of [[G_V, "volt"], [G_A, "amp"]]) {
    const [gx, gy] = g.at;
    const z = g.z;
    const top = z + 0.4;
    const Fz = G.frameOf([gx, gy, 0], [0, 0, 1], [1, 0, 0], [0, 1, 0]);
    post(`gauge.${tag}.case`, gx, gy, GAUGE.z, top, GAUGE.R - 0.4, { tone: "mid", steps: 40, bevel: 0.5 });
    const bezelShape = record(A.ring(Fz, z + 0.25, top, GAUGE.R - 1.1, GAUGE.R - 0.2, { name: `gauge.${tag}.bezel`, owner: `gauge.${tag}.case` }));
    put(`gauge.${tag}.bezel`, [gx, gy, z], S({ fill: k.ring(gx, gy, GAUGE.R - 0.6, z + 0.25, P, 40), outline: k.ring(gx, gy, GAUGE.R - 0.2, z, P, 44) + k.ring(gx, gy, GAUGE.R - 1, z + 0.25, P, 44), crease: "", top: "", shades: ["", "", "", ""], seamless: false, flat: true }, { tone: "hi", flat: true }), [bezelShape], { bias: 0.1 });
    const ticks = k.radialTicks(gx, gy, GAUGE.R - 1.8, 48, 6, z + 0.3, [1.1, 2.4], P, -Math.PI * 0.75, Math.PI * 1.5);
    // 面盘是一块贴壳口的薄盘；刻度与零位环都印在它上面
    const faceShape = record(A.disc(Fz, top - 0.1, top, GAUGE.R - 0.6, { name: `gauge.${tag}.face`, owner: `gauge.${tag}.case` }));
    const zero = tag === "volt" ? Ln(k.ring(gx, gy, GAUGE.R - 4.2, z + 0.4, P, 20), { tone: "faint" }) : "";
    put(`gauge.${tag}.ticks`, [gx, gy, z + 0.3], Ln(ticks.minor, { tone: "lo" }) + Ln(ticks.major, { tone: "mid" }) + zero + Ln(k.ring(gx, gy, 1.2, z + 0.4, P, 12), { tone: "hi" }), [faceShape], { bias: 0.2 });
  }
  {
    const p = [G_A.at[0] + 6.6, G_A.at[1] + 6.6, G_A.z + 0.8];
    const linkShape = record(A.ball(p, 0.4, { name: "gauge.amp.link", owner: "gauge.amp.case" }));
    put("gauge.amp.link", p, Dots([at(p)], { size: 0.55, tone: "hi" }), [linkShape], { bias: 0.22 });
  }
}
{
  const [kx, ky] = KNOB.at;
  post("knob.skirt", kx, ky, 0, 1.6, 8.6, { tone: "mid", steps: 36, bias: 0 });
  post("knob.body", kx, ky, 1.6, 6, 6.6, { tone: "mid", steps: 36, bevel: 0.4, inner: Ln(k.knurl(kx, ky, 6.6, 1.8, 5.8, 30, P), { tone: "lo" }) });
  const hubAt = [kx, ky, 6.2];
  const hubShape = record(A.ball(hubAt, 0.45, { name: "knob.hub", owner: "knob.body" }));
  put("knob.hub", hubAt, Dots([at(hubAt)], { size: 0.5, tone: "hi" }), [hubShape], { bias: 0.2 });
}

// =====================================================================
// 8. 高压电缆：充电回路 2 条 + 驱动回路 2 条（全部汇于右端）
// =====================================================================
const RT = {};
// 每根电缆的两端都沿端口轴线直线引入（tip 在 mouth 平面上，首/末控制点落在轴线上）。
// 相机常量：+x 屏角 −33.9°、+y +17.0°、+z −90°，视线 V=(−0.739,0.498,0.454)。
// 样条某点切线一旦接近 ±V，投影就出现尖点（屏曲率半径→0，audit 报 folds/self-overlap），
// 而 ±V 正好是 (+x,−y,−z) 的组合：所以 +x 的长行程要么保持平直，要么配 +y/+z 分量抵消，
// 转弯放在 y–z 竖直面里做；路线用 routecheck.mjs 预筛（屏半径 ≥ 2×管宽）。
// 高压线的中段按重力下垂（z 从端口高度落到 ~78 再回到 90），而不是向右侧扫出大弧。
RT["hv.plus"] = cable("hv.plus", spline([[58.4, -3.7, 96.4], [58.4, 14, 96.4], [64, 22, 90], [80, 24, 80], [98, 22, 78], [114, 18, 84], [126, 12, 90], [126, -12, 90], [126, -31.4, 90]]), 1.1, { shells: [towerPort, chgPort1], touch: ["blk.towerport", "chg.*"], maxLength: 10, smooth: true });
RT["hv.minus"] = cable("hv.minus", spline([[56, -2.4, 80], [56, 16, 80], [64, 26, 76], [82, 30, 70], [100, 28, 72], [118, 22, 80], [135, 14, 90], [135, -12, 90], [135, -31.4, 90]]), 1.1, { shells: [blkPort, chgPort2], touch: ["blk.port", "chg.*"], maxLength: 10, smooth: true });
RT["drive.a"] = cable("drive.a", spline([[57, 10.6, 36], [57, 20, 36], [59, 26, 37], [68, 26, 39], [80, 26, 41], [90, 27, 43], [96, 30, 46], [101.4, 30, 46]]), 1.0, { shells: [pbdPortA, gland1], touch: ["pbd.port.a", "mot.*"], maxLength: 9, smooth: true });
RT["drive.b"] = cable("drive.b", spline([[61.5, 10.6, 52], [61.5, 22, 52], [63, 30, 52], [70, 30, 52], [82, 27, 52], [92, 24, 52], [98, 23, 53], [101.4, 23, 53]]), 1.0, { shells: [pbdPortB, gland2], touch: ["pbd.port.b", "mot.*"], maxLength: 9, smooth: true });

// =====================================================================
// 9. 真实深度 settle、预留槽与页面输出
// =====================================================================
A.settle(R, P);
R.items.sort((a, b) => a.key - b.key);
const indexOf = (name) => R.items.findIndex((item) => item.name === name);
const slots = new Map();
slots.set(indexOf("cell0.seps"), `<g data-part="ions"></g>`);
const samSep = indexOf("sam.sep");
if (samSep < 0) throw new Error("缺少 sam.sep：试样离子槽无处安放");
slots.set(samSep, `<g data-part="ions2"></g>`);
slots.set(Math.max(indexOf("mot.nut"), indexOf("mot.bell1")), `<g data-part="fan"></g>`);
slots.set(Math.max(indexOf("gauge.volt.ticks"), indexOf("gauge.amp.ticks")), `<g data-part="needles"></g>`);
slots.set(indexOf("knob.hub"), `<g data-part="knob-mark"></g>`);
slots.set(Math.max(indexOf("pbd.leda"), indexOf("pbd.ledb")), `<g data-part="leds"></g>`);
const groups = R.items.map((item, index) => `<g class="it" data-name="${item.name}"${item.attrs ?? ""}>${item.svg}</g>${slots.get(index) ?? ""}`).join("");

const LABEL =
  "工作台上六只方壳电芯串联成模组，左前一只被剖开（近侧壳壁与极芯前半切除），露出三条极片断面与两条离子通道；台板左前另夹一只放大约四倍、转 90° 面向观众的极芯试样（正极片—隔膜—负极片）；托盘左端壁上贴从控板，右端母线箱与端子块经四条高压电缆分别挂接右后的直流充电柜与右前的驱动电机（带风扇）；仪表架上两只表盘读电压与电流，左前一只滚花旋钮选充电/放电。";
const svg = k.figureSvg({ width: WIDTH, height: HEIGHT, label: LABEL, body: [...back, groups, `<g data-part="electrons"></g>`] });

const ptsOf = (name) => R.routes.find((r) => r.name === name).points.map((p) => at(p).map(f2));
const DATA = {
  P,
  cables: Object.fromEntries(Object.keys(RT).map((n) => [n, ptsOf(n)])),
  ions: { gaps: [{ a: -53.8, b: -50.6, from: "a" }, { a: -49.0, b: -45.8, from: "b" }], y: [-15.9], z: [14, 70], n: 4,
    // 试样：沿 y（堆叠轴）在通道里往返， lanes = [x, z]
    sample: { a: -7.2, b: 3.2, r: 1.9, lanes: [[-156, 11], [-152, 17], [-155, 23], [-150.5, 29], [-153.5, 34], [-157, 27]] } },
  fan: { cx: 111, cz: 22, y0: 46.3, y1: 46.9, r0: 2.6, r1: 9.6, n: 5 },
  gauges: {
    volt: { o: [12, 44, 60.95], r: 8, min: 2.6, max: 4.4 },
    amp: { o: [36, 44, 60.95], r: 8.4, min: -110, max: 110 },
  },
  knob: { o: [KNOB.at[0], KNOB.at[1], 6.15], r: 5.4 },
  leds: [[57.4, 10.35, 60], [60.6, 10.35, 60]],
  cells: CELL.cells,
};

const modelScript = readFileSync(join(HERE, "model.mjs"), "utf8").replace(/^export /gm, "");
const liveScript = readFileSync(join(HERE, "live.js"), "utf8").replace("__DATA__", JSON.stringify(DATA));
const CSS = `.lib-soc{fill:none;stroke:var(--anatomy-lo);stroke-width:.7px}.lib-soc.on{fill:var(--anatomy-lit);stroke:var(--anatomy-lit)}`;

const bodyHtml =
  `<style>${CSS}</style>` +
  k.plateHtml({
    fig: "图 1",
    title: "锂电池台 · 充电与放电",
    hint: "空格/点击：切换充放电 · ← 充电 · → 放电",
    readout: "恒流充电 · 18% · 21.9V · +50A",
    keys: [
      { mark: "lit", label: "活动粒子：Li⁺ 在极片间隙与膜孔里穿梭，e⁻ 沿电缆反向流动" },
      { mark: "mid", label: "左前试样＝极芯放大剖面：亮边为正极片、暗边为负极片，中间虚点片为隔膜" },
    ],
    caption:
      "六只 100 Ah 方壳电芯串联成约 22 V 模组（台板上的叠层为示意，实际数百片）。充电：充电柜以 0.5C（50 A）恒流注入（CC），单体端压升至 4.20 V 后转恒压（CV），电流按 I=(4.20−OCV)/r 自然衰减至 0.02C 截止——这就是恒流-恒压曲线。放电：模组经母线箱向驱动电机输出 1C（100 A），至 2.75 V 截止。台板左前的试样把同一叠层放大四倍并转 90° 面向观众：充电时 Li⁺ 从正极锂金属氧化物晶格里脱出，经电解液穿过隔膜微孔，嵌入负极石墨层间，放电时反向；电子只能走外电路，所以与离子方向相反。托盘端壁上的从控板逐芯采压测温，满充或欠压时由母线箱里的接触器断回路；电流表指针过零，就是充与放的分界。",
    body: `<div class="iso-stage" tabindex="0" role="group" aria-label="锂电池台。空格或点击切换充电/放电；左箭头充电，右箭头放电。">${svg}<span style="position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%)" role="status" aria-live="polite" data-status></span></div>`,
  });

const page = k.pageHtml({ title: "锂电池台 · 充电与放电", theme: THEME, body: bodyHtml, script: kitScript() + modelScript + liveScript, width: 650 });
const outName = THEME === "light" ? "liion-bench-light.html" : "liion-bench.html";
writeFileSync(join(HERE, outName), page);
console.log("wrote", outName, `${(page.length / 1024).toFixed(0)} KB`, `${R.items.length} items`, `scale ${KS.toFixed(3)}`, `${CABLES.length} cables`);

A.auditOrExit(R, P, {});
