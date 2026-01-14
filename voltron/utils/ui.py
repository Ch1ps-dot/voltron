import threading
import time
from voltron.utils.logger import logger
from dataclasses import dataclass, field
from voltron.analyzer.analyzer import Analyzer
from rich.layout import Layout
from rich.live import Live
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

@dataclass
class FuzzStats:
    target_name: str = ''
    execs: int = 0
    crashes: int = 0
    timeouts: int = 0
    states: int = 0
    req_num: int = 0
    path_num: int = 0
    res_types_num: int = 0
    trans_types_num: int = 0
    pro_name: str = ''
    strategy: str = ''
    start_time: float = field(default_factory=time.time)
    lock: threading.Lock = field(default_factory=threading.Lock)

def make_ui(
    ):
    layout = Layout()

    layout.split(
        Layout(name="header", size=3),
        Layout(name="body"),
    )

    layout["body"].split_row(
        Layout(name="info"),
        Layout(name="runtime"),
    )

    header = Panel(
        Text(
            f" Protocol Fuzzer [v0.0.1] ",
            justify="center",
            style="bold cyan",
        ),
        style="white on black",
    )
    layout["header"].update(header)

    return layout

def format_duration(
        seconds: int
) -> str:
    d, rem = divmod(seconds, 86400)
    h, rem = divmod(rem, 3600)
    m, s = divmod(rem, 60)
    return f"{d} days, {h:02d} hrs, {m:02d} min, {s:02d} sec"

def make_runtime_table(
        ana: Analyzer
):
    elapsed = int(time.time() - ana.start_time)
    table = Table(title="Fuzzer Runtime", show_header=False, box=None)
    table.add_column(justify='left')
    table.add_column(justify='right')
    data = {
        'run time': format_duration(elapsed),
        'request num': ana.req_num,
        'response num': ana.res_num,
        'exec requ path num': ana.path_num,
        'response types': ana.res_types_num(),
        'response transitions': ana.resp_trans_num(),
        'CRASH_num': ana.crash_num,
        'PULLERR num': ana.pollerr_num,
        'TIMEOUT num': ana.timeout_num,
        'RCLOSE num': ana.rclose_num
    }

    for k, v in data.items():
        table.add_row(k, str(v))

    return table

def make_info_table(
        ana: Analyzer
):
    data = {
        'target name': ana.target_name,
        'protol type': ana.pro_name,
        'strategy': ana.strategy
    }
    table = Table(title="Settings Info", show_header=False, box=None)
    table.add_column(justify='left')
    table.add_column(justify='right')

    for k, v in data.items():
        table.add_row(k, str(v))

    return table

def ui_loop(
        ana: Analyzer, 
        stop_event: threading.Event
    ):
    layout = make_ui()

    with Live(layout, refresh_per_second=1):
        logger.debug('UI: setup')
        while not stop_event.is_set():
            with ana.lock:
                layout["info"].update(make_info_table(ana))
                layout["runtime"].update(make_runtime_table(ana))

            time.sleep(1)