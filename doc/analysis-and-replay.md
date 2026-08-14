# Compliance analysis and replay

## Compliance analysis

`analyze_compliance.py` is an offline post-processing command. It examines
saved request/response pairs against relevant cached RFC sections and asks the
configured `llm_compliance` endpoint for a verdict.

Before running it, configure `llm_compliance`, run a specification-aware fuzz
workflow at least once, and retain the generated
`request_response_pairs/pair_*.json` files.

```bash
uv run analyze_compliance.py \
  -s lighttpd \
  -i results-lighttpd-voltron-<timestamp> \
  -o results-lighttpd-voltron-<timestamp>/compliance_analysis \
  --top-k 10 \
  --concurrency 4
```

`-i` accepts a result directory, `request_response_pairs` directory, or an
individual pair JSON file. Results are categorized under `compliant/`,
`non_compliant/`, `uncertain/`, and `failed/`. An `uncertain` verdict is a
completed analysis; files in `failed/` include error information.

In-run checker review is a separate feature enabled with
`--compliance-analysis` on the fuzzer command.

## Coverage replay

`replayer.py` sends the original request bytes from saved conversations and
collects cumulative source coverage:

```bash
uv run replayer.py \
  -s lighttpd \
  -d results-lighttpd-voltron-<timestamp> \
  -c /path/to/lighttpd/source-or-gcov-build
```

The result directory must contain `replayable_testcases/*.pkl`. Replay also
requires executable `config/subjects/<target>/cov_setup.sh` and
`cov_collect.sh` scripts. The repository provides them for `exim`, `kamailio`,
`lighttpd`, `live555`, and `pureftpd`; other targets need their own coverage
adapters.

Replay restarts the SUT for each testcase, reconstructs the saved request
sequence, writes `cov_over_time.csv`, and does not modify the testcase or run
response checkers/observers.
