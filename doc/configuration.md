# Configuration

Runtime configuration is in `config/configs.yaml`. Do not commit real API
keys; use environment-variable expansion or an ignored local configuration
file where appropriate.

## Add or update a local target

Each target needs an entry in `config/configs.yaml` and a matching
`config/subjects/<target>/` directory. A local target normally provides:

- `run.sh` to start the SUT;
- `setup.sh` to reset or prepare it;
- `info.md` with protocol- and target-specific synthesis notes.

Example:

```yaml
lightftp:
  protocol: ftp
  host: 127.0.0.1
  port: 2200
  rfc_name: ["rfc959", "rfc2428", "rfc3659", "rfc2389", "rfc2228"]
  trans_layer: tcp
  server: parent
```

`protocol`, `host`, `port`, `rfc_name`, and `trans_layer` identify the service
and its specifications. `server` controls the target lifecycle relationship.
Optional readiness and parser-validation fields can be added for targets that
need them; use existing entries in `config/configs.yaml` as working examples.

## Remote targets

Set `sut_deployment: remote` when Voltron must not manage a local SUT. Point
`host` and `port` at the remote protocol service. An optional `monitor` agent
may expose `POST /start`, `GET /health`, `GET /logs?tail=N`, and `POST /stop`.

```yaml
remote-lightftp:
  protocol: ftp
  host: 192.0.2.10
  port: 2200
  rfc_name: ["rfc959"]
  trans_layer: tcp
  server: parent
  sut_deployment: remote
  monitor:
    mode: agent
    url: http://192.0.2.10:9000
    service_host: 192.0.2.10
    service_port: 2200
    timeout_s: 1.0
```

Remote support is experimental. If the monitor is unavailable, Voltron can
continue black-box network interaction but cannot reliably classify a remote
crash versus a hang or network failure.

## LLM endpoints

`llm_doc`, `llm_fuzz`, and `llm_compliance` configure the endpoint, API key,
model, and concurrency for their respective workloads. For example:

```yaml
llm_fuzz:
  base_url: https://example.com/v1
  api_key: ${VOLTRON_LLM_FUZZ_API_KEY}
  model: example-model
  async_sem: 8
```

Use `llm_compliance` when running the separate compliance analysis command.

## RFC documents

Place the RFC text files named by `rfc_name` in `config/rfcs/`, for example
`config/rfcs/rfc959.txt`. The helper `skills/utils/rfc_download.sh` can fetch
RFC documents. Section-tree caches are stored under
`component/tree/<protocol>/` after parsing.
