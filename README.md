# Voltron

Developing version is under dev-qpf branch.

Implemented functions contains:

1. Split and parse rfc documents.

2. LLM guided synthesis of message generator and parser.

3. modified LM* algorithm for model learning

4. response feedback and request dependencies guided generator evolving.

## Project Structure

```txt
.
├── README.md
├── clean_out.sh    # clean logs and fuzzer output
├── configs.yaml    # configs of server under test
├── count_tool.py   # nonsense script tool to count code line 
├── input           # files for prompt augmentaion and fuzzer setup, including target information, rfc documents, scripts for running target and prompt templates.
├── main.py         # entry point of fuzzer
├── output          # files generated during executing, including protocol ir, message generator and parser
├── replayer.py     # unfinished replayer for testcase replaying
├── tests           # unused test framewokr
└── voltron
```

## Setup

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) as Python package and project manager.

```bash
wget -qO- https://astral.sh/uv/install.sh | sh
```

Install package dependencies with uv

```bash
uv sync
```

Actiavte virtual environment
```bash
source .venv/bin/activate
```

## Usage

1. Prepare server information and rfc documents of target protocol implementations, and put them under the folder input/infos and input/rfcs.
    - sut info -> input/infos
    - rfc documents -> input/rfc

2. Put the script of running and resetting target program under folder input/scripts/<targetname>.
    - run.txt: command to setup sut.
    - post.sh: scripts to reset the sut.

3. Write configurations of server under test in configs.yaml like other target, and don't forget to set your LLM API. 
    ```yaml
    lightftp:
        protocol: ftp
        host: 127.0.0.1
        port: 2200
        rfc_name: ["rfc959"]
        trans_layer: tcp #transport layer protocol
        server: parent #server mode (parent as default, a few of sut set up child process as server.)
    ```

4. run fuzzer. 

```bash
uv run cli.py -s <target-name> -a <mode> -t <time_s>
```

If it is the first time to test the target, fuzzer will begin to split provided rfc documents. Then it will use LLM to transform the message and state information within rfc to protoIR and state constraint. Finally, use LLM to generate seed generator and parser. The intermidiate files during above steps can be reused in another new round of fuzzing.

When you see the fuzzer runtime monitor menu, it means the fuzzer begins to work.

## Analysis

The fuzzer will create two folder under project folder.

- fuzz_logs: runtime debug information.

- results-<targetname>-<timestamp>: statistic, learned state models and so no.
