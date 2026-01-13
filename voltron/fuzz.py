from pathlib import Path
import yaml, time, threading, signal, sys

from voltron.utils.logger import logger

from voltron.llm.AsyncChat import AsyncChater

from voltron.rfcparser.AsyncRFCparser import AsyncRFCParser

from voltron.producer.AsyncProducer import AsyncProducer

from voltron.executor.executor import Executor
from voltron.analyzer.analyzer import Analyzer

from voltron.mapper.mapper import Mapper
from voltron.scheduler.rands import Rands
from voltron.utils.ui import ui_loop


class Fuzzer:
    def __init__(
            self, 
            time_limit_min: int,
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
        self.pre_script = self.base_path / 'scripts' / self.target_name / 'pre.sh'
        self.post_script =  self.base_path / 'scripts' / self.target_name / 'post.sh'
        self.doc_path = self.base_path / 'rfcs' / f'{self.rfc_name}.txt'
        self.pmp_path = self.base_path / 'prompts'
        self.eqp_path = self.base_path / 'equipment'

        self.time_limit_s = time_limit_min * 60

        self.module_init()

    def module_init(
            self
    ) -> None:

        # llm init
        self.chater = AsyncChater(
            self.pmp_path, 
            self.configs
        )
        print('Chater: setup')
        
        # metrics analyzer
        self.analyzer = Analyzer(
            pro_name=self.pro_name,
            target_name=self.target_name
        )
        print('Analyzer: setup')

        # rfcparser init
        self.rfcparser = AsyncRFCParser(
            doc_path=self.doc_path,
            pro_name=self.pro_name,
            chater=self.chater,
            rfc_name = self.rfc_name,
            base_path = self.base_path
        )
        print('RFCParser: setup')

        # handler init
        self.handler = AsyncProducer(
            chater=self.chater,
            rfcp=self.rfcparser,
            base_path = self.base_path 
        )
        print('Producer: equipment setup')
        
        # scheduler init
        self.mapper = Mapper(self.handler, self.analyzer)
        
        # setup executor
        self.exe = Executor(
            trans_layer=self.tra_layer,
            host=self.host,
            port=self.port,
            analyzer=self.analyzer,
            pre_script=self.pre_script,
            post_script=self.post_script,
            mapper=self.mapper
        )
        print('Executor: equipment setup')

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
        if fuzz_loop == None:
            logger.debug('Fuzzer: no algorithm') 
            return
        
        with self.analyzer.lock:
            self.analyzer.strategy = algo
        start_time = time.time()
        self.analyzer.start_time = start_time

        self.stop_event = threading.Event()
        signal.signal(signal.SIGINT, self.handle_normal_fuzzer_exit)
        
        # start fuzzing and set up ui
        t_ui   = threading.Thread(target=ui_loop, args=(self.analyzer, self.stop_event,))
        t_fuzz = threading.Thread(target=fuzz_loop, args=(self.stop_event,))

        t_fuzz.start()
        t_ui.start()

        t_fuzz.join()
        t_ui.join()
        logger.debug('Fuzzer: finish fuzzing')
        
        # collect results
        with self.analyzer.lock:
            self.analyzer.collect_results()

    def rand_fuzz(
            self,
            stop_event: threading.Event
    ):
        pass
        while not stop_event.is_set():
            try:
                fuzz = Rands(mapper=self.mapper, executor=self.exe)
                fuzz.run()
            except Exception as e:
                logger.debug(f'Fuzzer: exit {e}')
                exit(0)
            if (self.time_limit_s < time.time() - self.analyzer.start_time):
                stop_event.set()
                logger.debug('Fuzzer: timeout')

    def handle_normal_fuzzer_exit(
            self,
            signal_num, 
            frame
    ):
        # Handle normal exit of fuzzer Ctrl+C
        logger.debug('Fuzzer: caught interrupt signal, exiting gracefully...')
        self.stop_event.set()
        with self.analyzer.lock:
            self.analyzer.collect_results()
        sys.exit(0)
        

    