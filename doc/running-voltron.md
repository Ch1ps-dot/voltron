# Running Voltron and interpreting results

## Fuzzing

The standard command is:

```bash
uv run cli.py -s <target> -a state -t <minutes>
```

`-a state` is the default algorithm. `-t` is required for fuzzing and must be
at least one minute. `-c` overrides the target command line and `-o` selects a
custom result directory.

Important feature switches are:

- `--spec-knowledge` / `--no-spec-knowledge`: use RFC/IR knowledge, or run
  the LLM-only type-bootstrap ablation.  The latter does not read RFC/IR or
  cached equipment.
- `--state-learning` / `--no-state-learning`: enable or skip active learning.
- `--guided-scheduling` / `--no-guided-scheduling`: enable or ablate
  state/dependency-guided scheduling.
- `--offline-mutator-only`: fixed-component ablation.  It disables state
  learning, model/dependency scheduling, and LLM mutator evolution, while
  retaining AFLNet and Voltron interesting-seed prefixes plus offline byte
  mutation.
- `--observer` / `--no-observer`: enable or disable semantic observers.
- `--compliance-analysis`: enable in-run checker review; it is disabled by
  default.
- `--load-aflnet-seeds` / `--no-load-aflnet-seeds`: control loading converted
  AFLNet seeds after model learning.

`--no-spec-knowledge` builds a fresh, minimal request/response catalog from
the protocol name and transport only, then synthesizes its own generator and
parser under `component/equipment/<target>/llm-type-only/`.  It deliberately
does not fall back to an earlier full-run cache.

## Specification-only modes

```bash
# Cache SectionTrees only; no target or fuzzer is initialized.
uv run cli.py -s lightftp --rfc-parser

# Build SectionTrees and IR only; no target or fuzzer is initialized.
uv run cli.py -s lightftp --generate-ir
```

## Results and diagnostics

A normal run writes `results-<target>-voltron-<timestamp>/`. Important output
paths include:

| Path | Contents |
| --- | --- |
| `diagnostics/status/run_status.json` | Final run status. |
| `diagnostics/status/fuzzer_status` | Latest progress snapshot, not final authority. |
| `diagnostics/logs/` | Fuzzer and LLM logs. |
| `diagnostics/events/` | Append-only lifecycle and validation evidence. |
| `states.csv` | Event-driven parsed response-type and transition discoveries. |
| `phase_metrics.csv` | Phase duration and LLM usage. |
| `llm_usage_metrics.csv` | LLM calls, latency, and tokens grouped by usage/model. |
| `model_learning_iterations.csv` | Per-learning-iteration model and feedback metrics. |
| `generator_iteration_metrics.csv` | Response checkpoints around generator changes. |
| `request_response_pairs/` | Unique captured request/response pairs. |
| `replayable_testcases/` | Saved conversations usable by `replayer.py`. |

`run_status.json` describes the terminal result; a live process, archive, or
partial artifact alone does not establish successful completion.

`states.csv` records parsed response-type and adjacent-response-transition
discoveries. Transport outcomes such as timeouts and connection errors remain
separate counters and are not parsed response types.

Replayable conversations are retained when they discover a new response type
or response transition, or when they set a new run-phase record for response
sequence length or the number of distinct response transitions within one
conversation. Newly observed request/response-type relations still inform
scheduling, but do not alone save another byte-level replay seed.
