// 电缆路线体检：把样条投影到屏面，找出曲率半径小于管宽的位置（audit 的 folds/self 根因）
// 同时报告每段切线与视线的夹角（|dot| 越大越“顶镜头”，转弯会被压成尖点）
import * as k from "file:///C:/Users/joezxh/.qoder/skills/anatomy/kit/iso-kit.mjs";
import * as G from "file:///C:/Users/joezxh/.qoder/skills/anatomy/kit/lathe.mjs";

const WIDTH = 640, HEIGHT = 560, AZIMUTH = 146, ELEVATION = 27;
const PLATE = { x: -172, y: -74, w: 344, d: 148, r: 10 };
const PLATE_H = 10, FOOT_H = 6;
const CHG = { x: 120, y: -66, w: 38, d: 32, h: 106 };
const STRAP = { x: -55.7, y: -9.9, w: 117.2, d: 3.8, z0: 93.5, z1: 94.7 };
const MOTOR = { cx: 111, cz: 22, r: 18 };
const GAUGE = { post: [[12, 44], [36, 44]], z: 56, R: 11, H: 4.5 };
const KNOB = { at: [-80, 46] };
const G_A = { at: [36, 44], z: GAUGE.z + GAUGE.H };
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
export const spline = (pts, per = 14) => {
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
};
import { readFileSync } from "node:fs";
const arg = process.argv[2] ?? "routes.json";
const ROUTES = JSON.parse(arg.trim().startsWith("{") ? arg : readFileSync(arg, "utf8"));
for (const [name, { pts, r }] of Object.entries(ROUTES)) {
  const route = spline(pts);
  const q = route.map((p) => k.iso(p, P));
  const width = r * G.scaleOf(P);
  let worst = null, stall = null;
  for (let i = 2; i < route.length - 2; i++) {
    const a = [q[i][0] - q[i - 1][0], q[i][1] - q[i - 1][1]];
    const b = [q[i + 1][0] - q[i][0], q[i + 1][1] - q[i][1]];
    const c = [q[i + 1][0] - q[i - 1][0], q[i + 1][1] - q[i - 1][1]];
    const la = Math.hypot(...a), lb = Math.hypot(...b), lc = Math.hypot(...c);
    const area = Math.abs(a[0] * b[1] - a[1] * b[0]) / 2;
    const radius = area > 1e-9 ? (la * lb * lc) / (4 * area) : Infinity;
    if (!worst || radius < worst.radius) worst = { radius, at: route[i], la, lb };
    const t = G.unit3(G.sub3(route[Math.min(i + 1, route.length - 1)], route[Math.max(i - 1, 0)]));
    const cos = Math.abs(G.dot3(t, V));
    if (!stall || cos > stall.cos) stall = { cos, at: route[i] };
  }
  console.log(name.padEnd(9), "min screen radius", worst.radius.toFixed(2), "px / width", width.toFixed(2),
    "| worst tangent-vs-view cos", stall.cos.toFixed(3), "at", stall.at.map((x) => x.toFixed(1)).join(","),
    "| radius dip at", worst.at.map((x) => x.toFixed(1)).join(","));
}
