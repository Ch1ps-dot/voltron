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
            target: str,
            time_limit: int,
            target_name: str = ''
        ) -> None:

        with open('configs.yaml', 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)
        
        self.base_path = Path(__file__).resolve().parent.parent

        # key parameter of protocol
        self.pro_name = self.config[target_name]['protocol']
        self.target_name = target
        self.host = self.config[target_name]['host']
        self.tra_layer = self.config[target_name]['trans_layer']
        self.port = self.config[target_name]['port']
        self.rfc_name = self.config[target_name]['rfc_name']

        # some file path 
        self.pre_script = self.base_path / 'script' / self.target_name / 'pre.sh'
        self.post_script =  self.base_path / 'script' / self.target_name / 'post.sh'
        self.doc_path = self.base_path / 'rfcs' / f'{self.rfc_name}.txt'
        self.pmp_path = self.base_path / 'prompts'

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
            rfc_name = self.rfc_name,
            base_path = self.base_path
        )

        # handler init
        self.handler = Handler(
            chater=self.chater,
            rfcp=self.rfcparser,
            base_path = self.base_path 
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
            post_script=self.post_script,
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

        stop_event = threading.Event()
        t_ui   = threading.Thread(target=ui_loop, args=(self.analyzer, stop_event))
        t_fuzz = threading.Thread(target=fuzz_loop, args=(stop_event,))

        t_fuzz.start()
        t_ui.start()

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

    