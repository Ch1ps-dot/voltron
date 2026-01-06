from pathlib import Path
import yaml, time, threading

from voltron.utils.logger import logger

from voltron.llm.chat import Chater

from voltron.rfcparser.rfcparser import RFCParser

from voltron.handler.handler import Handler

from voltron.executor.executor import Executor
from voltron.utils.analyze import Analyzer

from voltron.sheduler.alphabet import Alphabet
from voltron.sheduler.rands import Rands
from voltron.utils.ui import ui_loop


class Fuzzer:
    def __init__(
            self, 
            time_limit: int,
            target_name: str
        ) -> None:

        self.base_path = Path(__file__).resolve().parents[1]

        self.configs: dict
        with open(self.base_path / 'configs.yaml', 'r', encoding='utf-8') as f:
            self.configs = yaml.safe_load(f)
        if(self.configs == None):
            logger.debug('No Configs') 
            exit(0)

        # key parameter of protocol
        self.pro_name = self.configs[target_name]['protocol']
        self.target_name = target_name
        self.host = self.configs[target_name]['host']
        self.tra_layer = self.configs[target_name]['trans_layer']
        self.port = self.configs[target_name]['port']
        self.rfc_name = self.configs[target_name]['rfc_name']

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
        self.chater = Chater(self.pmp_path, self.configs)

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

    