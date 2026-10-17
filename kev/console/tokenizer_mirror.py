"""tokenizer 的本地镜像：Hub 不可达时 precheck 仍然能用**真实** tokenizer 跑。

为什么必须多这一层（G1 的前提是真实 token 计数，不能拿字符数凑）：

- `huggingface.co` 在本机被重置（curl: (35) Recv failure: Connection was reset）；
  `HF_ENDPOINT=https://hf-mirror.com` 本身可用，所以「换源」只有在 Hub 直连这条路彻底不通时才需要。
- 但预检照样会炸：`HF_HUB_OFFLINE=1`（PyCharm 的 `kev.serve` 运行配置、`deploy/.env` 都设了）时
  huggingface_hub 一律只读磁盘缓存，而 `jaredpalmer/kev-0.8b` 的缓存目录里只有 `refs/main`、
  一个 blob 都没有 —— 于是 `LocalEntryNotFoundError: Cannot find the requested files in the disk
  cache and outgoing traffic has been disabled`，`kev.model.load_tokenizer` 连带失败。
- 该 checkpoint 仓库本身**不带 config.json**（只有 tokenizer.json / tokenizer_config.json + adapter），
  transformers 会先 AutoConfig 再回退 tokenizer_config.json，所以只要 tokenizer 文件到位即可加载。

做法：把 tokenizer 需要的文件从可达的镜像拉到 `data/console/tokenizers/<owner>__<name>/`，
ModelScope 国内站优先（`jaredpalmer/kev-0.8b` 在那边有同步，基座 `Qwen/Qwen3.5-0.8B-Base`），
HF 镜像回落（受 `HF_ENDPOINT` 控制）。落盘目录随后当 `--init-from` 用，一个字节也不再联网。
文件按 ModelScope 清单里的 Size + Sha256 校验过，镜像与 Hub 内容一致才算数。

Run: python -m kev.console.tokenizer_mirror --model jaredpalmer/kev-0.8b
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from kev.console import paths

MODELSCOPE_API = "https://www.modelscope.cn/api/v1/models"
# ModelScope 对 urllib 默认 UA 会 403，浏览器 UA 最省事（curl 能直接下，说明链路本身没问题）。
USER_AGENT = "Mozilla/5.0 (compatible; kev-tokenizer-mirror/1.0)"

# AutoTokenizer 从一个目录里可能读到的全部文件。kev 的 checkpoint 仓库不带 config.json 也能加载
# （transformers 回退 tokenizer_config.json 的 tokenizer_class；已在 kev-4b 的 snapshot 上实测）。
TOKENIZER_FILES = ("config.json", "tokenizer_config.json", "tokenizer.json", "vocab.json",
                   "merges.txt", "added_tokens.json", "special_tokens_map.json", "chat_template.jinja")
# 源的顺序即优先级：ModelScope 国内可达且有 kev 的同步，HF 镜像作为它没有的模型（裸基座）的回落。
SOURCES = ("modelscope", "hub")


def mirror_dir(model, root=None):
    """某个 Hub 模型镜像到本地的目录（`owner/name` -> `owner__name`，与 data/console 同在 git 外）。"""
    return (Path(root) if root is not None else paths.TOKENIZER_MIRROR) / model.replace("/", "__")


def _open(url, timeout):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    return urllib.request.urlopen(request, timeout=timeout)   # noqa: S310 (固定 https 端点)


def modelscope_manifest(model, timeout=30.0):
    """ModelScope 仓库文件清单：`{仓库内路径: {"Size": int, "Sha256": str}}`（该站从 HF 同步而来）。"""
    url = f"{MODELSCOPE_API}/{model}/repo/files?" + urllib.parse.urlencode(
        {"Revision": "master", "Recursive": "true"})
    with _open(url, timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    files = ((payload.get("Data") or {}).get("Files")) or []
    return {entry["Path"]: entry for entry in files if entry.get("Type") == "blob"}


def from_modelscope(model, dest, timeout=180.0):
    """把清单里属于 TOKENIZER_FILES 的文件拉到 dest，按 Size + Sha256 校验。返回落盘文件名。"""
    manifest = modelscope_manifest(model)
    dest = Path(dest)
    written = []
    for name, entry in manifest.items():
        if name not in TOKENIZER_FILES:
            continue
        url = f"{MODELSCOPE_API}/{model}/repo?" + urllib.parse.urlencode(
            {"Revision": "master", "FilePath": name})
        with _open(url, timeout) as response:
            blob = response.read()
        expected_size, expected_sha = entry.get("Size"), (entry.get("Sha256") or "").lower()
        if expected_size is not None and len(blob) != expected_size:
            raise ValueError(f"{name}: got {len(blob)} bytes, manifest says {expected_size}")
        if expected_sha and hashlib.sha256(blob).hexdigest() != expected_sha:
            raise ValueError(f"{name}: sha256 differs from the manifest")
        target = dest / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(blob)
        written.append(name)
    return written


def from_hub(model, dest, allow_patterns=None):
    """从 HuggingFace 拉（`HF_ENDPOINT` 决定端点，hf-mirror.com 是国内可达的那个）。"""
    from huggingface_hub import snapshot_download

    return snapshot_download(repo_id=model, local_dir=str(dest),
                             allow_patterns=list(allow_patterns or TOKENIZER_FILES))


def fetch(model, sources=SOURCES, timeout=180.0, force=False, root=None):
    """按 sources 的顺序把 tokenizer 镜像到本地，返回镜像目录；全都不可用时返回 None。

    幂等：目录里已有 tokenizer.json 就直接复用（除非 force），所以重复点「预检」不会重新下载。
    """
    dest = mirror_dir(model, root)
    if not force and (dest / "tokenizer.json").is_file():
        return dest
    failures = []
    for source in sources:
        try:
            if source == "modelscope":
                written = from_modelscope(model, dest, timeout)
            elif source == "hub":
                written = from_hub(model, dest)
            else:
                raise ValueError(f"unknown source {source!r}; pick from {list(SOURCES)}")
            if written:
                print(f"tokenizer 镜像完成（{source}）：{model} -> {dest}")
                return dest
            failures.append(f"{source}: 仓库里没有 {TOKENIZER_FILES} 中的任何文件")
        except Exception as error:   # 一个源不可用就换下一个；两个都不行才报错
            failures.append(f"{source}: {type(error).__name__}: {error}")
    print(f"tokenizer 镜像失败（{model}）：\n  " + "\n  ".join(failures), file=sys.stderr)
    return None


def ensure_source(model, sources=SOURCES, timeout=180.0, root=None, allow_fetch=True):
    """给 AutoTokenizer 一个一定能读的源：本地目录 → 已镜像的目录 → 现拉一次 → 原样返回 model。

    最后那步是有意的：拉不到就把 Hub id 交回去，让调用方按 transformers 的原样报错，
    而不是被这里换成一个更难懂的错误。
    """
    candidate = Path(model).expanduser()
    if candidate.is_dir():
        return model
    dest = mirror_dir(model, root)
    if (dest / "tokenizer.json").is_file():
        return str(dest)
    if allow_fetch and fetch(model, sources, timeout, root=root) is not None:
        return str(dest)
    return model


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", default="jaredpalmer/kev-0.8b", help="Hub 模型 id（owner/name）")
    parser.add_argument("--source", dest="sources", action="append", choices=list(SOURCES),
                        help="镜像源，可重复；默认按优先级 modelscope -> hub")
    parser.add_argument("--timeout", type=float, default=180.0, help="单次请求超时（秒）")
    parser.add_argument("--force", action="store_true", help="已有镜像也重新拉")
    args = parser.parse_args(argv)

    dest = fetch(args.model, tuple(args.sources or SOURCES), args.timeout, args.force)
    if dest is None:
        return 1
    # 打印这个目录：把它填进 precheck 的 --init-from，之后全程离线。
    print(str(dest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
