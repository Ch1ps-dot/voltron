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
    ├── scheduler/                # sequence scheduling and havoc fuzzing
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
- A `run.sh` script to start the SUT
- A `setup.sh` script to reset or prepare the SUT
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

### 2. Configure the LLM

The `llm` section in `config/configs.yaml` controls the API endpoint, key, model, and concurrency:

```yaml
llm:
  base_url: https://example.com/v1
  api_key: <your-api-key>
  model: gpt-5-mini-2025-08-07
  async_sem: 8
```

For safety, avoid committing real API keys to the repository.

### 3. Provide RFC documents

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

Example:

```bash
uv run cli.py -s lightftp -a state -t 30
```

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
- `component/equipment/<target>/`: synthesized generators, parsers, and mutators
- `results-<target>-voltron-<timestamp>/`: final run statistics and discovered state information

Depending on runtime configuration, log files may also be generated for debugging and crash triage.

## Replay

`replayer.py` exists for testcase replay and coverage collection, but it should currently be treated as experimental. The main fuzzing workflow through `cli.py` is the primary supported path.

## Supported Targets

The current configuration includes examples for several protocols and implementations, including FTP, HTTP, SMTP, SIP, RTSP, TFTP, CoAP, DNS, and DTLS targets.

