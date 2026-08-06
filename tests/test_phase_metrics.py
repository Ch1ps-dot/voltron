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
    generator_csv_path = tmp_path / "generator_iteration_metrics.csv"
    csv_path.write_text("old\n", encoding="utf-8")
    iteration_csv_path.write_text("old\n", encoding="utf-8")
    generator_csv_path.write_text("old\n", encoding="utf-8")

    metric.reset_phase_metrics()

    assert not csv_path.exists()
    assert not iteration_csv_path.exists()
    assert not generator_csv_path.exists()


def test_model_learning_iteration_metrics_are_recorded(tmp_path, monkeypatch):
    monkeypatch.setattr(configs, "results_path", tmp_path, raising=False)
    metric = Analyzer()
    metric.cur_res_types_cnt = {"331": 2, "230": 1}
    metric.cur_resp_trans_cnt = {"USER->331": 2}
    metric.res_types_cnt = {"331": 5, "230": 1, "500": 1}
    metric.resp_trans_cnt = {"USER->331": 4, "PASS->230": 1}
    metric.lifetime_res_types_cnt = {"220": 2, "331": 5, "230": 1}
    metric.lifetime_resp_trans_cnt = {
        "-->220": 2,
        "220->331": 5,
        "331->230": 1,
    }
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
    assert row["lifetime_response_types"] == "3"
    assert row["lifetime_response_type_events"] == "8"
    assert row["lifetime_response_transitions"] == "3"
    assert row["lifetime_response_transition_events"] == "8"


def test_lifetime_response_metrics_survive_phase_resets():
    metric = Analyzer()

    metric.res_types_update("220")
    metric.resp_trans_update("-/220")
    metric.res_types_update("331")
    metric.resp_trans_update("220/331")
    metric.res_types_update("331")
    metric.resp_trans_update("220/331")

    metric.reset_automata_cnt()
    metric.res_types_cnt = {}
    metric.resp_trans_cnt = {}

    assert metric.res_types_num() == 0
    assert metric.resp_trans_num() == 0
    assert metric.lifetime_res_events_num() == 3
    assert metric.lifetime_res_types_num() == 2
    assert metric.lifetime_resp_trans_events_num() == 3
    assert metric.lifetime_resp_trans_num() == 2


def test_state_snapshots_are_written_only_for_new_response_graph_items(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(configs, "results_path", tmp_path, raising=False)
    monkeypatch.setattr("voltron.analyzer.analyzer.time.time", lambda: 125.5)
    metric = Analyzer()
    metric.target_name = "demo"
    metric.start_time = 100.0

    metric.res_types_update("220")
    metric.resp_trans_update("-/220")
    metric.res_types_update("220")
    metric.resp_trans_update("-/220")

    rows = read_phase_rows(tmp_path / "states.csv")
    assert len(rows) == 12
    assert {row["event"] for row in rows} == {
        "new_response_type",
        "new_response_transition",
    }
    assert {row["event_value"] for row in rows} == {"220", "-/220"}
    assert {row["event_timestamp"] for row in rows} == {"125.500000"}
    assert {row["elapsed_seconds"] for row in rows} == {"25.500000"}
    assert {row["time"] for row in rows} == {"0"}

    first_snapshot = rows[:6]
    second_snapshot = rows[6:]
    assert {row["data_type"] for row in first_snapshot} == {
        "nodes",
        "edges",
        "lifetime_response_events",
        "lifetime_response_types",
        "lifetime_response_transition_events",
        "lifetime_response_transitions",
    }
    assert {
        row["data"] for row in first_snapshot if row["data_type"] == "nodes"
    } == {"1"}
    assert {
        row["data"] for row in second_snapshot if row["data_type"] == "edges"
    } == {"1"}


def test_generator_checkpoints_record_cumulative_values_and_deltas(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(configs, "results_path", tmp_path, raising=False)
    metric = Analyzer()
    metric.start_time = 0
    metric.reset_phase_metrics()

    metric.record_generator_checkpoint(
        phase="model_learning",
        checkpoint_type="model_learning_baseline",
        phase_iteration=0,
        baseline_operation_id="initial_generator",
    )
    metric.res_types_update("220")
    metric.resp_trans_update("-/220")
    metric.res_types_update("331")
    metric.resp_trans_update("220/331")
    metric.record_generator_checkpoint(
        phase="model_learning",
        checkpoint_type="before_generator_evolve",
        phase_iteration=0,
        operation_id="evolve-0",
        model_id="0",
        iteration_status="initial",
    )

    metric.res_types_update("331")
    metric.resp_trans_update("220/331")
    metric.res_types_update("230")
    metric.resp_trans_update("331/230")
    metric.record_generator_checkpoint(
        phase="model_learning",
        checkpoint_type="before_generator_evolve",
        phase_iteration=1,
        operation_id="evolve-1",
        model_id="1",
        iteration_status="improved",
    )

    metric.record_generator_checkpoint(
        phase="fuzzing",
        checkpoint_type="fuzzing_baseline",
        phase_iteration=0,
        baseline_operation_id="initial_mutator",
    )
    metric.res_types_update("500")
    metric.resp_trans_update("230/500")
    metric.record_generator_checkpoint(
        phase="fuzzing",
        checkpoint_type="before_generator_mutate",
        phase_iteration=0,
        operation_id="mutate-0",
        mutated_types=["PASS", "USER"],
    )
    metric.res_types_update("500")
    metric.resp_trans_update("230/500")
    metric.finalize_generator_metrics(phase_iteration=1)
    metric.finalize_generator_metrics(phase_iteration=1)

    rows = read_phase_rows(
        tmp_path / "generator_iteration_metrics.csv"
    )
    assert len(rows) == 6

    assert rows[0]["checkpoint_type"] == "model_learning_baseline"
    assert rows[0]["delta_response_types"] == "0"
    assert rows[0]["delta_response_transitions"] == "0"

    assert rows[1]["operation_id"] == "evolve-0"
    assert rows[1]["evaluated_operation_id"] == "initial_generator"
    assert rows[1]["lifetime_response_types"] == "2"
    assert rows[1]["delta_response_types"] == "2"
    assert rows[1]["lifetime_response_transitions"] == "2"
    assert rows[1]["delta_response_transitions"] == "2"

    assert rows[2]["operation_id"] == "evolve-1"
    assert rows[2]["evaluated_operation_id"] == "evolve-0"
    assert rows[2]["delta_response_events"] == "2"
    assert rows[2]["delta_response_types"] == "1"
    assert rows[2]["delta_transition_events"] == "2"
    assert rows[2]["delta_response_transitions"] == "1"

    assert rows[3]["checkpoint_type"] == "fuzzing_baseline"
    assert rows[3]["evaluated_operation_id"] == "initial_mutator"
    assert rows[3]["delta_response_types"] == "0"
    assert rows[3]["delta_response_transitions"] == "0"

    assert rows[4]["operation_id"] == "mutate-0"
    assert rows[4]["evaluated_operation_id"] == "initial_mutator"
    assert rows[4]["mutated_types"] == '["PASS","USER"]'
    assert rows[4]["delta_response_types"] == "1"
    assert rows[4]["delta_response_transitions"] == "1"

    assert rows[5]["checkpoint_type"] == "run_final"
    assert rows[5]["evaluated_operation_id"] == "mutate-0"
    assert rows[5]["delta_response_events"] == "1"
    assert rows[5]["delta_response_types"] == "0"
    assert rows[5]["delta_transition_events"] == "1"
    assert rows[5]["delta_response_transitions"] == "0"
