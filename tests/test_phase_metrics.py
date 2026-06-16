import csv
from types import SimpleNamespace

from voltron.analyzer.analyzer import Analyzer
from voltron.configs import configs


def read_phase_rows(path):
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def test_phase_metrics_record_duration_and_tokens(tmp_path, monkeypatch):
    monkeypatch.setattr(configs, "results_path", tmp_path, raising=False)
    metric = Analyzer()

    metric.reset_phase_metrics()
    metric.begin_phase("doc_analysis")
    metric.record_llm_usage(
        duration_s=0.25,
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
    )
    metric.end_phase("doc_analysis")

    rows = read_phase_rows(tmp_path / "phase_metrics.csv")
    assert len(rows) == 1
    row = rows[0]
    assert row["phase"] == "doc_analysis"
    assert row["status"] == "completed"
    assert float(row["duration_s"]) >= 0
    assert row["chat_time_s"] == "0.250000"
    assert row["llm_calls"] == "1"
    assert row["prompt_tokens"] == "10"
    assert row["completion_tokens"] == "5"
    assert row["total_tokens"] == "15"


def test_phase_metrics_can_record_skipped_phase(tmp_path, monkeypatch):
    monkeypatch.setattr(configs, "results_path", tmp_path, raising=False)
    metric = Analyzer()

    metric.reset_phase_metrics()
    metric.record_skipped_phase("model_learning")

    rows = read_phase_rows(tmp_path / "phase_metrics.csv")
    assert len(rows) == 1
    assert rows[0]["phase"] == "model_learning"
    assert rows[0]["status"] == "skipped"
    assert rows[0]["duration_s"] == "0.000000"


def test_phase_metrics_reset_removes_previous_csv(tmp_path, monkeypatch):
    monkeypatch.setattr(configs, "results_path", tmp_path, raising=False)
    metric = Analyzer()
    csv_path = tmp_path / "phase_metrics.csv"
    iteration_csv_path = tmp_path / "model_learning_iterations.csv"
    csv_path.write_text("old\n", encoding="utf-8")
    iteration_csv_path.write_text("old\n", encoding="utf-8")

    metric.reset_phase_metrics()

    assert not csv_path.exists()
    assert not iteration_csv_path.exists()


def test_model_learning_iteration_metrics_are_recorded(tmp_path, monkeypatch):
    monkeypatch.setattr(configs, "results_path", tmp_path, raising=False)
    metric = Analyzer()
    metric.cur_res_types_cnt = {"331": 2, "230": 1}
    metric.cur_resp_trans_cnt = {"USER->331": 2}
    metric.res_types_cnt = {"331": 5, "230": 1, "500": 1}
    metric.resp_trans_cnt = {"USER->331": 4, "PASS->230": 1}
    hypothesis = SimpleNamespace(
        states={1, 2, 3},
        alphabet={"USER", "PASS"},
        delta={
            (1, "USER"): 2,
            (2, "PASS"): 3,
            (3, "USER"): 2,
        },
        output={
            (1, "USER"): "331",
            (2, "PASS"): "230",
            (3, "USER"): "331",
        },
        table=(
            {("-",), ("USER",)},
            {("PASS",)},
            {
                ("-",): {("USER",): ("331",)},
                ("USER",): {("PASS",): ("230",)},
            },
        ),
    )

    metric.record_model_learning_iteration(
        iteration=2,
        hypothesis=hypothesis,
        duration_s=1.25,
        status="improved",
        try_limit=3,
    )

    rows = read_phase_rows(tmp_path / "model_learning_iterations.csv")
    assert len(rows) == 1
    row = rows[0]
    assert row["iteration"] == "2"
    assert row["status"] == "improved"
    assert row["duration_s"] == "1.250000"
    assert row["automata_states"] == "3"
    assert row["automata_transitions"] == "3"
    assert row["alphabet_symbols"] == "2"
    assert row["observation_table_s"] == "2"
    assert row["observation_table_e"] == "1"
    assert row["observation_table_t"] == "2"
    assert row["current_response_types"] == "2"
    assert row["current_response_type_events"] == "3"
    assert row["current_response_transitions"] == "1"
    assert row["current_response_transition_events"] == "2"
    assert row["total_response_types"] == "3"
    assert row["total_response_transitions"] == "2"
