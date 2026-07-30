# Voltron

Voltron is a protocol-aware fuzzer that combines RFC parsing, LLM-based code synthesis, active automata learning, and state-guided fuzzing for network services.

## Features

1. Split and parse RFC documents into structured section trees.
2. Use an LLM to synthesize protocol message generators and response parsers.
3. Learn a Mealy machine model with a modified LM* workflow.
4. Evolve generators and parsers with response feedback and request dependencies.
5. Generate state-dependent message sequences for fuzzing.
6. Replay saved testcases for coverage-oriented analysis.

## Repository Layout

```txt
.
├── README.md
├── pyproject.toml
├── cli.py                        # main CLI entry for fuzzing
├── replayer.py                   # replay entry point (experimental)
├── component/
│   └── ir/                       # generated or cached protocol IR assets
├── config/
│   ├── configs.yaml              # SUT and LLM configuration
│   ├── rfcs/                     # RFC text files
│   └── subjects/                 # per-target scripts and protocol notes
├── skills/                       # prompt templates and helper scripts
└── voltron/
    ├── analyzer/                 # runtime statistics and result collection
    ├── executor/                 # SUT lifecycle, network I/O, conversation recording
    ├── learner/                  # LM*-style Mealy machine learning
    ├── llm/                      # LLM client and prompt assembly
    ├── rfcparser/                # RFC parsing and IR generation
    ├── scheduler/                # sequence scheduling and berserker fuzzing
    ├── synthesizer/              # generator/parser/mutator synthesis
    └── utils/
```

## Architecture

The current execution flow is:

1. `cli.py` loads a target from `config/configs.yaml`.
2. `voltron.fuzz.Fuzzer` initializes the LLM client, RFC parser, synthesizer, mapper, executor, and analyzer.
3. `voltron.rfcparser` reads RFC documents from `config/rfcs/`, builds section trees, and generates protocol IR under `component/ir/<protocol>/`.
4. `voltron.synthesizer` uses the IR and target notes from `config/subjects/<target>/info.md` to generate or evolve request generators, parsers, and mutators.
5. `voltron.learner` learns a Mealy machine of the target service through membership and equivalence queries.
6. `voltron.scheduler` and `voltron.executor` drive state-guided fuzzing against the running target.

## Setup

Install [uv](https://docs.astral.sh/uv/getting-started/installation/):

```bash
wget -qO- https://astral.sh/uv/install.sh | sh
```

Install dependencies:

```bash
uv sync
```

Activate the virtual environment if you want to run commands directly:

```bash
source .venv/bin/activate
```

## Configuration

### 1. Add or update a target

Each target needs:

- An entry in `config/configs.yaml`
- A directory `config/subjects/<target>/`
- A `run.sh` script to start the SUT in local mode
- A `setup.sh` script to reset or prepare the SUT in local mode
- An `info.md` file with protocol- or target-specific notes for synthesis

Example target configuration:

```yaml
lightftp:
  protocol: ftp
  host: 127.0.0.1
  port: 2200
  rfc_name: ["rfc959", "rfc2428", "rfc3659", "rfc2389", "rfc2228"]
  trans_layer: tcp
  server: parent
```

### 2. Configure a remote target

Use remote mode when the SUT runs on another machine and Voltron should not
start, stop, or kill a local process. In this mode, `host` and `port` point to
the remote protocol service, and `monitor` optionally points to a lightweight
agent running beside the SUT.

```yaml
remote-lightftp:
  protocol: ftp
  host: 192.0.2.10
  port: 2200
  rfc_name: ["rfc959", "rfc2428", "rfc3659", "rfc2389", "rfc2228"]
  trans_layer: tcp
  server: parent
  sut_deployment: remote
  monitor:
    mode: agent
    url: http://192.0.2.10:9000
    service_host: 192.0.2.10
    service_port: 2200
    timeout_s: 1.0
    log_tail: 200
```

The agent endpoints are deliberately small:

- `POST /start`: optional; start or restart the remote SUT.
- `GET /health`: return process and service status as JSON.
- `GET /logs?tail=N`: optional; return recent log lines for crash triage.
- `POST /stop`: optional; stop the remote SUT.

`GET /health` should return fields such as:

```json
{
  "state": "RUNNING",
  "process_running": true,
  "port_listening": true,
  "returncode": null,
  "stderr": "",
  "logs": ""
}
```

Valid states are `RUNNING`, `EXITED`, `CRASHED`, `UNREACHABLE`, and `UNKNOWN`.
If the agent is unavailable, Voltron falls back to black-box network behavior:
it can still connect to the target and record protocol-level timeouts, but it
cannot reliably distinguish a remote crash from a hang or network failure.

Remote SUT support is still experimental and has not been fully validated across
real deployments. Users should try it with their own target, agent, and network
environment before relying on the results.

### 3. Configure the LLM

The `llm` section in `config/configs.yaml` controls the API endpoint, key, model, and concurrency:

```yaml
llm:
  base_url: https://example.com/v1
  api_key: <your-api-key>
  model: gpt-5-mini-2025-08-07
  async_sem: 8
```

For safety, avoid committing real API keys to the repository.

### 4. Provide RFC documents

Place RFC text files in `config/rfcs/` using the filenames referenced in `rfc_name`, for example `rfc959.txt`.

The parser also includes a helper download script at `skills/utils/rfc_download.sh`.

## Usage

Run the fuzzer with:

```bash
uv run cli.py -s <target-name> -a state -t <minutes>
```

Common options:

- `-s, --sut`: target name defined in `config/configs.yaml`
- `-a, --algorithm`: fuzzing algorithm, currently `state` is the main path
- `-t, --time`: fuzzing time in minutes
- `-c, --cmdline`: optional command line override, defaults to the target `run.sh`
- `-o, --output`: optional custom results directory
- `--rfc-parser`: only parse RFC documents into cached SectionTrees
- `--generate-ir`: only parse protocol specifications and generate protocol IR
- `--spec-knowledge/--no-spec-knowledge`: enable or ablate RFC/IR knowledge
- `--state-learning/--no-state-learning`: enable or skip Mealy-machine learning
- `--guided-scheduling/--no-guided-scheduling`: enable or ablate state/dependency-guided scheduling

Example:

```bash
uv run cli.py -s lightftp -a state -t 30
```

To parse only the RFC documents configured for a target into cached
`SectionTree` objects, use:

```bash
uv run cli.py -s lightftp --rfc-parser
```

This mode does not require `--time` and does not initialize the producer,
state learner, executor, or target process. It writes one pickle file per RFC
to `component/tree/<protocol>/<rfc-name>.pkl`; an existing valid cache is reused.

To run the complete protocol-specification parsing process and generate the
configured target's IR without starting fuzzing, use:

```bash
uv run cli.py -s lightftp --generate-ir
```

This mode also does not require `--time`. It creates or reuses the SectionTree
caches, then generates the request/response message IR and state relationships
under `component/ir/<protocol>/`. It does not initialize the producer, state
learner, executor, or target process.

Remote targets use the same command; select the remote target name from
`config/configs.yaml`:

```bash
uv run cli.py -s remote-lightftp -a state -t 30
```

For ablation runs, each switch can be disabled independently:

```bash
uv run cli.py -s lightftp -a state -t 30 --no-state-learning
uv run cli.py -s lightftp -a state -t 30 --no-guided-scheduling
uv run cli.py -s lightftp -a state -t 30 --no-spec-knowledge
```

The no-specification mode is a fixed-seed baseline. Run the full configuration
once first so `component/equipment/<target>/` contains seed generators and a
response parser. The ablated run loads only the first cached generator for each
request type and the first cached parser; it disables RFC parsing, request
dependencies, mutators, generator evolution, and parser evolution.

## First Run Behavior

When a target is fuzzed for the first time, Voltron will typically:

1. Parse the configured RFC documents.
2. Extract request and response fields.
3. Generate request and response IR.
4. Infer possible responses and request dependencies.
5. Synthesize initial message generators and parsers with the LLM.
6. Learn an initial state machine before entering fuzzing.

These intermediate artifacts are cached and reused in later runs.

## Generated Artifacts

During and after execution, the repository accumulates several kinds of outputs:

- `component/ir/<protocol>/`: parsed RFC trees, field descriptions, message IR, and state dependencies
- `component/models/<target>/`: learned or evolved automata models
- `component/equipment/<target>/`: synthesized generators, parsers,
  per-response-type checkers, and mutators
- `results-<target>-voltron-<timestamp>/`: final run statistics and discovered state information
- `results-<target>-voltron-<timestamp>/invalid_responses/`: request/response
  sequence prefixes whose parsed response failed its type-specific checker
- `results-<target>-voltron-<timestamp>/request_response_pairs/`: unique
  request-type/response-type pairs saved as JSON with Base64-encoded messages
- `results-<target>-voltron-<timestamp>/phase_metrics.csv`: per-stage timing
  and LLM token usage for document analysis, model learning, and fuzzing
- `results-<target>-voltron-<timestamp>/model_learning_iterations.csv`:
  per-iteration model-learning state and protocol feedback metrics
- `results-<target>-voltron-<timestamp>/generator_iteration_metrics.csv`:
  whole-process response snapshots and deltas around generator evolution and
  mutation rounds
- `compliance_analysis/`: optional per-pair protocol compliance judgments
  generated by `analyze_compliance.py`

Depending on runtime configuration, log files may also be generated for debugging and crash triage.

## Runtime Metrics

Voltron writes CSV metrics into the active result directory.

`phase_metrics.csv` contains one row per major execution phase:

- `doc_analysis`: RFC parsing and initial equipment synthesis
- `model_learning`: active state-machine learning
- `fuzzing`: berserker fuzzing and generator mutation

Each row records the phase status, start/end timestamps, wall-clock duration,
LLM chat time, LLM call count, and prompt/completion/total token usage. If
state learning is disabled, `model_learning` is recorded with status
`skipped`.

`model_learning_iterations.csv` contains one row for each successful
model-learning iteration. It records the iteration duration, remaining retry
budget, learned automaton size, observation-table size, response types and
response transitions seen in that iteration, and the cumulative response-type
and response-transition counts.

Whole-process response metrics use the `lifetime_` prefix. They are never reset
between model-learning and fuzzing iterations:

- `lifetime_response_type_events`: all successfully parsed response events,
  including unsolicited initial responses
- `lifetime_response_types`: distinct parsed response types
- `lifetime_response_transition_events`: all recorded adjacent-response events
- `lifetime_response_transitions`: distinct adjacent-response pairs

The same values are displayed in the runtime UI and written to `fuzzer_status`.
`states.csv` also records them as separate `lifetime_*` data types. Transport
outcomes such as timeout, closed connection, poll error, and crash retain their
existing dedicated counters and are not treated as parsed response types.

`generator_iteration_metrics.csv` records whole-process response checkpoints
around generator changes. It contains model-learning and fuzzing baselines, one
row immediately before each actual generator evolution or mutation, and one
final row at shutdown. Each row includes the cumulative lifetime values and
their deltas from the previous checkpoint.

Because a checkpoint is taken before an operation, its delta evaluates the
generator operation named by `evaluated_operation_id`, not the upcoming
`operation_id`. The final checkpoint captures the observation interval after
the last mutation. Mutation rows also record the exact request types selected
for that round in `mutated_types`.

## Compliance Analysis

`analyze_compliance.py` analyzes saved request-response pairs for possible
protocol non-compliance bugs. For each pair, it retrieves relevant protocol
requirements from the cached RFC SectionTrees, combines them with the captured
request and response, and asks the configured compliance LLM for a verdict.

Before running the analysis:

1. Configure the dedicated `llm_compliance` entry in
   `config/configs.yaml`:

```yaml
llm_compliance:
  base_url: your-api-base-url
  api_key: your-api-key
  model: your-model
  async_sem: 8
```

2. Run the normal specification-aware fuzzing workflow at least once. The
   required SectionTree caches must exist under
   `component/tree/<protocol>/<rfc-name>.pkl`.
3. Ensure the input contains the `pair_*.json` files generated under
   `request_response_pairs/`.

If one cached RFC SectionTree is missing or damaged, the script prints a
warning and continues with the remaining valid caches. If no usable cache
remains, rerun the normal specification-aware workflow to regenerate
`component/tree/<protocol>/*.pkl`.

Analyze all saved pairs in a fuzz result directory:

```bash
uv run analyze_compliance.py \
  -s lighttpd \
  -i results-lighttpd-voltron-<timestamp>
```

The input can also be the `request_response_pairs` directory or one pair file:

```bash
uv run analyze_compliance.py \
  -s lighttpd \
  -i results-lighttpd-voltron-<timestamp>/request_response_pairs

uv run analyze_compliance.py \
  -s lighttpd \
  -i results-lighttpd-voltron-<timestamp>/request_response_pairs/pair_000000.json
```

Common options:

- `-s, --sut`: target name defined in `config/configs.yaml`
- `-i, --input`: pair JSON file, pair directory, or complete fuzz result directory
- `-o, --output`: output directory; defaults to `compliance_analysis` beside
  the input
- `--top-k`: number of retrieved RFC sections sent to the LLM; default is `8`
- `--max-section-chars`: maximum characters retained from each section;
  default is `6000`
- `-j, --concurrency`: maximum number of pair analyses executed concurrently;
  defaults to `llm_compliance.async_sem`

Example with an explicit output directory:

```bash
uv run analyze_compliance.py \
  -s lighttpd \
  -i results-lighttpd-voltron-<timestamp> \
  -o results-lighttpd-voltron-<timestamp>/compliance_analysis \
  --top-k 10 \
  --concurrency 4
```

Each input `pair_NNNNNN.json` produces a categorized result:

```text
compliance_analysis/
├── compliant/
├── non_compliant/
├── uncertain/
└── failed/
```

Successful `pair_NNNNNN.analysis.json` files contain:

- `verdict`: `compliant`, `non_compliant`, or `uncertain`
- confidence and summary
- identified violations and supporting RFC requirements
- metadata for the retrieved RFC sections

Files that cannot be analyzed are stored under `failed/` with the source path,
exception type, and error message.

The script prints a one-line verdict for each pair and exits with a nonzero
status if any pair could not be analyzed. An `uncertain` verdict is still a
successful analysis result. While running, a command-line progress bar shows
the completed count, failure count, configured concurrency, and latest verdict.

## Replay

`replayer.py` replays the original request bytes saved during fuzzing and
collects cumulative source-code coverage after each testcase.

The testcase input must be a complete fuzz result directory containing:

```text
results-<target>-voltron-<timestamp>/
└── replayable_testcases/
    ├── cons_000000.pkl
    ├── cons_000001.pkl
    └── ...
```

Only `.pkl` files under `replayable_testcases/` are loaded. Invalid pickle
files are skipped without stopping the remaining replay run.

Run replay with:

```bash
uv run replayer.py \
  -s lighttpd \
  -d results-lighttpd-voltron-<timestamp> \
  -c /path/to/lighttpd/source-or-gcov-build
```

Options:

- `-s, --sut`: target name defined in `config/configs.yaml`
- `-d, --dir`: fuzz result directory containing `replayable_testcases/`
- `-c, --gcov_folder`: source or instrumented build directory passed to the
  target coverage scripts

Relative paths are converted to absolute paths before replay starts, so the
command can be launched from outside the project directory.

Replay requires both of the following executable scripts:

```text
config/subjects/<target>/cov_setup.sh
config/subjects/<target>/cov_collect.sh
```

The repository currently provides these scripts for `exim`, `kamailio`,
`lighttpd`, `live555`, and `pureftpd`. Other targets require target-specific
coverage scripts before coverage-oriented replay can be used.

During replay, Voltron:

1. Initializes coverage and creates
   `<result-directory>/cov_over_time.csv`.
2. Restarts the configured SUT for each testcase.
3. Reconstructs the request sequence from the saved `Conversation`.
4. Sends the saved raw request bytes in their original order.
5. Runs `cov_collect.sh` after each successfully replayed testcase.

Replay does not run response checkers or semantic observers and does not modify
the saved testcase. Pressing `Ctrl+C` once stops the active SUT and exits the
replay process.

## Supported Targets

The current configuration includes examples for several protocols and implementations, including FTP, HTTP, SMTP, SIP, RTSP, TFTP, CoAP, DNS, and DTLS targets.
