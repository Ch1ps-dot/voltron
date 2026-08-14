# Overview and architecture

Voltron fuzzes stateful network protocols by combining specification knowledge
with observations from the live target. RFC text is converted into structured
section trees and protocol IR. The synthesizer uses that context and the
target notes to create request generators, response parsers, checkers, and
observers. Active learning builds a Mealy-machine hypothesis, then the
scheduler uses the learned state and request dependencies to choose fuzzing
sequences.

## Execution flow

1. `cli.py` reads the selected SUT from `config/configs.yaml`.
2. `voltron.fuzz.Fuzzer` initializes the LLM clients, synthesizer, mapper,
   executor, and analyzer.
3. `voltron.rfcparser` loads RFC text from `config/rfcs/`, maintains section
   trees in `component/tree/<protocol>/`, and builds IR in
   `component/ir/<protocol>/`.
4. `voltron.synthesizer` produces or evolves protocol components using IR and
   `config/subjects/<target>/info.md`.
5. `voltron.learner` performs active state-machine learning when enabled.
6. `voltron.scheduler` and `voltron.executor` execute state-guided sequences
   and collect feedback from the SUT.

## Main directories

| Path | Purpose |
| --- | --- |
| `config/` | SUT definitions, RFC text, and target lifecycle scripts. |
| `component/ir/` | Generated or cached protocol IR. |
| `component/tree/` | Cached RFC section trees. |
| `component/equipment/` | Generated runtime protocol components. |
| `component/models/` | Activated imported model batches. |
| `results-*/` | Per-run results, metrics, diagnostics, and testcases. |
| `skills/` | Prompt templates and helper scripts used by synthesis. |

`component/` is runtime data, not a source-code substitute. Preserve the
bundle provenance and result artifacts needed to reproduce an experiment.
