import threading
import time
from voltron.utils.logger import logger
from dataclasses import dataclass, field
from voltron.analyzer.analyzer import analyzer
from rich.layout import Layout
from rich.live import Live
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.progress import Progress, BarColumn, TextColumn, TimeElapsedColumn


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
    
    layout['info'].split_column(
        Layout(name='algo'),
        Layout(name='progress')
    )

    header = Panel(
        Text(
            f" Voltron [v0.0.2] ",
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

def make_runtime_table():
    ana = analyzer
    elapsed = int(time.time() - ana.start_time)
    table = Table(title="Runtime Metric", show_header=False, box=None, expand=True, show_lines=True)
    table.add_column(justify='left')
    table.add_column(justify='right')
    data = {
        'run time': format_duration(elapsed),
        'synthesis iter': ana.iter,
        'request num': ana.req_num,
        'response num': ana.res_num,
        'query num': f'{ana.path_num}({ana.path_num/(time.time() - analyzer.start_time):.2f})',
        'response types': ana.res_types_num(),
        'response transitions': ana.resp_trans_num(),
        'state num': ana.state,
        'CRASH num': ana.crash_num,
        'CLOSED num': ana.rclose_num,
        'TIMEOUT num': ana.timeout_num
        # 'PULLERR num': ana.pollerr_num,
        # 'TIMEOUT num': ana.timeout_num,
        # 'RCLOSE num': ana.rclose_num
    }

    for k, v in data.items():
        table.add_row(k, str(v))

    return Panel(
            table,
            title="[bold cyan]Fuzz Metric",
            title_align="left",
            expand=True
        )

def make_info_table():
    ana = analyzer
    data = {
        'target name': ana.target_name,
        'protol type': ana.pro_name,
        'strategy': ana.strategy,
        'stage': ana.stage
    }
    table = Table(title="Fuzzer Info", show_header=False, box=None, expand= True, show_lines=True)
    table.add_column(justify='left')
    table.add_column(justify='right')

    for k, v in data.items():
        table.add_row(k, str(v))

    return Panel(
            table,
            title="[bold cyan]Fuzzer Infor",
            title_align="center",
            expand=True
        )

def make_progress_panel():
    if analyzer.show_progress == 'Obtable':
        data = {
            'desc': analyzer.progress_desc,
            'sent': analyzer.sent,
            'recv': analyzer.recv,
        }
        table = Table(title="Progress", show_header=False, box=None, expand= True, show_lines=True)
        table.add_column(justify='left')
        table.add_column(justify='right')
        
        for k, v in data.items():
            table.add_row(k, str(v))
        
        progress_panel = Panel(
            table,
            title="[bold cyan]Task Progress",
            title_align="left",
            expand=True
        )
    
        return progress_panel
    
    elif analyzer.show_progress == 'evolve':
        key = f'{analyzer.progress_desc}'
        v = f'{analyzer.finished}/{analyzer.total}'
        data = {
            key: v
        }
        table = Table(title="Progress", show_header=False, box=None, expand=True, show_lines=True)
        table.add_column(justify='left')
        table.add_column(justify='right')
        
        for k, v in data.items():
            table.add_row(k, str(v))
        
        progress_panel = Panel(
            table,
            title="[bold cyan]Task Progress",
            title_align="left",
            expand=True
        )
    
        return progress_panel
    
    else:
        txt = Text('NO PROGRESS', justify='center')
        return Panel(
            txt,
            title="[bold cyan]Task Progress",
            title_align="center",
            expand=True
        )

def ui_loop(
    stop_event: threading.Event
    ):
    layout = make_ui()
    ana = analyzer
    with Live(layout, refresh_per_second=1):
        logger.debug('UI: setup')
        while not stop_event.is_set():
            with ana.lock:
                layout["algo"].update(make_info_table())
                layout["progress"].update(make_progress_panel())
                layout["runtime"].update(make_runtime_table())

            time.sleep(1)