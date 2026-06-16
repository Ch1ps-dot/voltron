import json
import pickle
import threading
from pathlib import Path
from types import SimpleNamespace

from click.testing import CliRunner

import replayer as replayer_module
from voltron.analyzer.analyzer import analyzer
from voltron.configs import configs
from voltron.executor.conversation import Conversation
from voltron.executor.executor import Executor
from voltron.fuzz import Fuzzer


class ReplayExecutor:
    def __init__(self) -> None:
        self.replayed = []
        self.coverage_files = []

    def cov_setup(self, folder: Path, cov_file: Path):
        return None

    def interact(self, req_seq, poll_wait_ms=3000):
        self.replayed.append(req_seq)
        return True, Conversation()

    def cov_collect(self, folder: Path, cov_file: Path, file_path: Path):
        self.coverage_files.append(file_path)


def test_replay_process_loads_only_valid_pickle_files(tmp_path, monkeypatch):
    replay_dir = tmp_path / "results"
    testcase_dir = replay_dir / "replayable_testcases"
    testcase_dir.mkdir(parents=True)
    cons = Conversation()
    cons.add_state("-", "220")
    cons.add_data(b"", b"220 ready\r\n")
    cons.add_state("USER", "331")
    cons.add_data(b"USER test\r\n", b"331 password\r\n")
    with (testcase_dir / "cons_000000.pkl").open("wb") as stream:
        pickle.dump(cons, stream)
    (testcase_dir / "notes.txt").write_text("not a pickle", encoding="utf-8")
    (testcase_dir / "broken.pkl").write_bytes(b"not a pickle")

    fuzzer = Fuzzer.__new__(Fuzzer)
    fuzzer.exe = ReplayExecutor()
    fuzzer.stop_event = threading.Event()
    monkeypatch.setattr(configs, "target_name", "demo", raising=False)

    fuzzer.replay_process(replay_dir, tmp_path / "coverage")

    assert fuzzer.stop_event.is_set()
    assert fuzzer.exe.replayed == [[("USER", b"USER test\r\n")]]
    assert fuzzer.exe.coverage_files == [
        testcase_dir / "cons_000000.pkl"
    ]


def test_replay_process_stops_ui_when_input_directory_is_missing(
    tmp_path,
    monkeypatch,
):
    fuzzer = Fuzzer.__new__(Fuzzer)
    fuzzer.exe = ReplayExecutor()
    fuzzer.stop_event = threading.Event()
    monkeypatch.setattr(configs, "target_name", "demo", raising=False)

    fuzzer.replay_process(tmp_path / "missing", tmp_path / "coverage")

    assert fuzzer.stop_event.is_set()


def test_replayer_resolves_relative_paths(tmp_path, monkeypatch):
    captured = {}

    class FakeFuzzer:
        def __init__(self, **kwargs):
            captured["init"] = kwargs

        def replay(self, **kwargs):
            captured["replay"] = kwargs

    monkeypatch.setattr(replayer_module, "Fuzzer", FakeFuzzer)
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        Path("results").mkdir()
        Path("coverage").mkdir()
        result = runner.invoke(
            replayer_module.main,
            ["-s", "demo", "-d", "results", "-c", "coverage"],
        )
        expected_results = Path("results").resolve()
        expected_coverage = Path("coverage").resolve()

    assert result.exit_code == 0
    assert captured["init"]["output"] == str(expected_results)
    assert captured["replay"]["res_dir"] == expected_results
    assert captured["replay"]["cov_folder"] == expected_coverage


def test_crash_saves_unsaved_triggering_request(monkeypatch):
    executor = Executor.__new__(Executor)
    executor.crash_testcases = {}
    executor.analyzer = SimpleNamespace(
        lock=threading.Lock(),
        crash_num=0,
    )
    saved = []
    reports = []
    executor.save_cons = lambda cons, *args: saved.append(cons)
    executor.generate_crash_report = (
        lambda **kwargs: reports.append(kwargs["cons"])
    )
    monkeypatch.setattr(configs, "fuzz_mode", "fuzz", raising=False)

    cons = Conversation()
    cons.add_state("-", "220")
    cons.add_data(b"", b"220 ready\r\n")
    proc = SimpleNamespace(returncode=-11)
    trigger = b"CRASH\r\n"

    executor.handle_crash(
        cons,
        proc,
        "CRASH",
        trigger,
        stdout="captured",
        request_recorded=False,
    )

    assert cons.req_seq[-1] == "CRASH"
    assert cons.res_seq[-1] == "CRASH"
    assert cons.content[-1] == (trigger, b"")
    assert len(cons.req_seq) == len(cons.res_seq) == len(cons.content)
    assert saved == [cons]
    assert reports == [cons]


def test_crash_report_collects_feedback_and_messages(tmp_path, monkeypatch):
    class FakeChater:
        async def chat_llm(self, prompt, usage):
            self.prompt = prompt
            self.usage = usage
            return "# Crash Report\n\nLikely null dereference."

    chater = FakeChater()
    executor = Executor.__new__(Executor)
    executor.mapper = SimpleNamespace(
        producer=SimpleNamespace(chater=chater)
    )
    monkeypatch.setattr(configs, "results_path", tmp_path, raising=False)
    monkeypatch.setattr(configs, "target_name", "demo", raising=False)
    monkeypatch.setattr(configs, "pro_name", "ftp", raising=False)

    cons = Conversation()
    cons.add_state("-", "220")
    cons.add_data(b"", b"220 ready\r\n")
    cons.add_state("CRASH", "CRASH")
    cons.add_data(b"CRASH\r\n", b"")
    proc = SimpleNamespace(returncode=-11)

    executor.generate_crash_report(
        cons=cons,
        proc=proc,
        msg_type="CRASH",
        msg=b"CRASH\r\n",
        stdout="",
        stderr="AddressSanitizer: SEGV",
    )

    report_dir = tmp_path / "crash_reports"
    json_path = report_dir / "report_000000.json"
    md_path = report_dir / "report_000000.md"
    assert json_path.is_file()
    assert md_path.read_text(encoding="utf-8").startswith("# Crash Report")
    record = json.loads(json_path.read_text(encoding="utf-8"))
    assert record["target"] == "demo"
    assert record["protocol"] == "ftp"
    assert record["crash"]["returncode"] == -11
    assert record["response_feedback"]["request_sequence"] == [
        "-",
        "CRASH",
    ]
    assert record["response_feedback"]["response_sequence"] == [
        "220",
        "CRASH",
    ]
    assert record["exchanges"][1]["request"]["encoding"] == "base64"
    assert record["exchanges"][1]["request"]["length"] == len(b"CRASH\r\n")
    assert record["llm_report"].startswith("# Crash Report")
    assert chater.usage == "crash_report"
    assert "AddressSanitizer: SEGV" in chater.prompt


def test_executor_does_not_load_checkers_or_hashers_in_replay(
    monkeypatch,
):
    mapper = SimpleNamespace(
        cur_parser=object(),
        equip_checkers=lambda: (_ for _ in ()).throw(
            AssertionError("checker loaded")
        ),
        equip_hashers=lambda: (_ for _ in ()).throw(
            AssertionError("hasher loaded")
        ),
    )
    monkeypatch.setattr(configs, "fuzz_mode", "replay", raising=False)
    monkeypatch.setattr(
        configs, "run_script", Path("/tmp/run.sh"), raising=False
    )
    monkeypatch.setattr(
        configs, "setup_script", Path("/tmp/setup.sh"), raising=False
    )
    monkeypatch.setattr(configs, "host", "127.0.0.1", raising=False)
    monkeypatch.setattr(configs, "port", 1, raising=False)
    monkeypatch.setattr(configs, "trans_layer", "tcp", raising=False)
    monkeypatch.setattr(Executor, "load_parser", lambda self, parser: None)

    executor = Executor(
        mapper=mapper,
        stop_event=threading.Event(),
        cmdline=[],
    )

    assert executor.checker_funcs == {}
    assert executor.hasher_funcs == {}
