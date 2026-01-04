import yaml
from .utils.logger import logger

from .llm.chat import Chater

from .rfcparser.rfcparser import RFCParser
from .rfcparser.setciontree import SectionTree

from .handler.handler import Handler

from .executor.executor import Executor
from .utils.analyze import Analyzer

from .sheduler.alphabet import Alphabet, Symbol
from .sheduler.rands import Rands

from pathlib import Path
import os, pickle, json, time, threading
from .utils.ui import ui_loop

class Fuzzer:
    def __init__(
            self, 
            pro_name: str,
            time_limit: int,
            target_name: str = ''
        ) -> None:

        with open('configs.yaml', 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)

        # key parameter of protocol
        self.pro_name = pro_name
        self.target_name = target_name
        self.host = self.config[pro_name]['host']
        self.tra_layer = self.config[pro_name]['trans_layer']
        self.port = self.config[pro_name]['port']
        self.rfc_name = self.config[pro_name]['rfc_name']

        # some file path 
        self.pre_script = self.config[pro_name]['pre_script']
        self.post_script = self.config[pro_name]['post_script']
        self.doc_path = Path.cwd() / 'rfcs' / f'{self.rfc_name}.txt'
        self.pmp_path = Path.cwd() / 'prompts'

        self.time_limit = time_limit

        self.module_init()

    def module_init(
            self
    ) -> None:

        # llm init
        self.chater = Chater(self.pmp_path)

        # rfcparser init
        self.rfcparser = RFCParser(
            doc_path=self.doc_path,
            pro_name=self.pro_name,
            chater=self.chater,
            rfc_name = self.rfc_name
        )

        # handler init
        self.handler = Handler(
            chater=self.chater,
            rfcp=self.rfcparser
        )

        # scheduler init
        self.alphabet = Alphabet(self.handler)

        self.analyzer = Analyzer(
            pro_name=self.pro_name,
            target_name=self.target_name
        )

        # setup executor
        self.exe = Executor(
            trans_layer=self.tra_layer,
            host=self.host,
            port=self.port,
            pre_script=self.pre_script,
            post_scaript=self.post_script,
            handler=self.handler,
            analyzer=self.analyzer
        )

    def fuzz(
            self,
            algo: str
    ):
        """Fuzz the target one
        """
        fuzz_loop = None
        
        logger.debug(f'[Begin Fuzzing]')
        match algo:
            case 'rand':
                fuzz_loop = self.rand_fuzz
        if fuzz_loop == None: raise Exception
        start_time = time.time()
        self.analyzer.start_time = start_time

        # layout = self.make_ui()
        stop_event = threading.Event()
        t_ui   = threading.Thread(target=ui_loop, args=(self.analyzer, stop_event))
        t_fuzz = threading.Thread(target=fuzz_loop, args=(stop_event,))

        t_fuzz.start()
        t_ui.start()
        # with Live(layout, refresh_per_second=1):
        #     layout['settings'].update(self.make_info_table(algo))
        #     layout['runtime'].update(self.make_runtime_table(start_time=start_time))

        #     while time.time() - start_time < self.time_limit * 60:
        #         fuzzing()
        #         layout['runtime'].update(self.make_runtime_table(start_time=start_time))

    def rand_fuzz(
            self,
            stop_event: threading.Event
    ):
        while not stop_event.is_set():
            sched = Rands(self.alphabet)
            path = sched.select(10)
            self.exe.run(path=path)
            if (self.time_limit > time.time() - self.analyzer.start_time):
                stop_event.is_set()

    # """ 
    # ==== UI Related Function ===
    # """

    # def make_ui(
    #         self
    #     ):
    #     layout = Layout()

    #     layout.split(
    #         Layout(name="header", size=3),
    #         Layout(name="body"),
    #     )

    #     layout["body"].split_row(
    #         Layout(name="settings"),
    #         Layout(name="runtime"),
    #     )

    #     header = Panel(
    #         Text(
    #             f" Protocol Fuzzer [v0.0.1] ",
    #             justify="center",
    #             style="bold cyan",
    #         ),
    #         style="white on black",
    #     )
    #     layout["header"].update(header)

    #     return layout

    # def format_duration(
    #         self, 
    #         seconds: int
    # ) -> str:
    #     d, rem = divmod(seconds, 86400)
    #     h, rem = divmod(rem, 3600)
    #     m, s = divmod(rem, 60)
    #     return f"{d} days, {h:02d} hrs, {m:02d} min, {s:02d} sec"

    # def make_runtime_table(
    #         self,
    #         start_time
    # ):
    #     elapsed = int(time.time() - start_time)
    #     table = Table(title="Fuzzer Runtime", show_header=False, box=None)
    #     table.add_column(justify='left')
    #     table.add_column(justify='right')
    #     data = {
    #         'run time': self.format_duration(elapsed),
    #         'sent request num': self.analyzer.req_num,
    #         'exec path num': self.analyzer.path_num,
    #         'recv response types': self.analyzer.res_types_num(),
    #         'req/res pairs': self.analyzer.trans_types_num()
    #     }

    #     for k, v in data.items():
    #         table.add_row(k, str(v))

    #     return table
    
    # def make_info_table(
    #         self,
    #         strategy: str
    # ):
    #     data = {
    #         'target name': self.target_name,
    #         'protol type': self.pro_name,
    #         'strategy': strategy
    #     }
    #     table = Table(title="Settings Info", show_header=False, box=None)
    #     table.add_column(justify='left')
    #     table.add_column(justify='right')

    #     for k, v in data.items():
    #         table.add_row(k, str(v))

    #     return table


        

