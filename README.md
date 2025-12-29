# Voltron

## Folder structure

```txt
.
├── handler # generated messsage handler code
├── ir # generated message ir
├── prompts # prompts for llm
├── rfcs # rfc documents
├── tests # files for testing
└── voltron
    ├── configs # some configs 
    ├── executor 
    ├── fuzz.py
    ├── handler
    ├── llm
    ├── rfcparser
    ├── sheduler
    └── utils

```

## Setup

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) as Python package and project manager.

```bash
wget -qO- https://astral.sh/uv/install.sh | sh
```

Install package depencies with uv

```bash
uv pip install requirements
```

## TODO

- [x] basic workflow
- [x] data model
- [ ] code mutate
- [ ] state model
- [ ] real scene experiments

## Project Log

### 2025-12-01

utils/rag.py: be able to resolve documents to data structure.

### 2025-12-28

finish the basic workflow that start from parsing document to generating real message
