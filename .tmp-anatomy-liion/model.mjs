// 锂电池台的物理模型：NMC-石墨方壳电芯（100 Ah 级），与真实数值一致。
// 充电：0.5C 恒流(CC)至单体端压 4.20 V，转 4.20 V 恒压(CV)，电流自然衰减至 0.02C 截止；
// 放电：1C 恒流至 2.75 V 截止。所有读数、指针、粒子速度、SOC 条都由本模块的同一状态驱动。

export const CELL = {
  ah: 100,          // 额定容量 Ah
  r: 0.0015,        // 等效内阻 Ω（100 A 时极化 0.15 V）
  v_charge: 4.2,    // CV 电压 / 满充电压
  c_charge: 0.5,    // 充电倍率 0.5C -> 50 A（CC 段）
  i_cut: 2,         // 充满截止电流 0.02C
  c_disp: 1.0,      // 放电倍率 1C -> 100 A
  v_low: 2.75,      // 放电截止电压
  cells: 6,         // 模块串联单体数
};

// 开路电压 OCV(SOC)：典型 NMC532-石墨半电池合成值
const OCV_PTS = [
  [0.0, 3.05], [0.02, 3.25], [0.05, 3.5], [0.1, 3.58], [0.2, 3.65], [0.3, 3.7],
  [0.4, 3.74], [0.5, 3.78], [0.6, 3.83], [0.7, 3.89], [0.8, 3.97], [0.9, 4.1], [1.0, 4.2],
];

export function ocv(soc) {
  const s = Math.min(1, Math.max(0, soc));
  for (let i = 1; i < OCV_PTS.length; i++) {
    if (s <= OCV_PTS[i][0]) {
      const [x0, y0] = OCV_PTS[i - 1];
      const [x1, y1] = OCV_PTS[i];
      return y0 + ((s - x0) / (x1 - x0)) * (y1 - y0);
    }
  }
  return 4.2;
}

export function cellVoltage(st) {
  return ocv(st.soc) + st.i * CELL.r; // i>0 充电（端压抬升），i<0 放电（压降）
}

export function makeState() {
  return { soc: 0.18, i: 0, mode: "charge", phase: "CC", full: false, empty: false, t: 0 };
}

// dt 为电池时间（秒）；TIME_SCALE 在页面里把真实 1 s 映射为 120 s 电池时间
export function step(st, dt) {
  st.t += dt;
  const C = CELL.ah * 3600; // 库仑
  if (st.mode === "charge") {
    st.empty = false;
    if (st.full) { st.i = 0; st.phase = "FULL"; return; }
    // CC 段：电流恒为 0.5C，直到端压触及 4.20 V；之后转 CV，电流 = (4.2 - OCV)/r
    const i_cc = CELL.c_charge * CELL.ah;
    if (st.phase !== "CV") {
      st.i = i_cc;
      if (ocv(st.soc) + st.i * CELL.r >= CELL.v_charge) st.phase = "CV";
    }
    if (st.phase === "CV") {
      st.i = Math.min(i_cc, Math.max(0, (CELL.v_charge - ocv(st.soc)) / CELL.r));
      if (st.i <= CELL.i_cut) { st.i = 0; st.full = true; st.phase = "FULL"; }
    }
  } else {
    st.full = false;
    if (st.empty) { st.i = 0; st.phase = "IDLE"; return; }
    st.phase = "1C";
    st.i = -CELL.c_disp * CELL.ah;
    if (ocv(st.soc) + st.i * CELL.r <= CELL.v_low) { st.i = 0; st.empty = true; }
  }
  st.soc = Math.min(1, Math.max(0, st.soc + (st.i * dt) / C));
}
