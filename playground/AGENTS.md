<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->

# playground

Next.js 16 app in the repo. Two distinct consumers share it:

- `/` `/chess` `/docs/[lang]` — the public demo (Q&A over System One, chess, docs viewer).
- `/console/**` — the **medical fine-tune console** (see below).

## 医疗微调控制台（`/console`）

A control plane for the 12-step medical pipeline in `docs/medical/`. It does not compute
anything itself: it composes `kev` CLI commands and streams their output.

### Ports and processes

| Process | Where | Port | Started by |
| --- | --- | --- | --- |
| `playground` | Windows or WSL2 | 3000 | `npm run dev` |
| `kev-console` (FastAPI orchestrator) | **WSL2**, same env as torch | 8790 | `uv run python -m kev.console` |
| `kev.serve` (System One inference) | WSL2 | 8008 | the `deploy` job |

The orchestrator lives in WSL2 on purpose: it then spawns `kev.train` as an ordinary local
subprocess — no `spawn("wsl.exe", …)` path/shell/stdio translation. Windows reaches it
through WSL2's localhost forwarding. It binds `127.0.0.1` only, with no auth (local
single-user).

`playground/src/app/api/console/[...path]/route.ts` is a thin same-origin proxy to `:8790`
(SSE must be piped chunk by chunk — buffering it makes `EventSource` see nothing until the
job ends). Target is `KEV_CONSOLE_API`, default `http://127.0.0.1:8790/console/api`.

### Where things live

```
src/app/console/           pages: overview, datasets, train, eval, images, deploy, jobs/[id]
src/app/api/console/       the proxy route
src/components/console/    ArgvPreview, JobStagePage, JobMonitor, LossChart, GatePanel,
                           JobTable, usePoll, format.ts (+ .test.ts), strings.ts
src/lib/console.ts         API client + EventSource wiring
```

`JobStagePage` carries the shape shared by all five stage pages: editable form on the left,
live argv preview + gate panel on the right. A stage page supplies its field specs.

### Rules that are easy to break

- **argv is always visible.** `ArgvPreview` is not decoration: the runbook's value is that
  the command is readable and auditable. Do not replace it with a "run" button alone.
- **Gates block, they do not retry.** A `422 gate` response is a configuration problem, so
  nothing is persisted and the UI expands `GatePanel` in place. Never auto-retry it.
- **Paired CI lives only in `comparison.json`.** `kev.benchmark` writes `paired_flip`, not
  `bootstrap`; `kev.compare` produces `paired.acc.ci95`. G4 therefore needs
  baseline + benchmark + compare, and `eval/page.tsx` must keep showing that order.
- **No credentials in the browser.** `/console/api/config` returns booleans only. A
  hardcoded `NEXT_PUBLIC_` key once shipped to the client through the bundle; do not
  reintroduce that.
- **Tests:** `npm run test:console` (Node's built-in runner + native type stripping).
  Do not add vitest — it fails to resolve against the pinned next 16.3.5 / react 19.2.8.

Before changing `kev/console/`, read
`docs/superpowers/specs/2026-10-04-medical-finetune-console-design.md`.