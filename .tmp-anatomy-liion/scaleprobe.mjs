// 量一下真实屏面尺度：每个世界单位在卡片 CSS 像素里是多少
import { readFileSync } from "node:fs";
import { iso } from "file:///C:/Users/joezxh/.qoder/skills/anatomy/kit/iso-kit.mjs";

const s = readFileSync("liion-bench.html", "utf8");
const i = s.indexOf('"P":');
const P = JSON.parse(s.slice(i + 4).match(/^\{.*?\}/s)[0]);
const W = 650 / 640, H = 630.75 / 560;
const f = (p) => { const q = iso(p, P); return [q[0] * W, q[1] * H]; };
const o = f([0, 0, 0]);
const d = (a, b) => { const p = f(a), q = f(b); return [Math.round((q[0] - p[0]) * 100) / 100, Math.round((q[1] - p[1]) * 100) / 100]; };
console.log("per 10 units:  +x", d([0, 0, 0], [10, 0, 0]), " +y", d([0, 0, 0], [0, 10, 0]), " +z", d([0, 0, 0], [0, 0, 10]));
const c0 = f([-55.4, -16.5, 40]), c1 = f([-50.6, -16.5, 40]), c2 = f([-45.8, -16.5, 40]);
console.log("plate cut-face left edges on card:", c0.map(v => v.toFixed(1)).join(","), c1.map(v => v.toFixed(1)).join(","), c2.map(v => v.toFixed(1)).join(","));
console.log("gap travel (card px):", Math.round((f([-50.6, -16.5, 40])[0] - f([-53.8, -16.5, 40])[0]) * 100) / 100,
  "· 3-plate span:", Math.round((c2[0] - c0[0]) * 100) / 100, Math.round((c2[1] - c0[1]) * 100) / 100);
console.log("cell height (76 units) card px:", Math.round(iso([0, 0, 76], P)[1] * H - o[1]));
