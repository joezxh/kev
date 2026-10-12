// 从成品页面里取投影 P，算若干世界点的屏面 CSS 坐标，用于决定特写取景框
import { readFileSync } from "node:fs";
import { iso } from "file:///C:/Users/joezxh/.qoder/skills/anatomy/kit/iso-kit.mjs";

const s = readFileSync("liion-bench.html", "utf8");
const i = s.indexOf('"P":');
const m = s.slice(i + 4).match(/^\{.*?\}/s) || s.slice(i + 4).match(/^\[[\s\S]*?\]/);
console.log("raw:", s.slice(i, i + 200));
const P = JSON.parse(m[0]);
const W = 650 / 640, H = 630.75 / 560;
const f = (p) => { const q = iso(p, P); return [Math.round(q[0] * W), Math.round(q[1] * H)]; };
for (const [tag, p] of Object.entries({
  plate_mid: [-50, -8, 40], sep: [-49.8, -7.95, 43], tab: [-55, -8, 79],
  cell1face: [-30, -2, 40], traywallL: [-58, 0, 40],
  sam_tl: [-166, -18, 36], sam_br: [-106, 16, 0], sam_chan: [-155, -2, 20], sam_ion_a: [-158, -7.2, 11], sam_ion_b: [-158, 3.2, 11], cathode0: [-55.4, -16, 40], anode: [-50.6, -16, 40],
  bms_c: [-63.4, 0, 12], bms_tl: [-65.4, -14, 20], bms_br: [-62, 14, 4], trayL_top: [-62, 0, 24],
})) console.log(tag.padEnd(10), f(p).join(","));
