"""docs/domains 五领域 spec 的登记与派生：领域清单、轨制判定、中英标签、README 交叉校验。

控制台建库播种（`db.Store.seed_scenarios`）与导入脚本（`scripts/import_domain_specs.py`）都从这里
取「有哪些领域、有哪些场景、每个场景走哪条轨、spec 文件在哪」，不再依赖 `run_matrix.SCENARIOS`
（那份清单只含 docs/medical 的 10 个医疗场景，且已被 docs/domains 取代）。

轨制（`scenarios.track`）四值，与 docs/domains/README.md §1 的「轨制」列一一对应：
- `rule`     规则生成轨：spec.generator 九件套由 `generators/engine.py` 确定性采样、rules
             first-match 算标签；legacy 的 `generators/gen_<场景>.py` 专用脚本是同一轨的代码形态。
- `distill`  蒸馏轨：`generator.module = null` + `distill` 块 + `kev/console/distill/configs/<slug>.yaml`
             的 EasyDistill 五阶段流程（LLM 永不接触标签）。
- `both`     两轨都有（4 个 legacy 医疗场景：triage、diagnosis、medication-review、record-summary）。
- `llm`      直连 LLM 生成（icd-coding）：既无生成器也无 EasyDistill yaml，走
             `skills/kev-finetune/scripts/generate_data.py`，标签来自 LLM，靠金标审计把关。

判定只看代码与文件的存在性（spec 的 generator/distill 块、`gen_<slug>.py`、`configs/<slug>.yaml`），
不看注释；README 的轨制列作为交叉校验源，两者不一致即报错，避免文档与库内事实分叉。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from . import paths

DOMAINS_DIR = paths.ROOT / "docs/domains"
DOMAINS_README = DOMAINS_DIR / "README.md"
DISTILL_CONFIGS = paths.ROOT / "kev/console/distill/configs"

TRACK_RULE = "rule"
TRACK_DISTILL = "distill"
TRACK_BOTH = "both"
TRACK_LLM = "llm"
TRACKS = (TRACK_RULE, TRACK_DISTILL, TRACK_BOTH, TRACK_LLM)

# README §1 的「轨制」列文案 -> track 码
README_TRACK = {
    "规则生成": TRACK_RULE,
    "蒸馏": TRACK_DISTILL,
    "规则生成 + 蒸馏": TRACK_BOTH,
    "蒸馏（直连 LLM）": TRACK_LLM,
}
TRACK_LABEL = {code: text for text, code in README_TRACK.items()}

# 规则生成轨的引擎硬约束（spec §3.2 九件套）。出现任意一件即认为该 spec 可走 engine.py。
RULE_GENERATOR_KEYS = frozenset({
    "fields", "selectors", "tier_windows", "contexts", "patients",
    "rules", "augmentation", "plan_targets", "panel_category",
})

# 直连 LLM 生成轨（无生成器、无 EasyDistill yaml）：generators/README.md §「没有生成器的场景」
LLM_DIRECT = frozenset({"icd-coding"})

# 两个 legacy 场景自己不配 yaml，而是作为别的蒸馏场景的标签来源
# （kev/console/distill/make_seeds.py::SCENARIOS：inquiry 用 gen_triage、medication 用
#  gen_medication_review），所以它们同样「有蒸馏轨可用」。
DISTILL_LABEL_SOURCE = {"triage": "inquiry", "medication-review": "medication"}

# (slug, spec_dir, label_zh, label_en, sort)：五个领域。spec_dir 是 docs/domains 下的目录名，
# 落库为 scenario_domains.spec_dir，导入按它认领/新建域行。sort 只用于新建行（已有行不动）。
DOMAIN_REGISTRY = (
    ("medical", "medical", "医疗", "Medical", 0),
    ("finance", "finance", "金融", "Finance", 10),
    ("education", "education", "教育", "Education", 20),
    ("science", "science", "科研", "Research", 30),
    ("law", "law", "法律", "Law", 40),
)

# 旧库里由用户手工建的域可能用了别的 slug（「research」＝本目录的 science）。按 spec_dir 认领既有行，
# 不再插一条同义域；认领后把 spec_dir 写回该行。
LEGACY_DOMAIN_SLUGS = {"science": ("research",)}

# 30 个规则轨/legacy spec 里没有 label_zh/label_en（蒸馏轨的 31 个有），导入时按这里补齐；
# 医疗 legacy 7 条沿用控制台原有叫法，免得新建库与既有库显示不一致。
# 其余场景的中文名以 docs/domains/README.md §1 为准（readme_scenarios() 解析）。
FALLBACK_LABELS = {
    # ---- 医疗（legacy 7 + 引擎 3）----
    "critical-value": ("危急值", "Critical Value"),
    "diagnosis": ("诊断", "Diagnosis"),
    "icd-coding": ("ICD 编码", "ICD Coding"),
    "medication-review": ("用药审查", "Medication Review"),
    "nursing-quality": ("护理质量", "Nursing Quality"),
    "record-summary": ("病历摘要", "Record Summary"),
    "triage": ("分诊", "Triage"),
    "follow-up-tier": ("出院随访分级", "Follow-up Tiering"),
    "infection-report": ("感染上报分诊", "Infection Report Triage"),
    "transfusion-review": ("输血审核", "Transfusion Review"),
    # ---- 金融 ----
    "fin-aml-alert": ("反洗钱预警复核", "AML Alert Review"),
    "fin-collection-tier": ("催收分级", "Collection Tiering"),
    "fin-credit-doc-review": ("信贷资料完整性", "Credit Document Review"),
    "fin-fraud-claim-review": ("欺诈理赔复核", "Fraud Claim Review"),
    "fin-kyc-review": ("客户尽调资料复核", "KYC Due Diligence Review"),
    "fin-transaction-anomaly": ("异常交易识别", "Transaction Anomaly"),
    "fin-underwrite-triage": ("核保分诊", "Underwriting Triage"),
    # ---- 教育 ----
    "edu-admission-screen": ("招生材料预检", "Admission Material Precheck"),
    "edu-cheating-risk": ("考试行为异常识别", "Exam Misconduct Risk"),
    "edu-early-warning": ("学业预警", "Academic Early Warning"),
    "edu-question-classify": ("试题分类定级", "Question Classification"),
    # ---- 科研 ----
    "sci-experiment-normalize": ("实验记录规范化", "Experiment Record Normalization"),
    "sci-metadata-fair": ("FAIR 元数据评分", "FAIR Metadata Review"),
    "sci-reproducibility": ("可复现性预检", "Reproducibility Precheck"),
    "sci-software-archive": ("软件存档合规", "Software Archive Review"),
    "sci-topic-identification": ("研究主题识别", "Research Topic Identification"),
    # ---- 法律 ----
    "law-compliance-obligation": ("合规义务分级", "Compliance Obligation Tiering"),
    "law-contract-risk": ("风险条款分级", "Risk Clause Tiering"),
    "law-evidence-chain": ("证据链完整性", "Evidence Chain Integrity"),
    "law-regulation-watch": ("监管新规影响分级", "Regulation Watch"),
}


@dataclass(frozen=True)
class Domain:
    slug: str
    spec_dir: str
    label_zh: str
    label_en: str
    sort: int


@dataclass(frozen=True)
class SpecEntry:
    """一份 spec 文件落库前的全部事实（db.seed_scenarios 逐条 upsert）。"""
    domain: Domain
    slug: str
    label_zh: str
    label_en: str
    spec_path: str          # 仓库相对 posix 路径（scenarios.spec_path）
    track: str              # rule | distill | both | llm | ''
    generator_kind: str     # engine | script | ''
    distill_yaml: str       # 仓库相对 posix 路径或 ''
    sort: int               # 域内序号（按文件名排序）
    content: str            # spec 文件原文 -> scenarios.spec_json


def domains() -> list[Domain]:
    return [Domain(*row) for row in DOMAIN_REGISTRY]


def domain_for_spec_dir(spec_dir: str) -> Domain | None:
    for domain in domains():
        if domain.spec_dir == spec_dir:
            return domain
    return None


def spec_files() -> Iterable[tuple[Domain, Path]]:
    """docs/domains/<spec_dir>/specs/*.json，按领域清单顺序 + 文件名排序（决定 scenarios.sort）。"""
    for domain in domains():
        directory = DOMAINS_DIR / domain.spec_dir / "specs"
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.json")):
            yield domain, path


def generator_script(slug: str) -> Path:
    """legacy 代码形态的规则轨脚本：gen_<slug 连字符转下划线>.py。"""
    return paths.GENERATORS / f"gen_{slug.replace('-', '_')}.py"


def distill_yaml_for(slug: str, spec: dict) -> str:
    """该场景的 EasyDistill 配置（仓库相对 posix 路径），没有则 ''。

    `_meta.source_yaml` 是 spec 自己的声明（蒸馏轨必填），其次按文件名约定找
    `configs/<slug>.yaml`；legacy 双轨场景（triage / medication-review）自己没有 yaml，
    标签由 inquiry / medication 的蒸馏配置复用，故指向那份配置。
    """
    declared = (spec.get("_meta") or {}).get("source_yaml") or ""
    if declared and (paths.ROOT / declared).is_file():
        return str(Path(declared).as_posix())
    own = DISTILL_CONFIGS / f"{slug}.yaml"
    if own.is_file():
        return own.relative_to(paths.ROOT).as_posix()
    surrogate = DISTILL_LABEL_SOURCE.get(slug)
    if surrogate:
        other = DISTILL_CONFIGS / f"{surrogate}.yaml"
        if other.is_file():
            return other.relative_to(paths.ROOT).as_posix()
    return ""


def derive_track(spec: dict, slug: str) -> tuple[str, str, str]:
    """返回 (track, generator_kind, distill_yaml)，全部由代码/文件存在性推出。"""
    gen = spec.get("generator")
    gen = gen if isinstance(gen, dict) else {}
    has_engine = bool(set(gen) & RULE_GENERATOR_KEYS)
    has_script = generator_script(slug).is_file()
    yaml_path = distill_yaml_for(slug, spec)
    has_distill = bool(spec.get("distill")) or bool(yaml_path)

    if slug in LLM_DIRECT:
        track = TRACK_LLM
    elif has_engine or has_script:
        track = TRACK_BOTH if has_distill else TRACK_RULE
    elif has_distill:
        track = TRACK_DISTILL
    else:
        track = ""

    if has_engine:
        kind = "engine"
    elif has_script:
        kind = "script"
    else:
        kind = ""
    return track, kind, (yaml_path if has_distill else "")


def readme_scenarios() -> dict[str, tuple[str, str, str]]:
    """解析 docs/domains/README.md §1 的五张表 -> {slug: (领域 slug, 中文名, 轨制文案)}。

    表行形如 `| fin-aml-alert 反洗钱预警复核 | 规则生成 | ✅ |`，领域来自其上的
    `### 金融（finance，12 ✅）` 小标题。
    """
    out: dict[str, tuple[str, str, str]] = {}
    domain = ""
    for line in DOMAINS_README.read_text(encoding="utf-8").splitlines():
        head = re.match(r"^### .*（([a-z]+)，", line.strip())
        if head:
            domain = head.group(1)
            continue
        cells = [c.strip() for c in line.strip().split("|")]
        if len(cells) < 4 or not cells[1] or cells[1] == "场景":
            continue
        parts = cells[1].split(" ", 1)
        if len(parts) != 2 or not re.fullmatch(r"[a-z][a-z0-9-]*", parts[0]):
            continue
        out[parts[0]] = (domain, parts[1], cells[2])
    return out


def entries() -> list[SpecEntry]:
    """全部 spec 文件的落库事实（读文件一次，约 30 ms）。"""
    readme = readme_scenarios()
    out: list[SpecEntry] = []
    per_domain: dict[str, int] = {}
    for domain, path in spec_files():
        content = path.read_text(encoding="utf-8")
        spec = json.loads(content)
        slug = spec.get("name") or path.stem
        if slug != path.stem:
            raise ValueError(f"{path}: spec.name={slug!r} 与文件名 {path.stem!r} 不一致")
        track, kind, yaml_path = derive_track(spec, slug)
        zh = spec.get("label_zh") or ""
        en = spec.get("label_en") or ""
        if not (zh and en):
            fallback = FALLBACK_LABELS.get(slug)
            if fallback is None:
                listed = readme.get(slug)
                fallback = (listed[1] if listed else slug, slug)
            zh = zh or fallback[0]
            en = en or fallback[1]
        sort = per_domain.get(domain.slug, 0)
        per_domain[domain.slug] = sort + 1
        out.append(SpecEntry(
            domain=domain, slug=slug, label_zh=zh, label_en=en,
            spec_path=path.relative_to(paths.ROOT).as_posix(),
            track=track, generator_kind=kind, distill_yaml=yaml_path,
            sort=sort, content=content))
    return out


def audit() -> list[str]:
    """结构与文档一致性检查，返回问题清单（空列表 = 干净）。导入脚本据此决定退出码。"""
    problems: list[str] = []
    readme = readme_scenarios()
    found = {e.slug: e for e in entries()}
    for slug in sorted(set(readme) - set(found)):
        problems.append(f"README 列了 {slug}（{readme[slug][0]}），docs/domains 下没有对应 spec 文件")
    for slug in sorted(set(found) - set(readme)):
        problems.append(f"{slug} 有 spec 文件但未登记进 README §1 的清单表")
    for slug, entry in sorted(found.items()):
        spec = json.loads(entry.content)
        missing = [f for f in ("name", "domain", "state", "questions") if not spec.get(f)]
        if missing or not isinstance(spec.get("questions"), dict) or not spec.get("questions"):
            problems.append(f"{slug}: spec 缺少必要字段 {missing or ['questions']}")
        if not entry.track:
            problems.append(f"{slug}: 判不出轨制（无 generator/distill 块，也无 gen_*.py 与 yaml）")
            continue
        listed = readme.get(slug)
        if listed is None:
            continue
        if listed[0] != entry.domain.slug:
            problems.append(f"{slug}: README 归在 {listed[0]}，文件实际在 docs/domains/{entry.domain.spec_dir}/specs")
        expected = README_TRACK.get(listed[2])
        if expected is None:
            problems.append(f"{slug}: README 轨制文案 {listed[2]!r} 无法识别")
        elif expected != entry.track:
            problems.append(f"{slug}: 轨制不一致 README={listed[2]}({expected}) 派生={entry.track}")
    for domain in domains():
        if not (DOMAINS_DIR / domain.spec_dir / "specs").is_dir():
            problems.append(f"领域 {domain.slug} 缺少目录 docs/domains/{domain.spec_dir}/specs")
    return problems


if __name__ == "__main__":  # pragma: no cover - 手工核对用
    from collections import Counter
    rows = entries()
    print(f"{'domain':10s} {'slug':26s} {'track':8s} {'kind':7s} yaml")
    current = None
    for e in rows:
        if e.domain.slug != current:
            current = e.domain.slug
            print(f"--- {current}（{e.domain.label_zh}）")
        print(f"{e.domain.slug:10s} {e.slug:26s} {e.track:8s} {e.generator_kind:7s} {e.distill_yaml}")
    print(Counter(e.track for e in rows))
    for problem in audit():
        print("PROBLEM:", problem)
