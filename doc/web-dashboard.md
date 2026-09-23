# Web dashboard

Voltron includes a local Web control plane for starting one fuzzing task and
observing its existing result artifacts in real time.

## Start the service

From the repository root:

```bash
uv run web.py
```

Open `http://127.0.0.1:8088`. To use another local port:

```bash
uv run web.py --host 127.0.0.1 --port 9000
```

The service has no authentication layer and is intentionally bound to
loopback by default. Do not expose it to an untrusted network. Put an
authenticated reverse proxy in front of it before any shared deployment.

## Design

The dashboard is a thin control and presentation layer:

```text
Browser dashboard
  |-- POST /api/runs --------> RunManager ----> cli.py child process
  |-- POST /api/runs/:id/stop ---- SIGINT ----> cooperative cleanup
  `-- GET status/metrics/logs <---- existing result artifacts
```

- Each run executes in a separate process, so the fuzzer's process-global
  configuration and analyzer state remain isolated from the Web server.
- Web-created results live under `web-runs/<run-id>/` and retain the normal
  Voltron result layout.
- The UI polls lightweight status, CSV metrics, state discoveries, and log
  tails every three seconds. The fuzzing hot path never calls the Web layer.
- Only one run can be active at a time because target ports, generated
  equipment, and other project resources may be shared.
- The process group receives `SIGINT` when the operator stops a run, allowing
  the existing fuzzer cleanup path to terminate the SUT and persist status.
- A small `web_run.json` file records launch options and process identity. A
  surviving run can be recognized after the Web service restarts.

## Page areas

- **Operation launcher:** target, duration, protocol knowledge, model learning,
  guided scheduling, semantic observer, and compliance analysis controls.
- **Mission overview:** execution paths, responses and transitions, anomalies,
  token use, elapsed progress, target identity, and pipeline status.
- **Run archive:** all tasks created from this Web service and their final
  outcomes.
- **Live terminal:** bounded tails of process, fuzzer, and LLM logs.

The API deliberately returns aggregate data and bounded log tails; it does not
provide arbitrary filesystem access or command-line input.
