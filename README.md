# Voltron

Voltron is a protocol-aware fuzzer for network services. It combines RFC
analysis, LLM-assisted component synthesis, active Mealy-machine learning, and
state-guided fuzzing.

## What it does

- Parses protocol specifications and builds reusable section-tree and IR caches.
- Synthesizes request generators, response parsers, checkers, and observers.
- Learns a state model of the target before state-guided fuzzing.
- Preserves diagnostics, response/state metrics, and replayable testcases for
  post-processing.

## Quick start

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and the
project dependencies:

```bash
uv sync
```

Configure an SUT and LLM endpoints in `config/configs.yaml` (keep real API keys
out of version control), then run a target for 30 minutes:

```bash
uv run cli.py -s lightftp -a state -t 30
```

For the first run, Voltron normally parses the configured specifications,
generates protocol components, learns an initial model, and then fuzzes. The
intermediate artifacts are cached for later runs.

Useful focused commands:

```bash
# Build only cached RFC section trees.
uv run cli.py -s lightftp --rfc-parser

# Generate protocol IR without starting the target or fuzzer.
uv run cli.py -s lightftp --generate-ir

# Learn and export a reusable model bundle without fuzzing.
uv run cli.py -s lightftp --learn-and-export -t 30
```

## Documentation

- [Project overview and architecture](doc/overview.md)
- [Target, remote deployment, LLM, and RFC configuration](doc/configuration.md)
- [Running Voltron, artifacts, and runtime metrics](doc/running-voltron.md)
- [Learning-bundle export, import, and model-batch selection](doc/learning-bundles.md)
- [Compliance analysis and coverage replay](doc/analysis-and-replay.md)

## Repository layout

```text
cli.py                  Main CLI entry point
component/              Generated IR, cached trees, equipment, and models
config/                 Runtime configuration, RFC text, and target scripts
doc/                    Usage and project documentation
skills/                 Prompt templates and helper scripts
voltron/                Fuzzer implementation
```

## Supported targets

The current configuration includes example FTP, HTTP, SMTP, SIP, RTSP, TFTP,
CoAP, DNS, and DTLS targets. See `config/configs.yaml` and
`config/subjects/` for the concrete target definitions.

## License

See [LICENSE](LICENSE).
