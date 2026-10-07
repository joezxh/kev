CREATE TABLE IF NOT EXISTS console_meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
  id            TEXT PRIMARY KEY,
  kind          TEXT NOT NULL,
  stage         TEXT NOT NULL,
  scenario      TEXT NOT NULL,
  title         TEXT NOT NULL,
  status        TEXT NOT NULL,
  request       TEXT NOT NULL,
  argv          TEXT NOT NULL,
  env_overlay   TEXT NOT NULL,
  cwd           TEXT NOT NULL,
  log_path      TEXT NOT NULL,
  artifacts_in  TEXT NOT NULL,
  artifacts_out TEXT NOT NULL,
  parent_id     TEXT REFERENCES jobs(id),
  attempt       INTEGER NOT NULL DEFAULT 1,
  exit_code     INTEGER,
  error         TEXT,
  created_at    TEXT NOT NULL,
  started_at    TEXT,
  finished_at   TEXT
);
CREATE INDEX IF NOT EXISTS jobs_status_idx   ON jobs(status);
CREATE INDEX IF NOT EXISTS jobs_scenario_idx ON jobs(scenario, created_at DESC);

CREATE TABLE IF NOT EXISTS artifacts (
  id         TEXT PRIMARY KEY,
  kind       TEXT NOT NULL,
  name       TEXT NOT NULL,
  path       TEXT NOT NULL,
  meta       TEXT NOT NULL,
  bytes      INTEGER,
  created_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS artifacts_kind_name ON artifacts(kind, name);

CREATE TABLE IF NOT EXISTS lineage (
  parent   TEXT NOT NULL,
  child    TEXT NOT NULL,
  relation TEXT NOT NULL,
  job_id   TEXT REFERENCES jobs(id),
  PRIMARY KEY (parent, child, relation)
);

CREATE TABLE IF NOT EXISTS events (
  id     BIGSERIAL PRIMARY KEY,
  job_id TEXT NOT NULL REFERENCES jobs(id),
  ts     TEXT NOT NULL,
  stream TEXT NOT NULL,
  line   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_job_idx ON events(job_id, id);

CREATE TABLE IF NOT EXISTS api_keys (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  key_hash TEXT NOT NULL UNIQUE,
  prefix TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  revoked_at TEXT
);
CREATE INDEX IF NOT EXISTS api_keys_hash_idx ON api_keys(key_hash);

CREATE TABLE IF NOT EXISTS usage_log (
  id BIGSERIAL PRIMARY KEY,
  key_id TEXT NOT NULL REFERENCES api_keys(id),
  endpoint TEXT NOT NULL,
  method TEXT NOT NULL,
  status INTEGER NOT NULL,
  input_tokens INTEGER NOT NULL DEFAULT 0,
  output_tokens INTEGER NOT NULL DEFAULT 0,
  latency_ms DOUBLE PRECISION NOT NULL,
  ts TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS usage_log_key_ts_idx ON usage_log(key_id, ts);
CREATE INDEX IF NOT EXISTS usage_log_ts_idx ON usage_log(ts);

CREATE TABLE IF NOT EXISTS distill_providers (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  base_url TEXT NOT NULL,
  model TEXT NOT NULL,
  daily_limit INTEGER NOT NULL DEFAULT 500000,
  key_count INTEGER NOT NULL DEFAULT 0,
  key_hints TEXT NOT NULL DEFAULT '[]',
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS distill_providers_active_idx ON distill_providers(active);

CREATE TABLE IF NOT EXISTS distill_usage (
  id BIGSERIAL PRIMARY KEY,
  job_id TEXT NOT NULL REFERENCES jobs(id),
  provider_id TEXT NOT NULL,
  key_hash TEXT NOT NULL,
  key_hint TEXT NOT NULL,
  model TEXT NOT NULL,
  base_url TEXT NOT NULL,
  day TEXT NOT NULL,
  tokens INTEGER NOT NULL DEFAULT 0,
  ts TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS distill_usage_ukd ON distill_usage(provider_id, key_hash, day);
CREATE INDEX IF NOT EXISTS distill_usage_job_idx ON distill_usage(job_id);
CREATE INDEX IF NOT EXISTS distill_usage_day_idx ON distill_usage(day);

CREATE TABLE IF NOT EXISTS scenario_domains (
  id         TEXT PRIMARY KEY,
  slug       TEXT NOT NULL UNIQUE,
  label_zh   TEXT NOT NULL,
  label_en   TEXT NOT NULL,
  sort       INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scenarios (
  id         TEXT PRIMARY KEY,
  domain_id  TEXT NOT NULL REFERENCES scenario_domains(id),
  slug       TEXT NOT NULL UNIQUE,
  label_zh   TEXT NOT NULL,
  label_en   TEXT NOT NULL,
  spec_path  TEXT NOT NULL,
  spec_json  TEXT,
  category   TEXT NOT NULL DEFAULT 'medical',
  sort       INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS scenarios_slug_idx   ON scenarios(slug);
CREATE INDEX IF NOT EXISTS scenarios_domain_idx ON scenarios(domain_id);

CREATE TABLE IF NOT EXISTS scenario_spec_history (
  id          TEXT PRIMARY KEY,
  scenario_id TEXT NOT NULL REFERENCES scenarios(id),
  spec_json   TEXT NOT NULL,
  created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS spec_history_scenario_idx ON scenario_spec_history(scenario_id, created_at DESC);

-- ---- 初始数据 ----
INSERT INTO console_meta (key, value) VALUES ('schema_version', '4') ON CONFLICT(key) DO NOTHING;
INSERT INTO scenario_domains (id, slug, label_zh, label_en, sort, created_at) VALUES ('medical', 'medical', '医疗', 'Medical', 0, '2026-01-01T00:00:00+00:00') ON CONFLICT(slug) DO NOTHING;
INSERT INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, spec_json, category, sort, created_at, updated_at) VALUES ('critical-value', 'medical', 'critical-value', '危急值', 'Critical Value', 'docs/medical/specs/critical-value.json', '{
  "name": "critical-value",
  "domain": "医院检验科与影像科报告复核。检验项目包括血钾、血钠、空腹血糖、肌酐、尿素氮、血气 pH、血红蛋白、血小板计数、白细胞计数、肌钙蛋白、D-二聚体。报告为中文，关键缩写与英文项目名混排（K+、Na+、GLU、Cr、pH、Hb、PLT、WBC、cTn、D-Dimer）。患者为门诊与住院混合，含成人、孕产妇与儿童。",
  "state": "一份已出具的检验或影像报告的结构化摘要：患者年龄性别、临床背景主诉（1 句）、检验项目名称与实测值（含单位）、是否含参考区间、以及报告是否遗漏了判读所需的患者信息（年龄/采样时间/单位）。不含医生结论。",
  "state_example": {
    "patient": "female 67",
    "context": "胸闷 3 天，血压 168/95 mmHg，既往 2 型糖尿病",
    "labs": {
      "K+": "2.9 mmol/L",
      "Na+": "141 mmol/L",
      "GLU": "9.8 mmol/L",
      "Cr": "96 umol/L",
      "pH": "7.36",
      "Hb": "132 g/L",
      "PLT": "213 x10^9/L",
      "WBC": "6.4 x10^9/L"
    },
    "ref_ranges_included": true,
    "missing_context": []
  },
  "questions": {
    "is_critical": {
      "type": "noul",
      "instructions": "该报告中的任一检验项目是否触及危急值（需要立即临床干预）？",
      "criteria": {
        "true": "至少一个项目超出危急值上下限，需要立即通知并干预",
        "false": "所有项目均在危急值范围内"
      }
    },
    "notify_within": {
      "type": "score",
      "instructions": "危急值应在多长时间内通知到主管医师？",
      "criteria": [
        "立即（15 分钟内）",
        "1 小时内",
        "当日内",
        "无需通知（全部项目均未触及危急值）"
      ]
    },
    "critical_item": {
      "type": "choice",
      "instructions": "触发危急值判定的是哪一类检验项目？",
      "criteria": {
        "none": "无（全部项目均未触及危急值）",
        "electrolyte": "电解质（血钾 K+、血钠 Na+）",
        "renal": "肾功能（肌酐 Cr、尿素氮）",
        "glucose_gas": "血糖与血气（血糖 GLU、血气 pH）",
        "cbc": "血常规（血红蛋白 Hb、血小板 PLT、白细胞 WBC）",
        "cardiac_coag": "心肌与凝血（肌钙蛋白 cTn、D-二聚体）"
      }
    },
    "evidence_sufficient": {
      "type": "noul",
      "instructions": "报告是否提供了判定危急值所需的全部要素（项目名、数值、单位、参考区间或判定标准）？",
      "criteria": {
        "true": "要素齐全，可直接对照阈值判定",
        "false": "缺少单位、参考区间或项目名，无法可靠判定"
      }
    }
  },
  "guidance": "危急值是本场景唯一判据：任一项目超出下表上下限即为 is_critical=true，label 取导致判定的那个项目。阈值（示例口径，实际以本院检验科危急值清单为准）：K+ <2.8 或 >6.2 mmol/L；Na+ <120 或 >160 mmol/L；GLU <2.8 或 >16.7 mmol/L；Cr >442 umol/L；pH <7.20 或 >7.60；Hb <50 或 >200 g/L；PLT <30 或 >1000 x10^9/L；WBC <1.5 或 >30 x10^9/L；cTn >0.04 ng/mL；D-Dimer >5 mg/L FEU。notify_within 由触发的项目决定，等级从 0（立即）到 3（当日内）：立即 15 分钟内适用于 K+>6.5、Na+>160 或 <120、pH<7.20、GLU>16.7 或 <2.8、cTn 升高伴胸痛、Hb<50；1 小时内的项目包括 K+ 在 2.8-3.0 或 6.2-6.5、Cr 在 442-600、PLT 在 30-50、Hb 在 50-70；其余触及危急值但未落入上述区间的为 2 小时内；仅 D-Dimer 孤立升高或 WBC 轻度异常为当日内。多个项目同时危急时 severity 取最快的一档，critical_item 取最快档中的项目。evidence_sufficient 为 false 时（缺单位、缺参考区间、缺项目名），is_critical 必须用软标签 target {\"true\":0.5,\"false\":0.5}，且 critical_item 不得凭猜测填写——证据不足即无把握。cr 阈值受年龄与性别影响很大，生成老年女性样本时 Cr 需明显更高才判危急，务必让数值与年龄方向一致。",
  "variety": [
    "科室来源：检验科、影像科、急诊、住院病房、门诊、体检中心",
    "危急值项目数（对应 is_critical 与 critical_item）：0 项全部正常、1 项触及、2 项同时触及、3 项以上同时触及、同一项目高低双侧都触及（如 K+ 同时 <2.8 且 >6.2 不可能，须只取真实方向）",
    "触发项目的六类归属（critical_item 逐项覆盖）：electrolyte（K+、Na+）、renal（Cr、尿素氮）、glucose_gas（GLU、pH）、cbc（Hb、PLT、WBC）、cardiac_coag（cTn、D-Dimer）、none（全部正常）",
    "电解质取值档（须与阈值方向一致）：K+ 正常 3.5-5.0 / 偏低 2.8-3.0 / 危急低 <2.8 / 偏高 6.2-6.5 / 危急高 >6.5；Na+ 正常 135-145 / 危急低 <120 / 危急高 >160",
    "肾功能与代谢取值档：Cr 正常 44-106 / 危急 442-600 / >600（老年女性基线更高，需明显更高才判危急）；GLU 正常 3.9-6.1 / 危急低 <2.8 / 危急高 >16.7；pH 正常 7.35-7.45 / 7.20-7.35 / <7.20 / >7.60",
    "血常规与心肌凝血取值档：Hb 正常 115-150 / 50-70 / <50；PLT 正常 125-350 / 30-50 / <30；WBC 正常 3.5-9.5 / 1.5-3.0 / <1.5 / >30；cTn <0.04 正常 / 0.04-0.1 升高 / >0.1 明显升高；D-Dimer <0.5 正常 / 0.5-5 升高 / >5 mg/L FEU",
    "通知时长档（notify_within 四档全覆盖）：0 立即（K+>6.5、Na+>160 或 <120、pH<7.20、GLU>16.7 或 <2.8、Hb<50）/ 1 小时内（K+ 2.8-3.0 或 6.2-6.5、Cr 442-600、PLT 30-50、Hb 50-70）/ 2 小时内（其余触及危急值项目）/ 3 当日内（孤立 D-Dimer 升高、WBC 轻度异常）",
    "报告完整度（对应 evidence_sufficient）：要素齐全、缺单位、缺参考区间、缺项目名、缺采样时间、缺患者年龄、两项以上同时缺失；evidence_sufficient=false 时 is_critical 必须用软标签且 critical_item 不得凭猜测填写",
    "患者人群：成人、儿童、孕产妇、老年（Cr 基线高）、肾功能不全者、透析患者",
    "临床背景：胸痛、呼吸困难、乏力、头晕、恶心呕吐、无明显症状（体检偶然发现）",
    "数值表述：带单位（mmol/L、g/L、x10^9/L、ng/mL、mg/L FEU）、仅给数值无单位、中文叙述夹英文缩写（K+、Cr、cTn、D-Dimer）、参考区间与实测值并列",
    "易错陷阱：老年女性 Cr 需明显高于 442 才判危急、儿童 Cr 基线低更易达危急、Hb 与 PLT 同时低下时不得只取其一、cTn 升高需结合胸痛才落在「立即」档"
  ]
}
', 'medical', 0, '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00') ON CONFLICT(slug) DO NOTHING;
INSERT INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, spec_json, category, sort, created_at, updated_at) VALUES ('diagnosis', 'medical', 'diagnosis', '诊断', 'Diagnosis', 'docs/medical/specs/diagnosis.json', '{
  "name": "diagnosis",
  "domain": "门诊与急诊的初诊评估。患者因主诉就诊，需要给出初步鉴别方向、是否需要进一步检查、以及就诊紧急度。涵盖心血管、呼吸、消化、神经、泌尿、代谢内分泌、肌肉骨骼、血液肿瘤九大系统。",
  "state": "患者就诊时的结构化记录：人口学、主诉（患者原话，1-3 句）、生命体征、已完成的检验值、是否已做影像、合并症、患病时长。字段名短且跨记录固定。",
  "state_example": {
    "patient": "male 58",
    "chief_complaint": "活动后气促 2 周，伴下肢水肿",
    "vitals": "BP 152/92 mmHg, HR 104 bpm, SpO2 93%",
    "labs": {"肌钙蛋白": "0.9 ng/mL", "NT-proBNP": "3200 pg/mL", "肌酐": "96 umol/L"},
    "imaging": "未做",
    "comorbidities": ["高血压 10 年", "2 型糖尿病 8 年"],
    "duration": "2 周"
  },
  "questions": {
    "differential_direction": {
      "type": "choice",
      "instructions": "初步判断应优先考虑哪个系统的鉴别方向？",
      "criteria": {
        "cardiovascular": "心源性：胸痛、心悸、活动后气促、下肢水肿、血压异常",
        "respiratory": "呼吸系统：咳嗽咳痰、气促、喘息、胸膜相关症状",
        "gastrointestinal": "消化系统：腹痛、反酸、呕吐、腹泻、便血",
        "neurologic": "神经系统：头痛、眩晕、肢体麻木无力、意识改变、言语不清",
        "urinary": "泌尿系统：尿频尿急尿痛、血尿、肾绞痛、排尿困难",
        "endocrine": "代谢内分泌：多饮多尿、体重明显改变、怕冷乏力、血糖异常",
        "musculoskeletal": "肌肉骨骼：关节痛、腰痛、外伤、行走困难",
        "hematologic_oncologic": "血液与肿瘤：贫血貌、淋巴结肿大、盗汗、乏力消瘦",
        "undirected": "现有信息不足以定向，需先完善影像与检验"
      }
    },
    "needs_test": {
      "type": "noul",
      "instructions": "是否需要影像或实验室检查才能进一步明确诊断？",
      "criteria": {
        "true": "已有指向性线索，但仍需检查确认范围、程度或并发症",
        "false": "临床表现已足以给出方向性判断，无需追加检查"
      }
    },
    "urgency": {
      "type": "score",
      "instructions": "本次就诊的紧急程度如何？",
      "criteria": [
        "0：可按普通门诊预约，无需当日处理",
        "1：建议尽快门诊，但无需急诊",
        "2：需要急诊评估或当日处理",
        "3：存在危险信号，需立即急救"
      ]
    },
    "red_flag": {
      "type": "noul",
      "instructions": "是否存在需要立即处理的危险信号？",
      "criteria": {
        "true": "存在危险信号：意识改变、持续胸痛、明显呼吸困难、大出血、严重低血压、SpO2 下降",
        "false": "未发现危险信号"
      }
    }
  },
  "guidance": "differential_direction 优先取最紧急且最专科化的系统：任一危险信号存在时，方向仍按受累系统给出（除非主诉指向两个系统且无法判定），但 needs_test 必为 true、urgency 必为 3。三个方向并存无法判定时取 undirected，且 needs_test 为 true。urgency 3 与 red_flag true 等价：存在任一危险信号则两者同时为真。urgency 0 时 red_flag 必为 false。needs_test 为 false 仅在主诉已高度特异且体征与检验均无异常时出现，此时 urgency 不得为 2 或 3。",
  "variety": [
    "九个系统的典型主诉（differential_direction 九选项逐一覆盖）：cardiovascular（胸痛、心悸、活动后气促、下肢水肿、血压异常）、respiratory（咳嗽咳痰、气促、喘息、胸膜相关症状）、gastrointestinal（腹痛、反酸、呕吐、腹泻、便血）、neurologic（头痛、眩晕、肢体麻木无力、意识改变、言语不清）、urinary（尿频尿急尿痛、血尿、肾绞痛、排尿困难）、endocrine（多饮多尿、体重明显改变、怕冷乏力、血糖异常）、musculoskeletal（关节痛、腰痛、外伤、行走困难）、hematologic_oncologic（贫血貌、淋巴结肿大、盗汗、乏力消瘦）、undirected（三个方向并存无法判定）",
    "危险信号八项（red_flag=true 与 urgency=3 需逐项覆盖，并各自触发对应系统方向）：意识改变或晕厥、持续胸痛、明显呼吸困难、呕血或黑便、大出血、严重低血压、SpO2 下降、剧烈头痛伴喷射性呕吐",
    "紧急度档（urgency 四档全覆盖）：0 可按普通门诊预约（慢病随访、常规体检、轻症稳定且 red_flag=false）、1 建议尽快门诊但无需急诊、2 需要急诊评估或当日处理、3 存在危险信号需立即急救（此时 red_flag 必为 true）",
    "needs_test=false 的特例（需专门生成此类以覆盖该标签）：主诉已高度特异且体征与检验均无异常，此时 urgency 不得为 2 或 3",
    "undirected 的特例（需专门生成此类以覆盖该标签）：主诉同时涉及三个系统、检验与影像均无指向性证据，此时 needs_test 必为 true",
    "主诉与检验方向关系：方向一致、主诉含糊但检验有明确指向、检验完全缺失、主诉与检验方向冲突（须按最紧急且最专科化的系统仲裁）",
    "主诉长度与语气：一句话、三句话、平实叙述、焦虑、急迫、表述含糊（患者说不清部位或时间）",
    "年龄跨度：婴幼儿、儿童、青年、中年、老年、极高龄",
    "生命体征组合：全部正常、仅一项异常、多项同时异常、完全未测量",
    "合并症与用药：无、单一慢性病（高血压/糖尿病）、多病共存、既往手术史、正在服用抗凝药或降糖药",
    "是否已做影像：未做、已做且正常、已做且有异常但与主诉方向不一致、影像为决定性证据（此时 needs_test 可为 false）",
    "患病时长：数小时、数天、2-4 周、3 个月以上、慢性反复发作"
  ]
}
', 'medical', 1, '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00') ON CONFLICT(slug) DO NOTHING;
INSERT INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, spec_json, category, sort, created_at, updated_at) VALUES ('icd-coding', 'medical', 'icd-coding', 'ICD 编码', 'ICD Coding', 'docs/medical/specs/icd-coding.json', '{
  "name": "icd-coding",
  "domain": "住院病案编码与 DRG/DIP 审核。对象为已出院病案的编码员复核场景，涉及主要诊断、其他诊断、手术操作编码，以及诊断与病历记录是否一致、编码是否在合理候选集内、是否需要编码员逐条核对。涉及疾病系统以常见内外科为主：循环、呼吸、消化、泌尿、代谢内分泌、肿瘤、骨关节、妇产。",
  "state": "一份病案的**结构化摘要**（不是病历全文）：患者年龄性别、住院天数、主要诊断与次要诊断列表（已由 HIS 导出）、手术操作名称与部位、检验与影像的关键阳性发现、既往史与合并症。用药与治疗经过只保留与诊断相关的要点（一到两句），不含病程记录全文。",
  "state_example": {
    "patient": "male 64",
    "length_of_stay_days": 9,
    "primary_dx": "急性ST段抬高型心肌梗死（前壁）",
    "secondary_dx": ["高血压3级 很高危", "2型糖尿病", "高脂血症"],
    "procedure": ["冠状动脉造影", "经皮冠状动脉药物洗脱支架置入（前降支）"],
    "key_findings": ["心电图 II III aVF V1-V6 ST段抬高0.3-0.5mV", "肌钙蛋白I 18.4 ng/mL 升高", "心脏超声 LVEF 42%"],
    "past_history": ["高血压 12 年", "2 型糖尿病 8 年", "吸烟 30 年"],
    "clinical_course": "急诊行 CAG 后植入 DES，术后规律用药，病情稳定出院"
  },
  "questions": {
    "coding_reasonable": {
      "type": "choice",
      "instructions": "病案首页填报的诊断与手术操作，在本候选集内是否合理？",
      "criteria": {
        "reasonable": "诊断与病历记录相符，诊断顺序与并发症关系正确，手术操作与记录一致",
        "questionable": "存在疑点：并发症/合并病顺序、主诊断选择、手术操作部位或层次不清，需要编码员核对",
        "wrong": "明显错误：诊断与病历记录矛盾、凭空增加诊断、主诊断与手术严重不符"
      }
    },
    "needs_coder": {
      "type": "noul",
      "instructions": "该病案是否必须由编码员逐条复核后才能入档？",
      "criteria": {
        "true": "含肿瘤诊断、罕见病、复杂手术、多系统并发症、诊断与记录不一致、疑难主诊断选择",
        "false": "诊断与手术常规清晰，可批量校验通过"
      }
    },
    "evidence_gap": {
      "type": "choice",
      "instructions": "该病案最主要的问题是什么？",
      "criteria": {
        "none": "证据链完整，诊断与记录相互印证",
        "order": "诊断顺序问题：主诊断未选为本次入院的主要病因或并发症关系颠倒",
        "missing_dx": "诊断缺失：病历中明确提及但首页未填的并发症或合并症",
        "over_dx": "过度诊断：首页诊断缺乏病历记录支持",
        "procedure_mismatch": "手术操作不符：操作名称、部位或层次与记录不一致",
        "insufficient_record": "记录不足：关键诊断依据在摘要中缺失，无法判定"
      }
    },
    "confidence_tier": {
      "type": "score",
      "instructions": "对该病案编码正确性的置信档位如何？",
      "criteria": [
        "0 = 高置信：证据链完整，判定无争议",
        "1 = 中置信：存在轻微疑点但结论方向明确",
        "2 = 低置信：关键依据缺失或矛盾，需人工裁定"
      ]
    }
  },
  "guidance": "本场景**不要求模型直接输出 ICD 编码**，只判断「病案首页填报的诊断与手术，在给定候选集内是否合理」。coding_reasonable 的判定必须以 key_findings 与 clinical_course 中可见的记录为唯一依据，不得依据常识补全病历中未提及的诊断：key_findings 与诊断列表一一对应且顺序符合「病因在前、并发症在后」时判 reasonable；主诊断是并发症而非本次入院主因、或诊断顺序颠倒（如把高血压放在急性心梗之前）判 questionable；病历记录（key_findings / clinical_course）与首页诊断直接矛盾、或首页含记录中完全未提及的诊断时判 wrong。needs_coder 为独立信号：诊断列表含恶性肿瘤（含转移瘤）、罕见病、系统性自身免疫病，或 procedure 含复杂操作（如多支血管支架、联合脏器手术、移植），或 evidence_gap 不为 none 时，即使 coding_reasonable 为 reasonable 也须 true。evidence_gap 的判定优先级：记录矛盾或凭空诊断 → over_dx 或 procedure_mismatch；主诊断选择错误或顺序颠倒 → order；记录中提到但首页未填 → missing_dx；摘要中依据不足无法判定 → insufficient_record；完全一致 → none。confidence_tier 由 evidence_gap 决定：none 且 reasonable 时必须为 0；insufficient_record 时必须为 2；其余情况按 reasonable→1、questionable→2、wrong→2 映射。特别地，即使 key_findings 支持某诊断，clinical_course 完全未提及时也判 insufficient_record 而不是 reasonable——本场景宁可交人工，不可凭医学常识替编码员做主。",
  "variety": [
    "疾病系统（覆盖 domain 列出的各系统）：循环（急性心梗、心衰、房颤、高血压 3 级）、呼吸（COPD 急性加重、肺炎、支气管肺癌、哮喘）、消化（肝硬化失代偿、急性胆囊炎、重症胰腺炎、上消化道出血）、泌尿（前列腺增生、肾结石、膀胱癌、急性肾损伤）、代谢内分泌（糖尿病酮症酸中毒、甲状腺功能减退、高钾血症）、肿瘤（肺癌根治术、消化道肿瘤化疗、转移瘤）、骨关节（全髋关节置换、脊柱融合、股骨颈骨折内固定）、妇产（剖宫产、子宫肌瘤剔除、卵巢囊肿蒂扭转）、神经（脑梗死、颅内出血、帕金森病）",
    "病案类型：单病种手术、复杂多系统并发症、肿瘤化疗、危重症转归、死亡病例、择期手术、无手术的内科住院",
    "诊断顺序问题（对应 evidence_gap=order）：主诊断正确、并发症误当主诊断、顺序颠倒（如高血压排在急性心梗之前）、主诊断为术后并发症而非入院病因、缺主诊断",
    "诊断缺失（对应 missing_dx）：病历提到但首页未填的并发症（术后肺炎、深静脉血栓、急性肾损伤、低蛋白血症）、未填的合并症（房颤、既往骨折、陈旧性脑梗）、未填的恶性肿瘤转移灶",
    "过度诊断（对应 over_dx）：凭空增加的诊断、与 key_findings 无关的诊断、与用药记录完全不相关的诊断",
    "操作不符（对应 procedure_mismatch）：操作部位不符（左侧 vs 右侧、主动脉 vs 上肢）、操作层次不清（部分切除 vs 全切除、根治 vs 姑息）、操作名称笼统（仅写「手术」）、操作与记录时间线不符",
    "记录质量：记录完整、关键依据缺失（clinical_course 完全未提及该诊断）、记录与首页直接矛盾、事后补记痕迹",
    "证据强度：key_findings 明确且与诊断一一对应、仅有笼统描述、只有诊断无任何检查依据、影像结论与检验数值矛盾",
    "needs_coder=true 的触发场景（须专门生成）：诊断含恶性肿瘤（含转移瘤）、罕见病、系统性自身免疫病、复杂手术（多支血管支架、联合脏器手术、器官移植）、evidence_gap 不为 none",
    "置信档（对应 confidence_tier 三档）：0 高置信（证据链完整且 reasonable）、1 中置信（轻微疑点但方向明确）、2 低置信（关键依据缺失或矛盾，需人工裁定；insufficient_record 时必须为 2）",
    "住院时长与转归：1-3 天、4-9 天、10 天以上、死亡、自动出院、转院",
    "主诊断表述规范度：规范术语（含部位与性质）、笼统表述（症状主导）、待排诊断（带「?」或「待排」）、英文缩写混排"
  ]
}
', 'medical', 2, '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00') ON CONFLICT(slug) DO NOTHING;
INSERT INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, spec_json, category, sort, created_at, updated_at) VALUES ('medication-review', 'medical', 'medication-review', '用药审查', 'Medication Review', 'docs/medical/specs/medication-review.json', '{
  "name": "medication-review",
  "domain": "门诊与住院处方审核。药品覆盖抗感染药、降压药、降糖药、抗凝药、NSAIDs、质子泵抑制剂、镇痛药等常见类别；患者为成人、孕产妇、哺乳期妇女、儿童、老年、肝肾功能不全者。审核依据为药品说明书禁忌与剂量上限、重复用药、特殊人群禁忌、给药途径与适应症。",
  "state": "一份待审核处方的结构化摘要：患者年龄性别与生理状态（妊娠周数、哺乳、肾功能 eGFR 数值、肝功能）、过敏史、既往用药、当前处方药品与剂量频次、疗程天数（已由生成器算好，不要求模型做日期运算）、适应症诊断。字段值为中文叙述夹英文药名缩写。",
  "state_example": {
    "patient": "female 34, gestation 28 weeks",
    "state_flags": "pregnant, eGFR 88 mL/min/1.73m2",
    "allergies": "青霉素（皮疹）",
    "current_meds": ["头孢曲松 1g qd"],
    "current_rx": "甲硝唑 0.4g tid x 7天",
    "days_on_drug": 3,
    "indication": "细菌性阴道炎"
  },
  "questions": {
    "verdict": {
      "type": "choice",
      "instructions": "该处方的审核结论是什么？",
      "criteria": {
        "pass": "无问题，可直接执行",
        "conditional": "有可纠正的偏差（如剂量偏小、疗程偏短、缺少辅助用药），放行但需提示",
        "reject": "存在必须拦截的严重问题（禁忌、重复用药、超剂量、明确适应症不符）"
      }
    },
    "needs_pharmacist": {
      "type": "noul",
      "instructions": "该处方是否必须由药师复核后才能执行？",
      "criteria": {
        "true": "含高风险信号（妊娠/哺乳/儿童/老年、肝肾功能异常、多药联用、注射剂、管制类）",
        "false": "低风险，可按常规执行"
      }
    },
    "issue_type": {
      "type": "choice",
      "instructions": "该处方最突出的问题是哪一类？",
      "criteria": {
        "none": "未发现问题",
        "contraindication": "禁忌：患者对该药存在绝对禁忌（如孕妇用四环素、青霉素过敏用头孢）",
        "dose_over": "剂量超限：单次或日剂量超过说明书上限",
        "duplicate": "重复用药：与既往用药或同处方内其他药物成分重复或同类叠加",
        "special_population": "特殊人群：妊娠、哺乳、儿童、老年、肝肾功能不全中的人群限制被忽略",
        "indication_mismatch": "适应症不符：药品与所列诊断不匹配"
      }
    },
    "severity": {
      "type": "score",
      "instructions": "该处方问题的严重程度如何？",
      "criteria": [
        "0 = 无需处理",
        "1 = 提示即可（轻微偏差，不影响疗效与安全）",
        "2 = 需干预（影响疗效或有潜在风险，须修改后执行）",
        "3 = 必须拦截（禁忌或超剂量，存在严重不良事件风险）"
      ]
    }
  },
  "guidance": "verdict 由最严重的问题决定：出现 contraindication 或 dose_over 或 duplicate 判 reject；仅 special_population 或 indication_mismatch 且可纠正判 conditional；无问题判 pass。issue_type 取命中的最突出的一类，多类同时命中时按 contraindication > dose_over > duplicate > special_population > indication_mismatch 的优先级取。severity 与 verdict 严格对应：pass=0、conditional=2、reject=3，issue_type=none 时 severity 必须为 0。severity 1 仅用于「无规则命中但剂量偏离常规」的情形，此时 verdict 为 pass、issue_type 为 none。needs_pharmacist 为独立风险信号，与 verdict 无关：只要涉及妊娠、哺乳、儿童、老年、肝肾功能异常（eGFR<30 或转氨酶升高）、注射剂、管制类、或同时使用 3 种以上药物，即使 verdict 为 pass 也须 true。妊娠期禁忌示例：四环素类、喹诺酮类（权衡后）、华法林、ACEI/ARB（妊娠中晚期）、异维A酸；哺乳期：大剂量化疗、四环素；儿童：四环素（<8 岁）、喹诺酮（<18 岁）、阿司匹林（水痘/病毒感染期）；肝肾功能不全需减量或禁用头孢曲松、氨基糖苷类、万古霉素。dose_over 示例：甲硝唑单次 >0.6g、对乙酰氨基酚单次 >1g 或日剂量 >4g、头孢曲松单次 >2g（普通感染）。days_on_drug 与疗程天数字段已由生成器算好，模型只判断「疗程是否明显不合理」，绝不做日期加减运算。过敏史为「青霉素（皮疹）」时，任何青霉素类或头孢类均为 contraindication。",
  "variety": [
    "药品类别（务必覆盖）：抗感染药（头孢曲松、阿莫西林、甲硝唑、左氧氟沙星、喹诺酮类）、降压药（ACEI/ARB、钙通道阻滞剂、利尿剂、β受体阻滞剂）、降糖药（二甲双胍、磺脲类、胰岛素）、抗凝与抗血小板（华法林、低分子肝素、阿司匹林、氯吡格雷）、NSAIDs（布洛芬、双氯芬酸）、镇痛药（对乙酰氨基酚、曲马多、吗啡）、质子泵抑制剂（奥美拉唑、雷贝拉唑）、抗真菌与抗病毒药",
    "问题类型（对应 issue_type 六选项全覆盖）：none 无问题、contraindication 绝对禁忌、dose_over 剂量超限、duplicate 重复用药、special_population 特殊人群禁忌、indication_mismatch 适应症不符",
    "审核结论档（对应 verdict）：pass 无问题可执行、conditional 可纠正偏差（剂量偏小、疗程偏短、缺辅助用药、缺监测、给药频次不当）、reject 必须拦截（禁忌、重复用药、超剂量、明确适应症不符）",
    "严重度档（与 verdict 严格对应）：pass=0、conditional=2、reject=3；severity=1 仅用于「无规则命中但剂量偏离常规」，此时 verdict=pass 且 issue_type=none",
    "剂量超限的具体对照（写进 state 的实测值）：甲硝唑单次 >0.6g、对乙酰氨基酚单次 >1g 或日剂量 >4g、头孢曲松单次 >2g（普通感染）、华法林超出抗凝范围、胰岛素剂量未按体重折算",
    "禁忌的具体对照：孕妇用四环素类、青霉素过敏（皮疹）用头孢类、肝功能不全用头孢曲松、eGFR<30 用氨基糖苷类或万古霉素、哺乳期大剂量化疗",
    "重复用药的具体形态：同处方内两种成分相同的药、头孢与喹诺酮抗菌谱重叠、同机制叠加（双联 PPI、两种促泌剂）、抗凝药与 NSAIDs 并用增加出血风险",
    "特殊人群（needs_pharmacist=true 的主要触发）：孕早/中/晚期、哺乳期、新生儿与儿童（<8 岁四环素、<18 岁喹诺酮）、老年 ≥65 岁且多病共存、肝肾功能不全（eGFR<30 或转氨酶升高）、透析、注射剂、管制类、同时使用 3 种以上药物",
    "过敏史形态：有明确药物过敏（青霉素皮疹）、多种药物过敏、过敏史为空、曾有皮疹但非速发过敏（此时不得判 contraindication）",
    "用药数量：单一用药、2-3 种联用、4-5 种、5 种以上多药联用",
    "疗程与已用天数：疗程合理、偏短需延长、明显不合理（过长或过短）；days_on_drug 与疗程天数须由生成器算好，模型只判断是否明显不合理、不做日期运算",
    "给药途径与药名表述：口服片、静脉滴注、静脉推注、肌肉注射、外用、吸入；中文商品名、通用名、英文缩写（ceftriaxone / metronidazole）、中英混排；剂量写法 mg/g/ml/片/支 混用",
    "适应症不符的具体对照：抗生素用于无细菌指征的功能性消化不良、镇痛药用于与诊断无关的疼痛、降压药用于非高血压适应症",
    "边界陷阱（务必按 guidance 处理）：eGFR<30 或转氨酶升高时即使 verdict=pass 也须 needs_pharmacist=true；过敏史为「青霉素（皮疹）」时任何青霉素类或头孢类均为 contraindication；禁忌与重复用药的优先级高于剂量偏差"
  ]
}
', 'medical', 3, '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00') ON CONFLICT(slug) DO NOTHING;
INSERT INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, spec_json, category, sort, created_at, updated_at) VALUES ('nursing-quality', 'medical', 'nursing-quality', '护理质量', 'Nursing Quality', 'docs/medical/specs/nursing-quality.json', '{
  "name": "nursing-quality",
  "domain": "医院护理质量管控。质控维度覆盖护理评估、给药执行、护理记录、管路与设备、皮肤与压疮、跌倒与导管预防、医患沟通。对象为住院患者与门诊输液患者。质控依据为护理核心制度、检查表条目与医院质控标准。",
  "state": "一次护理质量检查的结构化摘要：患者年龄性别与护理级别、所在病区、检查时间点、涉及的具体护理环节（如静脉输液、皮下注射、留置导尿管、压疮风险评估、跌倒风险评估、护理记录书写）、检查中发现的实际情况（做了什么、记录了什么、是否规范）、患者依赖程度（是否卧床、是否留置多路管路）。",
  "state_example": {
    "patient": "male 71, bedridden",
    "ward": "神经内科 3 病区",
    "nursing_level": "一级护理",
    "check_point": "静脉输液过程",
    "observed": "输液前未核对腕带姓名，巡视记录本上 14:00 一栏空白",
    "dependencies": "留置尿管 1 条，桡动脉测压管 1 条",
    "risk_scores": "Braden 12 分（中等风险），Morse 评分 45 分（高风险）"
  },
  "questions": {
    "issue_type": {
      "type": "choice",
      "instructions": "本次检查发现的问题属于哪一类？",
      "criteria": {
        "none": "未发现问题",
        "assessment": "护理评估：入院评估、风险评估（压疮/跌倒/导管）未做或做得不完整",
        "execution": "给药与操作执行：核对、给药、输血、导管维护等操作未按规范执行",
        "record": "护理记录：记录缺失、漏项、事后补记、字迹或时间逻辑不自洽",
        "communication": "沟通与健康教育：告知不到位、知情同意缺失、宣教未落实",
        "device": "设备与管路：管路固定、标识、刻度、引流装置管理不规范"
      }
    },
    "reportable": {
      "type": "noul",
      "instructions": "该问题是否需要上报护理部（形成质量缺陷事件）？",
      "criteria": {
        "true": "构成护理不良事件或需质量改进追踪（给药错误、管路脱落、压疮发生、跌倒、非计划拔管、记录严重失真）",
        "false": "一般缺陷，可在科室质控会内整改"
      }
    },
    "severity": {
      "type": "score",
      "instructions": "该问题的严重程度如何？",
      "criteria": [
        "0 = 符合规范，无需处理",
        "1 = 轻度缺陷：流程执行不到位但未造成实际后果",
        "2 = 中度缺陷：已造成患者可观察的不适或潜在风险，需科室整改",
        "3 = 重度缺陷：构成护理不良事件，需立即上报并组织讨论"
      ]
    },
    "preventable": {
      "type": "choice",
      "instructions": "该问题的可预防性如何？",
      "criteria": {
        "preventable": "可通过规范执行与培训预防（多数护理缺陷属于此类）",
        "partially": "部分可预防，还需设备、药品或人力条件配合",
        "not_preventable": "不可预防（患者病情突变、不可避免的并发症等）"
      }
    }
  },
  "guidance": "issue_type 按检查点与 observed 的直接对应关系判定，不要外推：核对/给药/输血/操作步骤相关的问题归 execution；评估表未做或要素缺失归 assessment；记录本缺项、漏签名、时间逻辑矛盾归 record；宣教告知/解释不到位归 communication；管路固定松脱、无标识、刻度不准、引流装置更换超时归 device。reportable 为 true 的触发条件是问题造成了实际不良事件或需要跨科室质量追踪：给药错误（含给错药、漏给、剂量错误）、管路脱落与非计划拔管、压疮发生、跌倒致伤、非计划拔管、护理记录严重失真（事后补记伪造）、给药后不良反应未及时处置。severity 严格对应：issue_type=none 时 severity 必须为 0；一般执行或记录缺陷未造成后果为 1（对应 reportable=false）；已造成患者可观察不适或存在潜在风险为 2；构成不良事件为 3（reportable=true）。因此 issue_type=none 与 severity=0、reportable=false 必须同时成立。preventable 取值规则：只要缺陷源于执行动作或记录行为未按规范做，即为 preventable；仅当还牵涉设备缺陷、药品短缺、人手不足等系统因素时才是 partially；仅当问题源于患者病情本身突变（如突发动脉瘤破裂、术后并发症）时才是 not_preventable。patient 为 bedridden、dependencies 含多路管路、risk_scores 提示中高风险时，同等缺陷的 severity 应上浮一级，但前提是 observed 中确有该环节的执行或记录问题。",
  "variety": [
    "检查环节（覆盖 domain 的七个质控维度）：入院评估、压疮风险评估、跌倒风险评估、静脉输液、皮下注射、肌肉注射、口服药给药、输血核对、留置导尿管维护、留置胃管、静脉留置针管路维护、压疮护理、护理记录书写、交接班、医患沟通、健康教育宣教",
    "缺陷类型（issue_type 六选项逐一覆盖）：none 未发现问题、assessment 评估未做或要素缺失、execution 核对/给药/输血/无菌操作未按规范、record 漏项/漏签名/时间逻辑矛盾/事后补记、communication 告知不到位/知情同意缺失/宣教未落实、device 管路固定松脱/无标识/刻度不准/引流更换超时",
    "严重度档（severity 四档全覆盖，且须与 issue_type 联动）：0 符合规范（issue_type=none 时必须为 0）、1 轻度流程缺陷未造成后果、2 中度已造成可观察不适或潜在风险、3 重度构成护理不良事件",
    "不良事件类型（reportable=true 的触发，须逐项覆盖）：给药错误（给错药/漏给/剂量错误）、管路脱落、非计划拔管、压疮发生、跌倒致伤、护理记录严重失真（事后补记伪造）、给药后不良反应未及时处置",
    "可预防性（preventable 三选项全覆盖）：preventable 源于执行或记录未按规范、partially 牵涉设备缺陷/药品短缺/人手不足、not_preventable 源于患者病情突变（突发动脉瘤破裂、术后并发症）",
    "患者依赖度：自理、部分自理、卧床 bedridden、多路管路、意识障碍、术后早期活动受限",
    "护理级别：特级、一级、二级、三级",
    "病区：内科、外科、ICU、肿瘤科、老年科、产科、儿科、康复科",
    "风险评分：Braden 低/中/高风险、Morse 跌倒评分低/中/高风险并给出具体分值、评分缺失未评估",
    "时间点：交接班高峰、午间、夜间、查房时、抢救后、术前准备期",
    "检查主体与场景：护士长巡查、责任护士自查、质控科抽查、实习生带教、跨科室会诊",
    "严重度上浮规则（须按 guidance 处理）：patient 为 bedridden、dependencies 含多路管路或 risk_scores 提示中高风险时，同等缺陷的 severity 上浮一级，但前提是 observed 中确有该环节的执行或记录问题"
  ]
}
', 'medical', 4, '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00') ON CONFLICT(slug) DO NOTHING;
INSERT INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, spec_json, category, sort, created_at, updated_at) VALUES ('record-summary', 'medical', 'record-summary', '病历摘要', 'Record Summary', 'docs/medical/specs/record-summary.json', '{
  "name": "record-summary",
  "domain": "住院病历的现病史与病程记录摘要核对。摘要由结构化要素组成：主诉、现病史要点、体格检查、诊断、用药、诊疗计划。上游医师已写下部分要素，摘要助手需要判断要素是否完整、是否需要编码员复核、以及缺陷的严重程度。不直接生成 ICD 编码，只判断完整性与是否需人工。",
  "state": "一份住院病历的结构化摘录，字段短且跨记录固定：人口学、主诉、现病史要点、查体记录、诊断列表、用药记录、诊疗计划、缺失标记。要点已由上游抽取或规则截断，不含病历全文。",
  "state_example": {
    "patient": "female 64",
    "chief_complaint": "反复右上腹疼痛 3 个月",
    "presenting_history": "3 个月前无明显诱因出现右上腹隐痛，餐后加重，伴嗳气，无反酸",
    "examination": "右上腹轻压痛，无反跳痛，肝区叩击痛阴性",
    "diagnosis": ["慢性胃炎", "幽门螺杆菌感染待排"],
    "medications": ["雷贝拉唑 20 mg qd", "阿莫西林 1000 mg tid"],
    "plan": "胃镜检查 + 幽门螺杆菌呼气试验，评估根除治疗指征",
    "missing_element": "无"
  },
  "questions": {
    "missing_element": {
      "type": "choice",
      "instructions": "摘要中缺失的是哪个要素？",
      "criteria": {
        "none": "六个要素齐全，无缺失",
        "chief_complaint": "缺主诉",
        "presenting_history": "缺现病史要点",
        "examination": "缺体格检查记录",
        "diagnosis": "缺诊断",
        "medication": "缺用药记录",
        "plan": "缺诊疗计划"
      }
    },
    "needs_coder_review": {
      "type": "noul",
      "instructions": "这份摘要是否需要编码员复核后才能用于编码？",
      "criteria": {
        "true": "需要复核：要素缺失影响诊断编码，或诊断列表与记录内容不一致",
        "false": "无需复核：要素齐全且诊断与记录一致"
      }
    },
    "severity": {
      "type": "score",
      "instructions": "摘要缺陷的严重程度如何？",
      "criteria": [
        "0：要素齐全，无缺陷",
        "1：轻度缺陷：缺主诉或现病史要点，不影响诊断判断",
        "2：中度缺陷：缺查体、诊断或用药记录，诊断可信度下降",
        "3：重度缺陷：缺诊疗计划，无法判断后续处理"
      ]
    },
    "coding_confidence": {
      "type": "score",
      "instructions": "依据这份摘要做诊断编码的置信档位如何？",
      "criteria": [
        "0：低置信 —— 关键要素缺失，编码需要额外临床信息",
        "1：中置信 —— 诊断可初步判断，但需补充要素确认",
        "2：高置信 —— 要素齐全且诊断与记录一致"
      ]
    }
  },
  "guidance": "missing_element 为 none 当且仅当六个要素全部存在；此时 severity 必为 0、needs_coder_review 必为 false、coding_confidence 必为 2。severity 由缺失要素的类型决定而非随机：缺主诉或现病史要点为 1，缺查体、诊断或用药记录为 2，缺诊疗计划为 3。needs_coder_review 为 true 当且仅当 severity >= 2。coding_confidence 由 severity 派生：severity 0 对应 2，severity 1 与 2 对应 1，severity 3 对应 0。诊断列表存在但与用药记录明显不符（用药为完全不相关类别）时，即使无要素缺失也需要编码员复核，此时 severity 取 2、coding_confidence 取 1。",
  "variety": [
    "六要素缺失组合（missing_element 七选项逐一覆盖）：全齐 none、缺主诉 chief_complaint、缺现病史要点 presenting_history、缺体格检查 examination、缺诊断 diagnosis、缺用药记录 medication、缺诊疗计划 plan、缺两项（低频但须存在）",
    "严重度档（severity 由缺失要素类型派生，不得随机）：0 六要素全齐、1 缺主诉或现病史要点、2 缺查体/诊断/用药记录、3 缺诊疗计划",
    "置信档（coding_confidence 由 severity 派生）：2 高置信（要素齐全且诊断与记录一致）、1 中置信（severity 为 1 或 2，需补充要素确认）、0 低置信（severity 为 3，缺诊疗计划无法判断后续处理）",
    "needs_coder_review=true 的两类来源（须都生成）：要素缺失影响诊断编码（severity>=2）；六要素齐全但诊断列表与用药记录明显不符（用药为完全不相关类别），此时 severity 取 2、coding_confidence 取 1",
    "科室来源：内科、外科、肿瘤科、妇产科、儿科、ICU、康复科、中医科",
    "病程阶段：入院记录、首次病程记录、阶段小结、出院小结、死亡记录、手术记录",
    "诊断数量与构成：单一诊断、并列多个诊断、待排诊断（带「待排」或「?」）、入院诊断与出院诊断不一致、并发症未列入诊断列表",
    "用药复杂度：无用药记录、单药、联合用药、特殊人群用药（孕产妇/肾功能不全/肝功能异常）、用药与诊断明显不符",
    "主诉风格：口语化（「肚子疼」）、书面化、极简（「发热」）、冗长、时间表述模糊（「这几天」）",
    "现病史要素完整度：起病时间/诱因/性质/加重缓解因素/伴随症状/既往诊疗经过——六要素齐全、仅前三项、完全缺失",
    "查体记录：生命体征齐全、仅部分系统、仅记录阳性体征、缺阴性体征、模板化复制上一份",
    "诊疗计划：明确检查计划、仅笼统记录（「对症处理」）、缺失、计划与诊断不匹配",
    "患者人群：成人、儿童、孕产妇、老年、危重、术后"
  ]
}
', 'medical', 5, '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00') ON CONFLICT(slug) DO NOTHING;
INSERT INTO scenarios (id, domain_id, slug, label_zh, label_en, spec_path, spec_json, category, sort, created_at, updated_at) VALUES ('triage', 'medical', 'triage', '分诊', 'Triage', 'docs/medical/specs/triage.json', '{
  "name": "triage",
  "domain": "医院门诊与互联网医院的导诊分诊。输入为患者自述或接线员记录的中文主诉，涵盖发热、咳嗽、腹痛、胸闷胸痛、头晕头痛、关节痛、皮疹、创伤、孕产、下泌尿道症状、儿童发热等。场景含线下门诊挂号导诊与线上问诊分诊两类。",
  "state": "一位患者就诊意图的结构化摘要：年龄性别、就诊方式、主诉（患者原话或接线员记录，1-3 句，混合口语化表达与医学术语）、症状持续时间、伴随症状列表、基础疾病与用药、生命体征数值（若已知）、有无急症红旗征象描述。字段值为中文叙述。",
  "state_example": {
    "patient": "male 58",
    "channel": "线下门诊导诊台",
    "chief_complaint": "胸口压着难受，走了两条路就喘不上气，晚上睡不平",
    "duration": "3 天",
    "accompanying": ["活动后气促", "夜间不能平卧", "出汗"],
    "history": ["高血压 10 年", "长期吸烟"],
    "vitals": "BP 165/98 mmHg, HR 96 bpm, SpO2 94%",
    "red_flags": "无晕厥、无剧烈持续胸痛"
  },
  "questions": {
    "department": {
      "type": "choice",
      "instructions": "这位患者应该首先挂哪个科室？",
      "criteria": {
        "general_medicine": "内科（普通内科）",
        "cardiology": "心血管内科",
        "respiratory": "呼吸内科",
        "gastroenterology": "消化内科",
        "neurology": "神经内科",
        "orthopedics": "骨科",
        "dermatology": "皮肤科",
        "urology": "泌尿外科",
        "obstetrics_gynecology": "妇产科",
        "pediatrics": "儿科",
        "emergency": "急诊科",
        "ophthalmology": "眼科",
        "ent": "耳鼻咽喉科",
        "endocrinology": "内分泌科"
      }
    },
    "immediate_human": {
      "type": "noul",
      "instructions": "这位患者是否应当立即由人工分诊员介入（而不是直接指引其自行挂号）？",
      "criteria": {
        "true": "存在急症或高危信号，需人工立即介入",
        "false": "可按指引自行挂号"
      }
    },
    "acuity": {
      "type": "score",
      "instructions": "该患者情况的紧急程度如何？",
      "criteria": [
        "0 = 非紧急（可择期就诊）",
        "1 = 亚急性（数日内就诊）",
        "2 = 急性（当日就诊）"
      ]
    },
    "red_flag": {
      "type": "noul",
      "instructions": "是否存在需要立即急诊处理的红旗征象（胸痛、意识改变、大出血、呼吸困难、剧烈头痛伴呕吐、持续高热惊厥、孕产出血等）？"
    }
  },
  "guidance": "department 是患者应当首先挂的科室，不是所有相关科室。多症状共存时按以下优先级归属：任何红旗征象一律先判 emergency（覆盖其他一切科室规则），其次看主诉对应的系统；主诉同时涉及两个系统时，取更紧急或更专科化的那个——胸闷/心悸/活动后气促/水肿/血压极高判 cardiology 而非 general_medicine；咳嗽咳痰/气喘/发热伴呼吸道症状判 respiratory；腹痛按部位（上腹、右上腹、脐周、下腹）分别对应 gastroenterology、hepatology 类或 general_medicine、妇科；眩晕/肢体麻木无力/言语不清判 neurology；外伤/骨折/关节肿痛判 orthopedics；皮疹/瘙痒/皮损判 dermatology；尿频尿急尿痛、血尿、肾绞痛判 urology；孕产相关（停经、阴道流血、孕期不适、产检）判 obstetrics_gynecology；14 岁以下且以发热、咳嗽、腹泻、呕吐为主诉判 pediatrics（除非有明确红旗征象，则 emergency 优先）。immediate_human 为 true 当且仅当 red_flag 为 true，或存在以下高危信号：胸痛/胸闷伴出汗与气促、意识改变或晕厥、咯血或呕血、黑便、剧烈头痛伴喷射性呕吐、持续高热 >3 天伴精神萎靡、呼吸困难（SpO2<94% 或说话不能成句）、婴幼儿高热惊厥、孕期阴道流血或腹痛。acuity 与 red_flag 联动：red_flag 为 true 时 acuity 必须为 2；immediate_human 为 true 但无红旗时 acuity 为 2；可择期就诊（如复诊、慢病随访、常规体检咨询）为 0；数日内需就诊为 1。acuity=0 的样本必须 immediate_human=false。红旗征象必须由主诉或生命体征明确支持，模型不得凭科室归属反推红旗。",
  "variety": [
    "14 个科室的典型主诉（department 每一选项都须覆盖）：general_medicine（乏力、发热待查、慢病开药）、cardiology（胸闷胸痛、心悸、活动后气促、下肢水肿、血压极高）、respiratory（咳嗽咳痰、气喘、咯血、呼吸困难）、gastroenterology（上腹痛、烧心反酸、呕吐腹泻）、neurology（眩晕、头痛、肢体麻木无力、言语不清、意识改变）、orthopedics（外伤、骨折、关节肿痛、腰腿痛、行走困难）、dermatology（皮疹、瘙痒、皮损、脱发）、urology（尿频尿急尿痛、血尿、肾绞痛、排尿困难）、obstetrics_gynecology（停经、阴道流血、孕期不适、产检、妇科下腹痛）、pediatrics（14 岁以下以发热/咳嗽/腹泻/呕吐为主诉）、emergency（任何红旗征象、严重外伤、中毒、溺水、窒息）、ophthalmology（视物模糊、眼痛、飞蚊、视野缺损）、ent（鼻塞流涕、咽痛、耳鸣、鼻出血、吞咽困难）、endocrinology（多饮多尿、体重改变、怕冷乏力、血糖异常、甲状腺肿）",
    "红旗征象（red_flag 与 immediate_human 的触发源，须逐项覆盖）：胸痛、意识改变或晕厥、大出血（呕血/黑便/阴道流血）、呼吸困难（SpO2<94% 或说话不能成句）、剧烈头痛伴喷射性呕吐、持续高热 >3 天伴精神萎靡、婴幼儿高热惊厥、孕产出血或腹痛、咯血",
    "紧急度档（acuity 三档全覆盖）：0 非紧急可择期（复诊、慢病随访、常规体检咨询，且 immediate_human=false）、1 亚急性需数日内就诊、2 急性需当日就诊（red_flag=true 时必须为 2）",
    "特殊人群：婴幼儿、儿童、青少年、成人、老年、孕产妇、哺乳期女性",
    "就诊渠道：线下门诊导诊台、互联网医院图文问诊、电话分诊、自助机、基层转诊",
    "主诉风格与长度：一句话、三句话、大量口语与方言、完全口语化、夹医学术语、患者自述与护士记录混合",
    "一主诉跨多科室（须按优先级仲裁而非罗列全部）：胸闷伴气促与出汗（cardiology 优先于 general_medicine）、腹痛按部位区分（上腹/右上腹/脐周/下腹）、眩晕伴恶心（neurology）、发热伴咳嗽（14 岁以下判 pediatrics）",
    "生命体征：已测且正常、已测且异常、未知（多数线上场景缺失）、SpO2 下降、血压极高、心率过速",
    "既往史：无特殊病史、慢病多病共存、术后、肿瘤治疗中、长期服药、孕产史",
    "边界情形：罕见科室主诉、单症状可挂多科而无明确指向（判 general_medicine）、症状已缓解但要求复查、明确要求指定某科室"
  ]
}
', 'medical', 6, '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00') ON CONFLICT(slug) DO NOTHING;
