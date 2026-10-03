## Table of Contents
1. Highlights
2. Model Family
3. Inference API
4. Training and Fine-Tuning
5. Deployment and Playground
6. Evaluation and Calibration
7. Migration and Compatibility
8. Known Issues
9. Getting Started
10. Acknowledgements

## Highlights
Kev 1.0 is the first stable release of the small decision-model family, delivering an end-to-end path from local training to deployment:
- Four model sizes: 0.8B, 4B, 9B, 27B, covering Mac to datacenter GPUs.
- A TypeSafe System One compatible `/v1/systemone` API, a drop-in replacement for Jev.
- Calibrated probability output by default, with stable argmax and improved Brier/calibration.
- LoRA adapter and full fine-tuning paths, with data formats, training commands, and eval commands documented.
- Local HTTP service, Modal HTTPS deployment, and a browser Playground.
- Reproducible evaluation, open weights, and open calibration parameters.

## Model Family
Kev 1.0 includes four sizes:

| Model | Base | Training | Best for |
|---|---|---|---|
| Kev-0.8B | Qwen3.5-0.8B-Base | LoRA adapter | low-memory devices, quick prototypes |
| Kev-4B | Qwen3.5-4B-Base | LoRA adapter | general decision classification |
| Kev-9B | Qwen3.5-9B-Base | LoRA adapter | higher accuracy, more stable probabilities |
| Kev-27B | Qwen3.8-27B | full fine-tune + weight averaging | highest precision, long documents, production |

Kev-27B is the first full fine-tune based on the Qwen3.8 post-trained release, published as bf16 full weights.

## Inference API
The core endpoint is `POST /v1/systemone`, compatible with TypeSafe System One:
- Input: shared `state` and multiple typed `questions` (noul / choice / score).
- Output: probabilities per option, most-likely option, confidence, and usage statistics.
- Other endpoints: `GET /v1/models`, `POST /v1/systemone/permute`, `POST /v1/systemone/separate`.
- Auth: optional Bearer auth via `KEV_API_KEY`.
- Behavior switches via env vars: `KEV_TEMPERATURE`, `KEV_DATE_FACTS`, `KEV_TRUNCATE_STATES`, `KEV_DTYPE`.

## Training and Fine-Tuning
Kev 1.0 supports two paths:
- LoRA adapter: fast incremental fine-tuning from a base or trained checkpoint; supports shared prefix, length sorting, micro-batch splitting, snapshots, and resume.
- Full fine-tuning: trains the whole backbone plus the head; uses fp32 master weights for stability; supports staged snapshots and resume.

Data sources include a frozen suite, custom JSONL, and replay sampling. Augmentation includes none-pair siblings and permutation copies for permutation KL.

## Deployment and Playground
- Local: `uv run --extra serve python -m kev.serve --run <model> --port <port>`.
- Cloud: Modal deploys an HTTPS endpoint; combine with your own GPU machines for production.
- Frontend: the Playground provides preset loading, text editing, question config, real-time inference, and result display, plus a built-in chess board game.

## Evaluation and Calibration
- Benchmark metrics: accuracy, Brier, calibration error, automation ratio, option-order stability, question isolation.
- `kev.benchmark` scores a run or Hub revision; `kev.calibrate` reports what a fitted temperature would do.
- Every checkpoint carries a temperature; calibrated probabilities are returned by default and do not change the argmax.

## Migration and Compatibility
- TypeSafe SDK / Jev clients: point the base URL at the Kev service; no caller changes needed.
- From earlier Kev versions: load checkpoints via the same path; check head.pt fields and temperature.
- From Qwen bases: Kev adapters attach to the matching Qwen3.5/3.8 base; verify base_revision.

## Known Issues
- MPS out of memory on Apple Silicon: ensure only one training task runs at a time.
- Playground buttons unresponsive on non-localhost domains: use `localhost:3001`, or adjust allowedDevOrigins.
- Long-document performance: Kev-27B or recalibration on your own data is recommended for long inputs.

## Getting Started
```bash
git clone https://github.com/jaredpalmer/kev.git && cd kev
uv sync --extra serve
uv run --extra serve python -m kev.serve --run jaredpalmer/kev-4b --port 8009
```

Then send a request with curl or the Python SDK, or open the Playground to try it interactively.

## Acknowledgements
Thanks to the Qwen team for the base models, the TypeSafe team for the System One protocol, and all contributors to the evaluation datasets and tooling.
