from pathlib import Path
from types import SimpleNamespace

from click.testing import CliRunner

import cli as cli_module


def test_rfc_parser_option_does_not_start_fuzzer(tmp_path, monkeypatch):
    output_path = tmp_path / "component" / "tree" / "ftp" / "rfc959.pkl"
    calls = []

    monkeypatch.setattr(
        cli_module,
        "parse_target_section_trees",
        lambda target: calls.append(target) or [
            SimpleNamespace(
                rfc_name="rfc959",
                source="regenerated",
                output_path=output_path,
            )
        ],
    )
    monkeypatch.setattr(
        cli_module,
        "Fuzzer",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("Fuzzer must not start in RFC parser mode")
        ),
    )

    result = CliRunner().invoke(
        cli_module.main,
        ["--sut", "lightftp", "--rfc-parser"],
    )

    assert result.exit_code == 0
    assert calls == ["lightftp"]
    assert f"rfc959: regenerated -> {output_path}" in result.output


def test_fuzzing_mode_still_requires_time():
    result = CliRunner().invoke(
        cli_module.main,
        ["--sut", "lightftp"],
    )

    assert result.exit_code == 2
    assert 'Missing option "-t" / "--time" for fuzzing mode.' in result.output


def test_compliance_analysis_option_is_forwarded_to_fuzzer(monkeypatch):
    captured = {}

    class FakeFuzzer:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def fuzz(self, **_kwargs):
            return 0

    monkeypatch.setattr(cli_module, "Fuzzer", FakeFuzzer)

    result = CliRunner().invoke(
        cli_module.main,
        ["--sut", "lightftp", "--time", "1", "--no-compliance-analysis"],
    )

    assert result.exit_code == 0
    assert captured["compliance_analysis"] is False


def test_observer_option_is_forwarded_to_fuzzer(monkeypatch):
    captured = {}

    class FakeFuzzer:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def fuzz(self, **_kwargs):
            return 0

    monkeypatch.setattr(cli_module, "Fuzzer", FakeFuzzer)

    result = CliRunner().invoke(
        cli_module.main,
        ["--sut", "lightftp", "--time", "1", "--no-observer"],
    )

    assert result.exit_code == 0
    assert captured["observer_enabled"] is False


def test_generate_ir_option_does_not_start_fuzzer(tmp_path, monkeypatch):
    output_path = tmp_path / "component" / "ir" / "ftp"
    calls = []

    monkeypatch.setattr(
        cli_module,
        "generate_target_ir",
        lambda target: calls.append(target) or output_path,
    )
    monkeypatch.setattr(
        cli_module,
        "Fuzzer",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("Fuzzer must not start in IR generation mode")
        ),
    )

    result = CliRunner().invoke(
        cli_module.main,
        ["--sut", "lightftp", "--generate-ir"],
    )

    assert result.exit_code == 0
    assert calls == ["lightftp"]
    assert f"IR generated for lightftp -> {output_path}" in result.output


def test_parser_only_options_are_mutually_exclusive(monkeypatch):
    monkeypatch.setattr(
        cli_module,
        "parse_target_section_trees",
        lambda _target: (_ for _ in ()).throw(
            AssertionError("SectionTree parsing must not start")
        ),
    )
    monkeypatch.setattr(
        cli_module,
        "generate_target_ir",
        lambda _target: (_ for _ in ()).throw(
            AssertionError("IR generation must not start")
        ),
    )

    result = CliRunner().invoke(
        cli_module.main,
        ["--sut", "lightftp", "--rfc-parser", "--generate-ir"],
    )

    assert result.exit_code == 2
    assert (
        "--rfc-parser and --generate-ir cannot be used together."
        in result.output
    )


def test_rfc_parser_option_reports_configuration_error(monkeypatch):
    def fail(_target):
        raise ValueError("unknown target: missing")

    monkeypatch.setattr(cli_module, "parse_target_section_trees", fail)

    result = CliRunner().invoke(
        cli_module.main,
        ["--sut", "missing", "--rfc-parser"],
    )

    assert result.exit_code == 1
    assert "Error: unknown target: missing" in result.output


def test_generate_ir_option_reports_configuration_error(monkeypatch):
    def fail(_target):
        raise ValueError("unknown target: missing")

    monkeypatch.setattr(cli_module, "generate_target_ir", fail)

    result = CliRunner().invoke(
        cli_module.main,
        ["--sut", "missing", "--generate-ir"],
    )

    assert result.exit_code == 1
    assert "Error: unknown target: missing" in result.output
