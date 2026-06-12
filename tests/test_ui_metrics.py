import time

from rich.console import Console

from voltron.analyzer.analyzer import analyzer
from voltron.utils.ui import make_info_table, make_runtime_table


def test_fuzz_metric_displays_possible_non_compliance_count():
    original_start_time = getattr(analyzer, "start_time", None)
    original_count = analyzer.non_compliant_num
    try:
        analyzer.start_time = time.time() - 1
        analyzer.non_compliant_num = 7
        console = Console(record=True, width=120)
        console.print(make_runtime_table())
        rendered = console.export_text()
    finally:
        analyzer.non_compliant_num = original_count
        if original_start_time is not None:
            analyzer.start_time = original_start_time

    assert "POSSIBLE NON-COMPLIANCE" in rendered
    assert "7" in rendered


def test_fuzzer_info_displays_current_llm_operation():
    original_operation = analyzer.current_operation
    original_target_name = getattr(analyzer, "target_name", None)
    original_pro_name = getattr(analyzer, "pro_name", None)
    try:
        analyzer.target_name = "demo"
        analyzer.pro_name = "demo-protocol"
        analyzer.current_operation = "Updating checker with LLM"
        console = Console(record=True, width=120)
        console.print(make_info_table())
        rendered = console.export_text()
    finally:
        analyzer.current_operation = original_operation
        if original_target_name is not None:
            analyzer.target_name = original_target_name
        if original_pro_name is not None:
            analyzer.pro_name = original_pro_name

    assert "current operation" in rendered
    assert "Updating checker with LLM" in rendered
