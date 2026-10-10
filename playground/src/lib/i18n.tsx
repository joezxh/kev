"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

import { CONSOLE_STRINGS } from "@/components/console/strings";

export type Lang = "en" | "zh";

type Dict = Record<string, { en: string; zh: string }>;

// UI strings. Placeholders use {name}; pass them via t(key, params).
// 控制台的文案合并进同一张表，保持 t() 单一入口 —— 不引入第二套 i18n。
const dict: Dict = {
  ...CONSOLE_STRINGS,
  // ---- kev tab ----
  "kev.tagline": { en: "Typed questions in, probabilities out, one forward pass.", zh: "类型化问题进，概率分布出，一次前向传播。" },
  "kev.intro": {
    en: "The state is read once. Every question is answered in parallel and cannot see the others. Each answer is a distribution over the options you supplied.",
    zh: "状态只读取一次。每个问题并行作答，彼此互不可见。每个答案都是你给定选项上的概率分布。",
  },
  "kev.stateLabel": { en: "State", zh: "状态" },
  "kev.stateHint": { en: "(text, or a JSON object or array)", zh: "（文本，或 JSON 对象/数组）" },
  "kev.questionsLabel": { en: "Questions", zh: "问题" },
  "kev.questionsHint": { en: "(noul, choice, score)", zh: "（noul、choice、score）" },
  "kev.tab.answers": { en: "Answers", zh: "答案" },
  "kev.tab.permute": { en: "Permutation", zh: "排列" },
  "kev.tab.json": { en: "JSON", zh: "JSON" },
  "kev.empty": { en: "Run the request to see one distribution per question.", zh: "运行请求后，这里会显示每个问题的一份分布。" },
  "kev.separate": {
    en: "One request with {n} questions: {m1} ms, {t1} tokens. {n} separate requests: {m2} ms, {t2} tokens. Largest probability difference between the two: {d}.",
    zh: "一次请求含 {n} 个问题：{m1} ms，{t1} tokens。{n} 次独立请求：{m2} ms，{t2} tokens。两者最大概率差：{d}。",
  },
  "kev.separate.ok": { en: "Sibling questions did not change any answer.", zh: "并列问题没有改变任何答案。" },
  "kev.separate.bad": { en: "This exceeds rounding; check the request.", zh: "差值超过舍入误差，请检查请求。" },
  "kev.perm.underN": { en: "under {n} option orders", zh: "在 {n} 种选项顺序下" },
  "kev.perm.caption": { en: "Probability of each option under different option orders", zh: "不同选项顺序下每个选项的概率" },
  "kev.perm.same": { en: "The top option is the same in every order.", zh: "无论选项顺序如何，最优选项都一致。" },
  "kev.perm.changes": { en: "The top option changes between orders.", zh: "最优选项随顺序而变。" },
  "kev.perm.order": { en: "Order", zh: "顺序" },
  "kev.perm.spread": { en: "Spread (max − min)", zh: "离散度（最大 − 最小）" },
  "kev.perm.foot": {
    en: "Each row is the same question with its options in a different order. A spread above 0.10 is shown in bold.",
    zh: "每一行是同一问题、选项顺序不同。离散度高于 0.10 以粗体显示。",
  },
  "kev.raw.request": { en: "Request", zh: "请求" },
  "kev.raw.response": { en: "Response", zh: "响应" },
  "kev.run": { en: "Run", zh: "运行" },
  "kev.running": { en: "Running", zh: "运行中" },
  "kev.packed": { en: "Packed vs separate", zh: "打包 vs 独立" },
  "kev.comparing": { en: "Comparing", zh: "对比中" },
  "kev.permute": { en: "Permute", zh: "排列" },
  "kev.permuting": { en: "Permuting", zh: "排列中" },
  "kev.packed.title": {
    en: "Answer every question in its own request, then compare with the packed answer",
    zh: "让每个问题各自独立请求，再与打包答案对比",
  },
  "kev.permute.title": { en: 'Re-ask "{id}" under 6 option orders', zh: "以 6 种选项顺序重新询问「{id}」" },
  "kev.questionWord": { en: "question", zh: "个问题" },
  "kev.questionsWord": { en: "questions", zh: "个问题" },
  "kev.inputTokens": { en: "input tokens", zh: "输入 tokens" },
  "kev.connecting": { en: "connecting", zh: "连接中" },
  "kev.backendUnavailable": { en: "backend unavailable: {error}", zh: "后端不可用：{error}" },
  "kev.nav.console": { en: "console", zh: "控制台" },

  // ---- chess tab ----
  "chess.tagline": { en: "Every move is a Choice question.", zh: "每一步都是一道选择题。" },
  "chess.intro": {
    en: "The legal moves are the options, the board is the state. The model returns a probability for each move and a Score for who is better, in one request. The model has never seen a chess game, so expect the distributions to be more interesting than the play.",
    zh: "合法走法是选项，棋盘是状态。模型在一次请求中为每个走法返回概率，并对局势优劣给出一个分数。模型从未见过真正的棋局，所以这些分布往往比实际走子更有意思。",
  },
  "chess.mode.self": { en: "Model vs model", zh: "模型对模型" },
  "chess.mode.white": { en: "You play White", zh: "你执白" },
  "chess.mode.black": { en: "You play Black", zh: "你执黑" },
  "chess.play": { en: "Play", zh: "开始" },
  "chess.pause": { en: "Pause", zh: "暂停" },
  "chess.step": { en: "Step", zh: "单步" },
  "chess.modelMoves": { en: "Model moves", zh: "模型走子" },
  "chess.undo": { en: "Undo", zh: "悔棋" },
  "chess.newGame": { en: "New game", zh: "新对局" },
  "chess.sample": { en: "Sample from distribution", zh: "按分布采样" },
  "chess.thinking": { en: "Model is choosing", zh: "模型正在选择" },
  "chess.yourMove": { en: "Your move ({side}). Click a piece, then a square.", zh: "轮到你走（{side}）。先点棋子，再点目标格。" },
  "chess.toMove": { en: "{side} to move", zh: "{side}走子" },
  "chess.check": { en: "check", zh: "将军" },
  "chess.moveTitle": { en: "Best move among {n} legal moves", zh: "在 {n} 个合法走法中挑选最佳" },
  "chess.moveTitlePlain": { en: "Best move among the legal moves", zh: "在合法走法中挑选最佳" },
  "chess.confidence": { en: "confidence {c}", zh: "置信度 {c}" },
  "chess.moreMoves": { en: "{n} more moves share the remaining {r}", zh: "另有 {n} 步瓜分剩余 {r}" },
  "chess.evalTitle": { en: "Who is better in this position?", zh: "当前局势谁占优？" },
  "chess.distAppears": { en: "The model's distribution appears here after its first move.", zh: "模型走第一步后，分布会显示在这里。" },
  "chess.options": { en: "options", zh: "个选项" },
  "chess.movesLabel": { en: "Moves", zh: "走法" },
  "chess.noMoves": { en: "No moves yet.", zh: "尚无走子。" },
  "chess.prevGames": { en: "Previous games (stored in this browser)", zh: "历史对局（存储在本浏览器）" },
  "chess.noneYet": { en: "None yet. Finished games are listed here.", zh: "暂无。已结束的对局会列在这里。" },
  "chess.plies": { en: "plies", zh: "半回合" },

  // ---- language toggle (label = language to switch TO) ----
  "lang.toggle": { en: "中文", zh: "English" },
};

type Ctx = { lang: Lang; setLang: (l: Lang) => void; t: (key: string, params?: Record<string, string | number>) => string };

const LangCtx = createContext<Ctx | null>(null);

const KEY = "kev.lang";

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>("en");

  useEffect(() => {
    const saved = typeof window !== "undefined" ? (localStorage.getItem(KEY) as Lang | null) : null;
    if (saved === "en" || saved === "zh") {
      setLangState(saved);
      document.documentElement.lang = saved;
    }
  }, []);

  const setLang = (l: Lang) => {
    setLangState(l);
    if (typeof window !== "undefined") {
      localStorage.setItem(KEY, l);
      document.documentElement.lang = l;
    }
  };

  const t = (key: string, params?: Record<string, string | number>) => {
    const entry = dict[key];
    const s = entry ? entry[lang] : key;
    if (!params) return s;
    return s.replace(/\{(\w+)\}/g, (_, n: string) => (params[n] !== undefined ? String(params[n]) : `{${n}}`));
  };

  return <LangCtx.Provider value={{ lang, setLang, t }}>{children}</LangCtx.Provider>;
}

export function useLang(): Ctx {
  const ctx = useContext(LangCtx);
  if (!ctx) throw new Error("useLang must be used within a LanguageProvider");
  return ctx;
}
