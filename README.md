# Voltron

Developing version is in dev-qpf branch
## Folder structure

```
├── test: testcases and PUTs
└── voltron: source code of fuzzer
    ├── configs: configuration files
    ├── executor: modules for executing PUTs
    ├── handler: message generators and packet parsers 
    ├── llm: modules for invoking llm
    ├── nio: network I/O for communication
    └── sheduler: state scheduler

```

## Setup

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) as Python package and project manager.

```
wget -qO- https://astral.sh/uv/install.sh | sh
```

Install package depencies with uv

```
uv pip install requirements
```