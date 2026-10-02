# 在 Modal 上部署 Kev

你自己的 Kev 端点，讲 TypeSafe 的 System One 协议，三条命令搞定。空闲时它会缩放到零，所以一个未使用的端点不花任何钱。

```bash
pip install modal && modal setup                  # 一次：在浏览器中登录 Modal
curl -LO https://raw.githubusercontent.com/jaredpalmer/kev/main/skills/kev-deploy/scripts/kev_serve.py
KEV_API_KEY=$(openssl rand -hex 24) modal deploy kev_serve.py
```

部署会打印 `https://<your-workspace>--kev-api.modal.run`。保存好这个 key：请求需要 `Authorization: Bearer <key>`。把任意 TypeSafe 客户端指向这个 URL：

```python
client = TypeSafeClient(api_key=KEV_API_KEY, base_url="https://<your-workspace>--kev-api.modal.run", model="kev-latest")
```

| Model | Set | GPU ($/h while up) | 6 个问题下的预热模型时间（新状态 / 重复状态） | 空闲后的首个请求 |
| --- | --- | --- | --- | --- |
| Kev-0.8B | `KEV_MODEL=jaredpalmer/kev-0.8b` | L4 (0.80) | 23 / 16 ms | ~40 s |
| Kev-4B (default) | nothing | L40S (1.95) | 42 / 28 ms | ~35 s |
| Kev-9B | `KEV_MODEL=jaredpalmer/kev-9b` | H100 (3.95) | 24 / 17 ms | ~55 s |
| Kev-27B | `KEV_MODEL=jaredpalmer/kev-27b` | B200 (6.25) | 47 / 32 ms | ~50 s |

并发请求在每个容器中被批处理（Kev-4B：在 H100 进程内大约 100 请求/秒）。通过 Modal 的 web 端点，一个容器上限大约 40-50 请求/秒，并且 Modal 在超过 32 个并发请求时逐个增加容器。`KEV_FLASH=1`（配合 `KEV_REGION`）使用 Modal 的实验性直接 HTTP 服务器：约 46 ms 的往返，而不是约 77 ms，并且保持一个容器常驻。

往返还要加上网络和 Modal 的代理（从美国到 us-east 的一个保持连接的容器大约 80-100 ms）；`KEV_REGION=us` 让容器贴近美国调用方。第一次部署还会下载权重并编译 kernel（1-2 分钟；Kev-27B 的 51 GB 要好几分钟）；之后的冷启动会复用缓存。

`KEV_MIN_CONTAINERS=1` 让它保持温热；`modal app stop kev` 把它关停。用 agent 时，`npx skills add jaredpalmer/kev@kev-deploy` 并让它部署 Kev；它遵循 [SKILL.md](SKILL.md)。`modal skills install` 会在一旁加入 Modal 自己的 agent 技能和文档，以处理本文件之外的事情（GPU、secrets、日志、billing）。
