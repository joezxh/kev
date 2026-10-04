"""危急值复核记录生成器 —— 双尺寸主力场景。

标签完全由 PANELS 的阈值表派生，标注零漂移：同一个数值永远得到同一个标签。阈值口径与
docs/medical/specs/critical-value.json 的 guidance 必须逐项一致（以本文件为权威判据）。

最小对（minimal pairs）按构造成对生成：同一份报告只有一个测量值不同、恰好跨过危急值边界，标签必然翻转。
这教会模型决策取决于哪个字段，而不是学到捷径特征。

用法::

    python3 docs/medical/generators/gen_critical_value.py --n 787 --out data/cv.jsonl --seed 0
"""
import random
import sys

from common import boundary_value, base_parser, labelled, load_spec, split_data, write_records

SCENARIO = "critical-value"
NONE_ITEM = "none"
NO_NOTIFY = 3  # notify_within 第 4 档：全部项目正常

# (项目短名, 单位, 正常下界, 正常上界, 危急下界, 危急上界, 默认通知档位)
# 通知档位 0=立即(15min) 1=1小时内 2=当日内 3=无需通知。危急下界或上界为 None 表示该侧不设危急值。
PANELS = [
    ("K+", "mmol/L", 3.5, 5.3, 2.8, 6.2, 1),
    ("Na+", "mmol/L", 137, 147, 120.0, 160.0, 0),
    ("GLU", "mmol/L", 3.9, 6.1, 2.8, 16.7, 0),
    ("Cr", "umol/L", 44, 106, None, 442.0, 1),
    ("pH", "", 7.35, 7.45, 7.20, 7.60, 0),
    ("Hb", "g/L", 115, 175, 50.0, 200.0, 1),
    ("PLT", "x10^9/L", 125, 350, 30.0, 1000.0, 1),
    ("WBC", "x10^9/L", 3.5, 9.5, 1.5, 30.0, 2),
    ("cTn", "ng/mL", 0.0, 0.04, None, 0.04, 0),
    ("D-Dimer", "mg/L FEU", 0.0, 0.5, None, 5.0, 2),
]

# 立即（15 分钟）通知：(项目, 方向, 阈值)。命中即 notify_within=0。
# 只有「危急界值与立即阈值不同侧且更极端」的项目才可能落在 1 小时档，见 TIER_WINDOWS。
IMMEDIATE = [
    ("K+", "high", 6.5), ("Na+", "high", 160.0), ("Na+", "low", 120.0),
    ("pH", "low", 7.20), ("GLU", "high", 16.7), ("GLU", "low", 2.8),
    ("cTn", "high", 0.04), ("Hb", "low", 50.0),
]
# 1 小时内：(项目, 方向, 下阈值, 上阈值) —— 仍属危急（已越过危急界值）但未达立即档。
# 注意：这里只列真正「既危急又未达立即」的单侧区间。曾经误列的 K+ 低侧 2.8-3.0、PLT 30-50、
# Hb 50-70 都已被移除，因为它们在危急界值之内（Hb>50、PLT>30 并非危急），写进去会让标签与数值矛盾。
WITHIN_1H = [
    ("K+", "high", 6.2, 6.5), ("Cr", "high", 442.0, 600.0),
]

CONTEXTS = [
    "胸闷 3 天，血压 168/95 mmHg，既往 2 型糖尿病",
    "体检发现血钾升高，无明显不适",
    "慢性肾病随访，本次复查",
    "上腹绞痛伴恶心 6 小时",
    "术前常规筛查",
    "发热 3 天，抗感染治疗中",
    "胸骨后压榨样疼痛 2 小时，含服硝酸酯后缓解",
    "心悸、乏力 1 周",
    "妊娠 34 周产检",
    "移植术后第 3 天",
]
PATIENTS = ["male 67", "female 58", "male 45", "female 72", "female 29", "male 8", "female 66", "male 3"]


def outside(panel, value):
    """Whether one measurement falls outside its critical range (a None bound means no critical limit that side)."""
    _, _, _, _, low, high, _ = panel
    if low is not None and value < low:
        return True
    return high is not None and value > high


def notify_tier(item, value):
    """0 = 立即, 1 = 1 小时, 2 = 2 小时, 3 = 当日内. The immediate and 1h rules override the panel default."""
    for name, direction, limit in IMMEDIATE:
        if name == item and ((direction == "high" and value >= limit) or (direction == "low" and value <= limit)):
            return 0
    for name, direction, low, high in WITHIN_1H:
        if name == item:
            if direction == "low" and low <= value < high:
                return 1
            if direction == "high" and low < value <= high:
                return 1
    return next(panel[6] for panel in PANELS if panel[0] == item)


def decimals_for(name):
    if name == "pH":
        return 2
    return 3 if name in ("cTn", "D-Dimer") else 1


def normal_value(rng, panel):
    """A measurement inside the reference range (cTn and D-Dimer are one-sided, so they stay under their limit)."""
    name, _, nlow, nhigh, clow, chigh, _ = panel
    decimals = decimals_for(name)
    if name == "cTn":
        return round(rng.uniform(0.0, chigh * 0.5), decimals)
    if name == "D-Dimer":
        return round(rng.uniform(0.0, chigh * 0.15), decimals)
    if nhigh <= nlow:
        return round(rng.uniform(nlow, nlow + 1.0), decimals)
    return boundary_value(rng, rng.uniform(nlow, nhigh), nlow, nhigh, decimals=decimals)


def critical_value(rng, panel):
    """A measurement just outside the critical bound, and sometimes past the immediate or 1h bound so the notify
    tier has something to separate rather than collapsing onto one value."""
    name, _, nlow, nhigh, clow, chigh, _ = panel
    decimals = decimals_for(name)
    high_side = chigh is not None and (clow is None or rng.random() < 0.5)
    if high_side:
        top = chigh * 1.7 if name in ("K+", "Hb", "PLT") else chigh + (chigh - nhigh + 0.2)
        return boundary_value(rng, chigh, nhigh, top, side=True, decimals=decimals)
    bottom = clow * 0.5 if name in ("K+", "WBC") else clow - (nlow - clow + 0.2)
    return boundary_value(rng, clow, bottom, nlow, side=False, decimals=decimals)


def crossed(rng, panel):
    """A value safely on the non-critical side of this panel's bound, for building a minimal pair."""
    name, _, nlow, nhigh, clow, chigh, _ = panel
    decimals = decimals_for(name)
    if chigh is not None and (clow is None or rng.random() < 0.5):
        return boundary_value(rng, chigh, nlow, chigh * 0.9, side=False, decimals=decimals)
    if clow is not None:
        return boundary_value(rng, clow, nlow * 0.5 if nlow > 0 else clow * 1.2, nhigh, side=True, decimals=decimals)
    return normal_value(rng, panel)


def format_measurement(panel, value, with_unit):
    unit = panel[1]
    return f"{value} {unit}".strip() if with_unit else str(value)


CATEGORIES = {
    "electrolyte": ["K+", "Na+"],
    "renal": ["Cr"],
    "glucose_gas": ["GLU", "pH"],
    "cbc": ["Hb", "PLT", "WBC"],
    "cardiac_coag": ["cTn", "D-Dimer"],
}
PANEL_CATEGORY = {name: cat for cat, names in CATEGORIES.items() for name in names}

# (通知档位, 项目) -> 能实现该档位的取值窗口。这是给临床专家 review 的单一事实来源：窗口端点来自
# IMMEDIATE / WITHIN_1H 与各项目危急界值，采样后仍会用 notify_tier() 复核，阈值改动不会静默产生错标。
TIER_WINDOWS = {
    (0, "K+"): [(6.5, 9.0)],
    (0, "Na+"): [(160.1, 175.0), (105.0, 119.9)],
    (0, "pH"): [(6.8, 7.19), (7.61, 7.9)],
    (0, "GLU"): [(16.7, 30.0), (1.5, 2.79)],
    (0, "cTn"): [(0.04, 0.4)],
    (0, "Hb"): [(30.0, 49.9)],
    (1, "K+"): [(6.21, 6.5)],
    (1, "Cr"): [(442.1, 900.0)],
    (1, "PLT"): [(5.0, 29.9), (1000.1, 1500.0)],
    (1, "Hb"): [(200.1, 260.0)],
    (2, "WBC"): [(30.1, 60.0), (0.3, 1.4)],
    (2, "D-Dimer"): [(5.1, 20.0)],
}
TIER_PANELS = {}
for (_tier, _name), _windows in TIER_WINDOWS.items():
    TIER_PANELS.setdefault(_tier, []).append(_name)
# 每个分类可以实现哪些档位 —— 规划时先按分类配额，再在该分类内部均匀挑档位。
CATEGORY_TIERS = {
    cat: sorted({tier for tier, names in TIER_PANELS.items() if any(PANEL_CATEGORY[n] == cat for n in names)})
    for cat in CATEGORIES
}
# 每个分类内部的档位配比。稀缺档位（当日内只有 WBC 与 D-Dimer 能实现）需要额外配额才能过 5% 下限，
# 所以配比写成显式数据而不是均匀分配 —— 均匀分配会让 notify_within=2 落在 5% 以下。
CATEGORY_TIER_SPLIT = {
    "renal": [(1, 1.0)],
    "glucose_gas": [(0, 1.0)],
    "electrolyte": [(0, 0.5), (1, 0.5)],
    "cardiac_coag": [(0, 0.5), (2, 0.5)],
    "cbc": [(0, 0.34), (1, 0.33), (2, 0.33)],
}


def decide(values, panels):
    """The four labels, derived from the threshold table alone -- the single source of truth.

    `values` maps panel name -> measured value. A report with no out-of-range value gets critical_item=none and
    notify_within=4 (无需通知), so a normal report is never forced onto a meaningless label. With several critical
    items the notification tier is the fastest one and critical_item is the category of that item.
    """
    hits = [(name, value) for name, value in values.items() if outside(panels[name], value)]
    if not hits:
        return {"is_critical": False, "notify_within": NO_NOTIFY, "critical_item": NONE_ITEM,
                "evidence_sufficient": True}
    fastest = min(notify_tier(name, value) for name, value in hits)
    triggering = next(name for name, value in hits if notify_tier(name, value) == fastest)
    return {"is_critical": True, "notify_within": fastest, "critical_item": PANEL_CATEGORY[triggering],
            "evidence_sufficient": True}


def make_record(rng, panels, values, with_unit, with_refs, dropped, context=None):
    """Assemble one labelled record. `dropped` names the element removed on purpose ("" for none)."""
    labels = decide(values, panels)
    labs = {name: format_measurement(panels[name], value, with_unit) for name, value in values.items()}
    state = {
        "patient": rng.choice(PATIENTS),
        "context": context or rng.choice(CONTEXTS),
        "labs": labs,
        "ref_ranges_included": with_refs,
        "missing_context": [dropped] if dropped else [],
    }
    soft = None
    if dropped:
        # Evidence removed on purpose: the honest answer is "cannot tell", so say so with a 50/50 target rather
        # than letting the model learn to guess from the remaining numbers.
        labels = {**labels, "evidence_sufficient": False}
        soft = {"is_critical": {"true": 0.5, "false": 0.5}}
    return labelled(load_spec(SCENARIO), state, labels, soft)


def realize_tier(rng, panel, tier):
    """A measurement for `panel` whose notification tier is exactly `tier`, or None if it cannot be realized.

    Candidates are drawn from the TIER_WINDOWS entry and then **verified** against notify_tier and outside, rather
    than trusting the arithmetic: verification is the authority, so editing a threshold cannot silently produce a
    record whose label disagrees with its measurement.
    """
    name = panel[0]
    windows = TIER_WINDOWS.get((tier, name))
    if not windows:
        return None
    low, high = rng.choice(windows)
    decimals = decimals_for(name)
    for _ in range(6):  # resample until the sampled value really lands in the tier
        value = round(rng.uniform(low, high), decimals)
        if outside(panel, value) and notify_tier(name, value) == tier:
            return value
    return None


def build(rng, target=None):
    """One record realizing `target`, plus a handle that :func:`pair_twin` can turn into a minimal pair.

    `target` is None (a normal report) or (tier, category) naming the notification tier and the critical-item
    category to realize. Driving generation from a target is what keeps every option above split_data's 5% floor:
    the label plan is drawn from a quota first, then a measurement that provokes exactly that label is built.
    Returns (None, None) when the target cannot be realized, so the caller can fall back to a normal report.
    """
    tier, category = target if target else (None, NONE_ITEM)
    if target:
        panels_for_category = [n for n in TIER_PANELS[tier] if PANEL_CATEGORY[n] == category]
    else:
        panels_for_category = [p[0] for p in PANELS]
    if not panels_for_category:
        return None, None
    name = rng.choice(panels_for_category)
    panel = next(p for p in PANELS if p[0] == name)

    chosen = {panel[0]: panel}
    for extra in rng.sample([p for p in PANELS if p[0] != name], rng.randint(2, 5)):
        chosen[extra[0]] = extra
    values = {n: normal_value(rng, p) for n, p in chosen.items()}

    if target:
        value = realize_tier(rng, panel, tier)
        if value is None:
            return None, None
        values[name] = value
        # Sometimes add a second critical item so the "fastest tier wins" rule has real evidence -- but only when it
        # is not faster than the target tier, otherwise the record would realize a different tier than planned and
        # the quota would drift (this is what kept notify_within=2 under the 5% floor).
        if rng.random() < 0.35:
            for other in rng.sample([n for n in chosen if not outside(chosen[n], values[n])],
                                    min(2, len(chosen))):
                value2 = critical_value(rng, chosen[other])
                if outside(chosen[other], value2) and notify_tier(other, value2) >= tier:
                    values[other] = value2
                    break

    with_unit, with_refs = True, True
    if rng.random() < 0.08:  # remove a decision-critical element
        if rng.random() < 0.5:
            with_unit = False
        else:
            with_refs = False
    dropped = "" if with_unit and with_refs else ("unit" if not with_unit else "reference_range")
    return make_record(rng, chosen, values, with_unit, with_refs, dropped), \
        {"name": name, "panels": chosen, "values": values, "dropped": dropped,
         "with_unit": with_unit, "with_refs": with_refs}


def pair_twin(rng, record, handle):
    """The minimal pair for `record`: a report whose only difference is that the triggering measurement sits just on
    the safe side of its bound, so is_critical flips to false and the category to none.

    Every other panel, the patient and the context are carried over unchanged, so the two states differ in exactly
    one measurement. Returns None when the record has nothing safely flippable, which keeps wrong pairs out.
    """
    if handle is None or handle["dropped"]:
        return None
    name, panel = handle["name"], handle["panels"][handle["name"]]
    safe = crossed(rng, panel)
    if outside(panel, safe):
        return None
    twin_values = {n: (safe if n == name else v) for n, v in handle["values"].items()}
    twin = make_record(rng, handle["panels"], twin_values, handle["with_unit"], handle["with_refs"],
                       handle["dropped"], context=record["state"]["context"])
    twin["state"]["patient"] = record["state"]["patient"]
    # Same rule common.minimal_pair enforces: a twin whose labels do not move teaches nothing, and a record can end
    # up here with a second critical item that keeps is_critical true, so the check has to be explicit here too.
    if not any(split_data.label_key(record["questions"][q]) != split_data.label_key(twin["questions"][q])
               for q in record["questions"]):
        return None
    return twin


def plan_targets(n, rng, critical_share):
    """The batch label plan: `critical_share` of records are critical, dealt out over the five critical-item
    categories and, inside each, over that category's tier split from CATEGORY_TIER_SPLIT. The remaining records are
    normal reports (critical_item=none, notify_within=3). Every option clears split_data's 5% floor at the default
    share; the floor for the categories alone is 6 options x 5% = 30%, so do not set --critical-share below 0.3.

    A balanced plan is what split_data.py asks for. It is deliberately NOT the clinical base rate -- critical values
    are ~1-3% of real reports -- so the served probabilities are conditioned on this balanced prior. Re-tune the
    thresholds from result.json on real traffic before go-live; see docs/medical/README.md.
    """
    categories = sorted(CATEGORIES)
    per_cat = max(1, int(n * critical_share) // len(categories))
    critical = []
    for cat in categories:
        split = CATEGORY_TIER_SPLIT[cat]
        for i in range(per_cat):
            tier = split[min(int(i * len(split) / per_cat), len(split) - 1)][0]
            critical.append((tier, cat))
    plan = [None] * max(0, n - len(critical)) + critical
    rng.shuffle(plan)
    return plan[:n]


def main(argv=None):
    parser = base_parser(__doc__.split("\n\n")[0])
    parser.add_argument("--critical-share", type=float, default=0.35,
                        help="share of records that are critical. The floor is 6 critical_item options x 5%% = 30%%, "
                             "so anything below ~0.3 will trip split_data's rare-label warning")
    parser.add_argument("--evidence-drop", type=float, default=0.08,
                        help="share of records with a decision-critical element removed (carries the soft target)")
    args = parser.parse_args(argv)
    rng = random.Random(args.seed)
    records, pairs, misses = [], 0, 0
    for target in plan_targets(args.n, rng, args.critical_share):
        want_pair = args.pairs > 0 and rng.random() < args.pairs
        record, handle = build(rng, target)
        if record is None:
            misses += 1
            record, handle = build(rng, None)
        if record is None:
            continue
        records.append(record)
        if want_pair and handle and target:
            twin = pair_twin(rng, record, handle)
            if twin is not None:
                records.append(twin)
                pairs += 1
    while len(records) < args.n:  # top up if realizations were rejected
        record, _ = build(rng, None)
        if record is None:
            break
        records.append(record)
    write_records(records[:args.n], args.out, args.seed, SCENARIO)
    print(f"minimal pairs built: {pairs} (each twin differs in one measurement and flips is_critical)")
    if misses:
        print(f"note: {misses} planned targets could not be realized and fell back to a normal report")
    return 0


if __name__ == "__main__":
    sys.exit(main())
