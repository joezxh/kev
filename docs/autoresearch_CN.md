# 运行一个无人值守的研究会话

这是一个在没有人类盯着看的情况下运行的研究会话的操作手册：一个通宵会话，或白天的一段长时间交接。它取代了逐夜的提示词（第 6 轮和 night-3 程序，保留在 git 标签 `research-archive-2026-09-24` 下的 `docs/prompts/` 中），并把那些夜晚出错的地方也一并纳入。它所应用的研究规则在 [`PLAN.md`](../PLAN.md) 的「Standing rules for every round（每一轮的常设规则）」中；命令在 [`AGENTS.md`](../AGENTS.md) 中。

一个会话会在注册的规则下做爬山（hill-climbing）并确认，并留下一份 Jared 可以采取行动的记录。它不会发布。

## 1. 开始

头 30 分钟用来阅读，而不是启动。

1. `AGENTS.md`，通读全部（命令、冻结套件、canonical homes、Modal 设置）。
2. `PLAN.md`：我们所处的位置、我们学到了什么、常设规则、数据策略以及 Next。对于你想在其基础上构建的发现，到归档中阅读它的证据：`git show research-archive-2026-09-24:PLAN.md`。
3. `.agents/skills/` 中的技能：`kev-modal-study`（启动、观察和拉取 GPU 工作；阅读它的 Gotchas）、`kev-verify`（证明一次代码改动没有回归）、`kev-pr-description`（在任何 PR 之前）、`thermonuclear-code-review`。
4. `kev/rounds.py`（它的 docstring 就是 spec 的 schema）、`experiments/rounds/` 中最接近的过往 spec，以及 `kev/autoresearch.py`（`session`）。
5. 交接本身：授权（Modal 费用额度、AI Gateway 费用额度）、范围内有哪些、哪些需要 Jared。

然后做如下设置：

- 在一个研究分支的 worktree 中工作（`git worktree add -b research/<session> /tmp/kev-<session> origin/main`）。每次提交后都 push，这样即使机器休眠也不会丢失任何东西。用于 main 的代码走它自己经过审查的 PR。
- 阅读 `uv run modal billing summary --json`，把 `metered_cost` 作为基线记录到状态文件（第 6 节）中。
- 如果上一个会话留下了状态文件，先读它并从它恢复；脱离（detached）的 Modal 作业会在没有你的情况下继续运行。

## 2. 预算与支出规则

- 授权额度是整个会话的总额，要把仍在运行的一切都算进去。在**每一次**启动之前，重新读取计量费用，如果 `(metered_now - baseline) + sum(仍在运行的每一项的准入上限) >= 授权额度`，就不要启动。
- 一个 study 的准入上限会在启动时打印出来并保存到 `runs/<study>.spawn.json`；一次 benchmark 调用的上限是 `compute_bound(gpu, timeout, trials)`（`kev/budget.py`）。一个 spec 的 study `budget` 必须至少等于它的上限（`kev.rounds validate` 会检查它；`modal_app.admit_study` 会在任何东西运行之前拒绝一个超过其预算的 study，并且一个 study 的上限是 $250 和 28,800 s）。
- 保留一笔储备金（约为授权额度的 10%），任何阶段计划都不许动用它：计费读数是滞后的并且会被修订，而且准入上限会严重高估读数（一个读取批次带着它最慢那个作业的 timeout）。
- 把每一次读数和它的 UTC 时间一起记录到状态文件中。AI Gateway 支出（Jev 参考读取、label judges）有自己的上限，由花掉它的脚本来强制执行，并记录在 `runs/<name>/usage.json` 中。
- Modal workspace 的支出上限只能从 dashboard 提升；撞到它会让正在运行的容器在训练中途中被杀掉。

## 3. 注册一轮

一轮是一个 PLAN.md 章节加一个 spec，在任何训练或读取之前一起提交。

1. 写 PLAN.md 章节：为什么（测量到的差距及其证据）、数据（先冻结，带有 manifests）、各个 arm、规则（primary，以及按每个套件设定阈值的 guards、rank）、确认阶段和预算。使用常设规则；不要为某一轮发明一个新的统计量。
2. 通过复制最接近的过往 spec 来写 `experiments/rounds/r<N>.json`（联合 delta 用 r15，27B 用 r17，skills 轮用 r10，无训练的 post-hoc arm 用 r20：一个 temperature 池、插值 checkpoints；朝另一个 checkpoint 混合的 blend 用 r23，其 arm 为两个端点的训练都命名 `trained_on`）。去掉 `"archive"`：那个键标记的是已记录的 5-18 轮。spec 点名的每一个 plan 文件，以及它的规则所需的每一个 parent 读取，都必须存在于这个 checkout 中；如果一个 parent 缺少读取，用 `launch-reads <spec> --parents` 来补上。去掉对每一个已移除套件的读取（`kev.suite.REMOVED_SUITES`，带理由）：`evals/external/scienthoon-v1` 在 2026-09-27 被移除，所以从 23 轮起，scienthoon 的读取、panel 和 guard 都去掉；`evals/external/wanli-v2` 和 `typesafe-v1` 在 2026-09-30 被移除，所以从 27 轮起它们的读取也去掉，而 SemIf 是仅剩的一个外部读取（只做报告）。汇总后的外部套件不是一道门：23 轮那经过审计的规则（23-26 轮都沿用）把 SemIf、WANLI-v2 和 TypeSafe 报告为可选 panel。`validate` 和 `launch` 会拒绝在套件仍以它命名的最后一轮之后还有该套件的轮次。
3. 新数据是在 `evals/` 下带一个 `manifest.json`（每个文件的 sha256、输入的哈希）的新目录。在 SFT 数据策略（PLAN.md）下，私有语料只在 git 中保留 manifest，带一个指向私有数据集的 `"mirror"` 条目。
4. **必须（MUST）：每一个被服务或发布的 temperature 都来自一个留出（held-out）数据集的池，绝不能是训练语料的一个划分。** 一个读取校准（ECE、Brier、confident errors、coverage）的轮次，会为它的 arm 注册一个 `temperature` 池（复制 r20：transfer-r3 校准划分的八个留出公开来源 + transfer-v9 MMLU-Pro），而一个发布会把 `scripts/calibrate_checkpoint.py` 在同一池上拟合出来的 temperature 一起发布。训练来源的留出*条目*（一个训练套件的 `calibration` / `development` 划分）是在分布内的：19 轮在 T 0.955 上服务了它的 SFT arm，该 T 是在 `sft-v1` 的 development 行上拟合的，并且每一项校准标准都失败了（breadth-v1 ECE 0.059）；20 轮的留出数据集池在同一个 checkpoint 上给出了 0.0085。强制它的是：
   - 从 21 轮起，`kev.rounds validate` 和 `launch` 会拒绝一个轮次，如果它的规则或确认里有一条 temperature 会移动的判据（ECE、Brier、NLL、confident errors、coverage；除了 accuracy 之外的任何东西）却没有 `temperature` 池。小于等于 20 的轮次只对每个在训练语料上训练的 arm 打印一条 `!!! warning`，所以它们记录的 spec 仍然能通过 validate。
   - `kev.rounds validate` 会拒绝一个池读取，如果它 (a) 是某个 arm 的训练套件、它的一个组成部分（sft-v1 的 `inputs.components`）或它 plan 的 `data` 套件，(b) 池化了一个有任何 arm 训练过的来源，或 (c) 读取了任何训练语料的 `calibration` 或 `development` 划分；它还会拒绝一个它无法检查的池（训练未知的 arm、没有 manifest 或列出了来源的套件）。没有 trial 的 checkpoint arm 可以命名 `trained_on`。
   - 读出（read-out）记录每个 arm 的 `temperature_source`；对于一个在服务时用了它某次 trial 的开发行的训练语料的 arm，表格打印 `!!!`（5-19 轮都是；从现在起，这样的 temperature 只用于筛选）。
   - `scripts/calibrate_checkpoint.py` 会拒绝相同的拟合集合（对照 head.pt 的训练套件来检查）；`--allow-in-distribution` 仅用于复现一次旧的拟合，并且它会被记录到 `head.pt["temperature_fit"]` 中。
   - 一次 trial 的 in-trial temperature（`result.json` 的 `calibration_fit`）写的是 `role: in-trial screening ... not a served or shipped temperature`（在 trial 内的筛选……不是被服务或被发布的 temperature）。
   - Parent 是在为它们 trial 的开发行拟合出来的 temperature 上服务的（对于 Kev-27B，那就是它发布的 1.38，在同一行上拟合出来）；读出记录这一点以及它们发布的 head.pt T（`parent_temperature_source`），并且当一个训练语料的行上两者相差超过 0.05 时，`validate` 会告警。
   - 不相交性检查是按来源*名称*（名义上的，而非语义上的）：两个用不同名字携带相同数据集的套件能通过它。所以一个池必须使用在 Kev 中按构造为只用于评估的来源，比如 transfer-r3 的八个留出公开来源和 transfer-v9 的 MMLU-Pro。一个池读取的 `sources` 白名单必须点名它的套件列出的来源（拼写错误是个问题），而训练检查器无法列出的（一个在 `evals/` 之外的 `data` 文件、一个没有来源的 manifest）对新一轮来说也是个问题。
   - `calibrate_checkpoint.py --temperature T`（一个手动值，没有拟合）需要 `--reason`，记录在 `head.pt["temperature_fit"]` 中（例如「copied from the pool fit of runs/r20-readout」）。
5. `uv run python -m kev.rounds validate experiments/rounds/r<N>.json`（加上 `--partitions` 来验证划分）直到它打印 `ok`。把 PLAN 章节和 spec 在一次提交中提交，并 push。那次提交的时间就是注册时间。

## 4. 端到端地运行它

```bash
KEV_GPU=H200 uv run modal deploy modal_app.py                     # 在 kev/*.py 有任何改动或 evals/ 下有任何新文件之后
uv run python -m kev.rounds launch experiments/rounds/r<N>.json   # 每个 study 一个 ::study，间隔 60 s，日志在 runs/<study>.log
caffeinate -i nohup uv run python -m kev.rounds watch experiments/rounds/r<N>.json > runs/r<N>.watch.log 2>&1 &
```

- 在每个 study 的头五分钟里，在 `modal container logs <id>` 中数每分钟的优化器步数，并对照 timeout 推算墙钟时间（`ep0 step N/M`：M 是所有 epoch 的总和）。一个超时的容器什么都不会保存；取消（`FunctionCall.from_id(cid).cancel()`）并用一个新的 study 名字、更少的记录或更长的 timeout 重新启动。
- `watch` 轮询 spawn 出来的 trial，拉取每一个完成的 study（一次只拉一个 study），为那个 arm 启动一次读取（每个 arm 一次批量的 `::benchmarks` 调用，间隔 60 s），等待它们完成，并写出 `runs/r<N>-readout/round<N>.json` 和一张表格。它可重启：状态在 `runs/<study>.watch.json` 中，启动意图在 `runs/r<N>-reads-<arm>.json` 中。手动做法：`launch-reads <spec> [--arms a,b] [--parents] [--dry-run]`、`readout <spec>`。
- 把读出写入 PLAN 章节：每一个 arm、带区间的每一条判据、结论以及失败的内容。
- **确认是刻意的，绝不自动。** 对于读出点名的候选，把选择写进 PLAN.md 并提交，然后按每个阶段：`launch-reads <spec> --stage <stage> --arm <arm>`，然后 `confirm <spec> --stage <stage> --arm <arm>`（→ `runs/r<N>-verdict/<size>-<stage>.json`）。在锁定读取之前先测 panel。每个只读一次，没有例外。
- 在一个上限之下连续多个已注册的轮次：`uv run python -m kev.autoresearch session experiments/rounds/r19.json [...] --spend-start <baseline> --spend-cap <authorization>`。它校验、启动并观察每一轮直到它的读出，在一个会让预算越过上限的轮次之前停下，追加到 `runs/autoresearch-sessions.jsonl`，并打印确认命令；它从不运行这些命令。`kev.autoresearch leaderboard` 刷新 `runs/leaderboard.{jsonl,md}`（不提交），`compare` 在 transfer accuracy 上把 trial 与某个参考配对，`release-check --study <name>` 筛选该研究中的每一个 config（每个 config 只有在它的所有 seed 都通过各自的门时才算通过）。

## 5. 一个会话可以碰和不可以碰什么

可以：写 spec、plan 和 PLAN.md 章节；在新的目录下构建新的冻结数据；通过 `modal_app.py` 启动 study 和读取；改动脚本和 `modal_app.py` 的基础设施常量；为属于 main 的代码开 PR。

未经 Jared 明确同意，不可以：

- 发布或改动 Hub 上的任何东西（`kev.publish`、`hf upload`、`hf repos tag`、`scripts/publish_space.sh`、一个已发布的 `head.pt`）、把一个私有 repo 变公开，或部署一个公开端点；
- 提交到 main、force-push，或合入一个 PR（代码通过经过审查、squash 合入的带绿色 CI 的 PR 进入 main）；
- 编辑 `evals/` 下存在的任何东西（冻结的），或评估器：`kev/experiment.py: EVALUATOR_FILES`、那些门、`kev/metrics.py`、`kev/rounds.py` 的配对读取。一个需要的评估器改动是它自己的 PR，在任何轮次依赖它之前，用 `kev-verify` 和 `tests/test_rounds.py` 验证；
- 在已注册的确认阶段之外传递 `--allow-test` 或运行 `locked_test`；
- 把任何 Jev 输出，或任何闭源模型的生成内容，放进训练数据；
- 在本地训练（一台 32 GB 的 Mac 装不下这些模型），或在一台机器上跑两个训练进程；
- 从 runs 卷中删除一个 checkpoint 或一个 snapshot（`modal volume rm`、容器里的 `shutil.rmtree`），或在一个已注册的 spec 中关闭一个 full-weight trial 的 snapshot（`"snapshot_fractions": "none"`）。Full-weight trial 在它们步数的 0.25、0.5 和 0.75 处保留 snapshot（`kev.experiment.SNAPSHOT_FRACTIONS`），这样一次读取能在一次运行结束后找到该运行的最佳点：19 轮不能，因为唯一的中途状态是一个 resume 点，在运行结束时被删除了，而 AutoJev 的最佳 checkpoint 在 0.7 个 epoch 处。一个 27B 的 snapshot 每个 trial 约为 154 GB 的卷空间；这个空间是 Jared 的决定，不是会话的决定。Snapshot 存放在 runs 卷（主存储）上；一个私有 Hub 镜像（一个 plan 中的 `snapshot_hub_repo`，或 `modal_app.py::mirror_snapshots`）是对于一个值得保留的 checkpoint 的长期存储，而不是替代：把 27B checkpoint 做镜像（每个约 51 GB，进到一个私有 repo，例如 `jaredpalmer/kev-snapshots`）也是 Jared 的决定，而且绝不进公开 repo。

如果一个 arm 被卡住（认证、支出限额、一个 30 分钟内搞不定的部署），把发生了什么写下来，转到下一个 arm。不要等人类。

## 6. 韧性（Resilience）

- **状态文件** `runs/<session>-state.json`（`runs/` 被 gitignore；在研究分支上用 `git add -f` 加入它）：基线和授权额度、带 UTC 时间的支出读数、每个带 spawn id、上限和状态的 study、已启动和已拉取的读取、候选、PR、待定决策。在每次启动、拉取和读取之后更新它，并和 PLAN 章节一起提交。
- **脱离的作业（Detached jobs）。** Study 在已部署的应用上 spawn，并在本地客户端之外存活；`study` 之后的一次本地错误可能仍然已经 spawn 了 trial，所以在重新启动之前先运行 `modal container list`，并且绝不在同一个 study 名字下重新启动。Probe 和 benchmark 用 `--detach` 运行。
- **观察器是本地进程**，会随机器或网络一起死掉。在 `nohup` 和 `caffeinate` 下运行它们；在任何中断之后重启 `watch`（它从它的状态恢复）。它会自己重试 DNS 和连接错误；一个 trial 自己的异常是一次失败，会被报告。
- **超时的 full-weight trial 由观察器而非 Modal 继续。** Trial 在 Modal 的 retries 关闭的情况下 spawn；当一个 full-weight trial 的调用因它的 timeout 而结束时，`watch` 运行 `modal_app.py::resume --trial <label>`，它会用该 study 被准入时所用的 GPU 和 timeout spawn 下一次尝试（它从上一个已提交的 resume 点继续），并记录到 `runs/<study>.spawn.json`（`attempts`，每个 trial 最多 1 + `kev.budget.FULL_FT_RETRIES`，这个计数就是准入上限计算所用的；一个当前调用仍在运行的 trial 永远不会被继续）。在观察器宕机期间什么都不会被继续：重启它，它就会把 timeout 接管过去。原因：Modal 对每个超时的尝试收了两次费（先是 timeout，然后是它在 30 s 后杀掉的任务），所以 `Retries(2)` 给了 22 轮那个 trial 三次尝试中的两次，而且 kill 的重试可能在一个正在运行的尝试旁边启动（`scripts/modal_retry_probe.py`）。一个在账本（ledger）之前 spawn 的 study 没有计数：`resume --trial <label> --beyond-bound` 在边界之外手动继续它，并如实说明。两个尝试绝不会共享一个 trial：每一个在它 spawn 之前就被记录为 pending，并且每一个都持有对 `kev-leases` 卷的租约（每分钟一次心跳）；在另一个的租约还新鲜时，新的尝试会被拒绝；而一次继续会在被 kill 的尝试的最后一个心跳之后最多等待 `kev.budget.LEASE_STALE`（15 分钟）才 spawn。
- **网络掉线**会杀掉本地客户端，但不会杀掉远程工作：一个客户端死掉的读取在 Modal 上通常已经完成；从卷上拉取它的目录（`modal volume get kev-runs /<name> runs/<name>`），而不是重新启动它。
- 一次失败的 benchmark 或 probe 会把它的目录留在卷上；用一个新的名字重试。

## 7. 报告

在会话结束时（并且随着进行写入状态文件）：

- 每一轮的 PLAN.md 章节都带有它的注册、读出表格、确认结果和结论（无论是否为负面），以及报告路径。
- 更新 PLAN.md 的「Where we stand（我们所处的位置）」（已发布和已确认的候选、正在运行的作业、支出）和「What we have learned（我们学到了什么）」（如果有发现改变了的话）；把每一轮加入 Record 表。
- 在 PLAN.md 中写一份会话摘要：支出（基线、最终读数、正在运行的边界）、在 Modal 上待处理的东西以及完成它的确切命令、事件，以及至多三个带有证据的后续步骤。
- 每一个数字都带 checkpoint、套件和划分、n 和报告路径；提交这些数字所来自的读出和结论（`.gitignore` 保留报告，而不是预测转储；为新读出目录加一条规则）。
- 时钟戳：注册和结果时间是提交时间。在事件发生之前不要把一个时间写进标题；night 3 的 scratchpad 这么做了，于是它的时间戳没法用。

## 8. 已知的坑（Known gotchas）

- **Modal app-create 速率限制。** 一分钟内超过大约三次脱离的 `modal run` 会以「App create rate limit exceeded」失败，并且什么都不会运行。`kev.rounds` 把启动错开到间隔 60 s，并把一个 arm 的读取批处理成一次调用；手动时照做。
- **benchmark 作业中的 `repo@sha`** 曾经会移动 `run@suite@name@flags` 的每一个字段；`modal_app.parse_jobs` 现在从右边解析，所以固定的 Hub 修订是安全的。套件和名字不能包含 `@` 或 `,`。
- **每个 study 一次拉取。** 对同一个 study 的并发拉取会删除彼此的 trial 目录；`pull_study` 现在持有一个每个 study 的锁。在 trial 仍在运行时拉取是安全的，并且只刷新未完成的 trial。
- **拉取会把 full weight 留在卷上。** `::pull`（和 `watch`）会跳过 full-weight 分片（`model*.safetensors`，每个 27B checkpoint 或 snapshot 约 51 GB）和 resume 点；其他一切都下来（结果、行、`head.pt`、configs）。在卷上读取一个 checkpoint 或一个 snapshot：`::benchmarks --jobs "/runs/<study>/<trial>/snapshots/step-<N>/checkpoint@<suite>@<name>"`。`::pull --weights` 会在本地确实需要分片时复制它们。
- **在数据之后部署。** 镜像会复制 `evals/`；启动器只检查 `kev/*.py` 的哈希，所以一个数据文件在部署之后才被加上的 trial 会在容器内失败。`study` 上的 `--gpu H200` 需要一个用 `KEV_GPU=H200` 部署的应用。
- **27B。** 仅 H200（bf16 backbone，常驻 55 GB）；study timeout 最多 28,800 s（一个 lr 2e-5 的 1-epoch skills delta 大约每优化器步 8.8 s）；fp32 读取约为 9B 的约三倍（spec `read_timeout: {"27b": 14400}`）；锁定读取需要在 H200 上的 `--timeout 14400 --memory-mb 131072`（spec `locked_args`）（GPU 来自 spec 的 `gpu` / 已部署的应用，或手动 `--gpu H200`）。每一个 bf16-weights trial 都会失败于 in-trial 的 `isolation_and_packing` 门（一个 fp32 检查）；从行中读取结果，并在 bf16 下单独测量被服务的隔离度。
- **`locked_test` 命名。** 当一个 in-trial 筛选门失败时，该工具要求 `-ungated` 后缀（`kev-4b-r8-ungated`）；结论仍然遵循已注册的规则。
- **每个套件的读取超时。** `modal_app.READ_TIMEOUTS` 设置长状态 panel 7,200 s、documents 5,400 s、transfer-v9 3,600 s，其他为 1,800 s。一个全局的 `--timeout` 会膨胀批次中每个作业的准入上限。
- **预算准入。** 一个超过它的 `--budget` 的启动会在任何东西运行之前退出；用至少等于打印出来的上限的预算重新启动。
- **外部服务器是单飞的（single-flight）。** AutoJev 的服务器一次只应答一个请求（忙时 HTTP 529）；在一次长 `kev.benchmark --remote` 之前先探测一个外部端点，并把 `--remote-concurrency` 设成它能承受的值。把它拒绝的请求（例如超出它上下文的 422）算作覆盖率，绝不可静默丢弃。
- **Temperature：已发布 vs in-trial。** 一个 trial 的 `result.json` 和它的锁定摘要是在 in-trial 拟合下打分的；一个发布发布的是 `scripts/calibrate_checkpoint.py` 写入 `head.pt` 的那个 T。第一次 AutoJev 的 head-to-head 在 in-trial 的 1.19 而非发布的 1.38 上服务了 Kev-27B，并且不得不被纠正。说明每一个数字用的是哪个 T，以及它是在哪拟合的（第 3 节，规则 4：留出数据集，绝不训练语料自己的划分）。
- **长上下文校准。** 一个带 `"by_length": true` 的 panel 会按状态 token 桶（8k 以下到 64k+，以及 8k+/16k+/32k+ 的尾部）报告 accuracy、ECE、Brier 和 confident errors，并且一条判据可以门控其中一个（`long.ece_16k_plus.candidate <= 0.05`）。Token 从读取的套件记录计数，所以两边都共享桶。
- **不新开套件版本的套件修复。** 一个 panel 可以在两边丢弃来源、任务或一个（私有的、哈希注册的）id 或来源列表（`exclude_sources`、`exclude_tasks`、`exclude_file`），并且一个只做报告的 panel 被标记为 `"optional": true`，这样一次缺失的报告读取绝不会让一个候选变得不完整。在任何基于它们的读出之前，按 label 有效性来选择排除项（24 轮取自 2026-09-27 的审计），并且绝不提交一个私有列表。
- **Workspace 容量。** 该 workspace 同时最多跑过大约十个 GPU 容器；pending 的容器是容量问题，不是 bug，所以不要重新启动它们。
- **小套件。** 一个在 89 或 144 个问题上做的 guard 无法解决 2-3 pp 的底线；通过汇总 panel 来门控它们。
- **Jev 读取在运行中失败**于 gateway 503；用一个新名字重跑整个读取，而不是把部分行拼接起来。
- **软目标（Soft-target）数据。** 写 builder 时，用肉眼检查几条记录：`target` 求和为 1，并且 label 的 mass 至少为 0.5，除非该记录是不可知的（`kev.data.none_pair` 曾经在软目标上训练出零 mass，在 #60 中修复）。
- 把 `modal run ...::study` 的输出重定向到一个日志文件；一个过滤器可能隐藏掉解释为什么什么都没启动的 `SystemExit`。
