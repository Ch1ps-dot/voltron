from pathlib import Path
import yaml, time, threading, signal, sys, traceback, pickle, copy

from voltron.utils.logger import logger

from voltron.llm.AsyncChat import AsyncChater

from voltron.rfcparser.AsyncRFCparser import AsyncRFCParser

from voltron.producer.AsyncProducer import AsyncProducer

from voltron.executor.executor import Executor
from voltron.analyzer.analyzer import analyzer

from voltron.mapper.mapper import Mapper
from voltron.scheduler.rands import Rands
from voltron.utils.ui import ui_loop

from voltron.configs import configs

from voltron.scheduler.mlstar import MealyLstar, MembershipOracle, EquOracle, ObTable
from voltron.scheduler.automata import MealyMachine


class Fuzzer:
    def __init__(
            self, 
            time_limit_min: int,
            target_name: str
        ) -> None:
        self.target_name = target_name
        self.time_limit_s = time_limit_min * 60

        self.load_configs()
        self.module_init()
        
    def load_configs(
        self
    ) -> None:
        self.configs_yaml: str
        try:
            with open(configs.base_path / 'configs.yaml', 'r', encoding='utf-8') as f:
                configs_yaml = yaml.safe_load(f)
        except Exception as e:
            logger.error(f'Fuzzer: config load failure {e}')
            
        # key parameter of protocol
        configs.pro_name = configs_yaml[self.target_name]['protocol']
        configs.target_name = self.target_name
        configs.host = configs_yaml[self.target_name]['host']
        configs.trans_layer = configs_yaml[self.target_name]['trans_layer']
        configs.port = configs_yaml[self.target_name]['port']
        configs.rfc_name = configs_yaml[self.target_name]['rfc_name']

        # some file path 
        configs.pre_script = configs.base_path / 'input' / 'scripts' / configs.target_name / 'pre.sh'
        configs.post_script =  configs.base_path / 'input' / 'scripts' / configs.target_name / 'post.sh'
        configs.info_path = configs.base_path / 'input' / 'infos' / f'{configs.target_name}.md'
        configs.doc_path = configs.base_path / 'input' / 'rfcs' / f'{configs.rfc_name}.txt'
        configs.pmp_path = configs.base_path / 'input' / 'prompts'
        configs.base_url = configs_yaml['llm']['base_url']
        configs.api_key = configs_yaml['llm']['api_key']
        configs.model = configs_yaml['llm']['model']
        configs.async_sem = configs_yaml['llm']['async_sem']
        
        configs.time_limit_s = self.time_limit_s
        
        current_time_struct = time.localtime()
        formatted_time = time.strftime("%m%d_%H_%M_%S", current_time_struct)
        results_dir = configs.base_path / f'results-{self.target_name}-voltron-{formatted_time}'
        if not results_dir.is_dir():
            results_dir.mkdir()
        
        configs.results_path = results_dir
        
        analyzer.pro_name = configs.pro_name
        analyzer.target_name = configs.target_name

    def module_init(
            self
    ) -> None:

        # llm init
        self.chater = AsyncChater()
        print('Chater: setup')
        
        # metrics analyzer
        print('Analyzer: setup')

        # rfcparser init
        self.rfcparser = AsyncRFCParser(
            chater=self.chater
        )
        self.rfcparser.run()
        print('RFCParser: setup')

        # handler init
        self.producer = AsyncProducer(
            chater=self.chater,
            rfcp=self.rfcparser
        )
        self.producer.run()
        print('Producer: equipment setup')
        
        # scheduler init
        self.mapper = Mapper(self.producer)
        
        self.stop_event = threading.Event()
        # setup executor
        self.exe = Executor(
            mapper=self.mapper,
            stop_event=self.stop_event
        )
       
        print('Executor: equipment setup')

    def fuzz(
            self,
            algo: str
    ):
        """Fuzz the target one
        """
        fuzz_loop = None
        
        if algo == 'rand':
            fuzz_loop = self.rand_fuzz
        elif algo == 'state':
            fuzz_loop = self.state_fuzz
        else:
            logger.debug('Fuzzer: no algorithm') 
            return
        
        with analyzer.lock:
            analyzer.strategy = algo
            start_time = time.time()
            analyzer.start_time = start_time

        
        signal.signal(signal.SIGINT, self.handle_normal_fuzzer_exit)
        
        # start fuzzing and set up ui
        t_ui   = threading.Thread(target=ui_loop, args=(self.stop_event,))
        t_fuzz = threading.Thread(target=fuzz_loop, args=(self.stop_event,))

        t_fuzz.start()
        t_ui.start()

        t_fuzz.join()
        t_ui.join()
        logger.debug('Fuzzer: finish fuzzing')
        
        # collect results
        with analyzer.lock:
            analyzer.collect_results()

    def rand_fuzz(
            self,
            stop_event: threading.Event
    ):
        fuzz = Rands(mapper=self.mapper, executor=self.exe)
        while not stop_event.is_set():
            try:
                if not fuzz.run():
                    stop_event.set()
            except Exception as e:
                logger.debug(f'Fuzzer: exit {e}')
                logger.debug(traceback.format_exc())
                stop_event.set()
            if (configs.time_limit_s < time.time() - analyzer.start_time):
                stop_event.set()
                logger.debug('Fuzzer: timeout')
                
    def state_fuzz(
        self,
        stop_event: threading.Event
    ):
        try:
            # set membership query and equivelence query method.
            mq = MembershipOracle(mapper=self.mapper, executor=self.exe)
            eq = EquOracle(mapper=self.mapper, executor=self.exe)
            h_lsit: list[MealyMachine] = []
            marked_table: ObTable # final learned model
            analyzer.iter = 0
            
            """--- model learning ---"""
            while not stop_event.is_set():
                try:
                    
                    with analyzer.lock:
                        analyzer.iter += 1
                        analyzer.cur_res_types_cnt = {}
                        analyzer.cur_resp_trans_cnt = {}
                    id = str(analyzer.iter)
                    
                    # run model learning
                    ml = MealyLstar(mq, eq, self.stop_event)
                    h = ml.run(id)
                    self.mapper.register_mapper(h)
                    marked_table = ml.table
                    
                    # save and evaluate the automata
                    with open(configs.results_path / f'model_{analyzer.iter}.pkl', 'wb') as f:
                        pickle.dump(h, f)
                    h.graph(id)
                    h.res_types = analyzer.cur_res_types_cnt
                    h.res_trans_types = analyzer.cur_resp_trans_cnt

                    if len(h_lsit) == 0:
                        h_lsit.append(h)
                        self.producer.generator_evo(h, id)
                        continue
                    # select a better generator to evolve
                    # the more states transitions the better the generator
                    last_states_num = len(h_lsit[-1].res_trans_types.keys())
                    cur_states_num = len(h.res_trans_types.keys())
                    
                    if last_states_num > cur_states_num:
                        self.producer.generator_evo(h_lsit[-1], id)
                        continue
                    
                    elif last_states_num < cur_states_num:
                        h_lsit.append(h)
                        self.producer.generator_evo(h, id)
                        continue

                except Exception as e:
                    logger.debug(f'Fuzzer: exit {e}')
                    logger.debug(traceback.format_exc())
                    stop_event.set()
                if (configs.time_limit_s < time.time() - analyzer.start_time):
                    stop_event.set()
                    logger.debug('Fuzzer: timeout')
            
            """--- havoc mutate ---"""
            with analyzer.lock:   
                analyzer.iter = 0
            mh_list: list[MealyMachine] = [h_lsit[-1]]
            S = marked_table.S
            E = marked_table.E
            T = marked_table.T
            
            while not stop_event.is_set():
                try:
                    # mutate generator
                    if analyzer.iter == 0:
                        self.producer.generator_mutate(mh_list[0], f'{analyzer.iter}-havoc')

                    # init new learning process with previous model
                    havoc_ml = MealyLstar(mq=mq, eq=eq, stop_event=self.stop_event, table=(S, E, T))
                    
                    # run fuzzer
                    mh = havoc_ml.havoc_run(f'{analyzer.iter}-havoc')
                    self.mapper.register_mapper(mh)
                    with analyzer.lock:   
                        analyzer.iter += 1
                    
                    # save the results
                    with open(configs.results_path / f'model_{analyzer.iter}[m].pkl', 'wb') as f:
                        pickle.dump(mh, f)
                    mh.graph(id)
                    mh.res_types = analyzer.cur_res_types_cnt
                    mh.res_trans_types = analyzer.cur_resp_trans_cnt
                    
                except Exception as e:
                    logger.debug(f'Fuzzer: exit {e}')
                    logger.debug(traceback.format_exc())
                    stop_event.set()
                if (configs.time_limit_s < time.time() - analyzer.start_time):
                    stop_event.set()
                    logger.debug('Fuzzer: timeout')
                
        except Exception as e:
            logger.debug(f'Fuzzer: exit {e}') 
            logger.debug(traceback.format_exc())
            stop_event.set()

    def handle_normal_fuzzer_exit(
            self,
            signal_num, 
            frame
    ):
        # Handle normal exit of fuzzer Ctrl+C
        logger.debug('Fuzzer: caught interrupt signal, exiting gracefully...')
        self.stop_event.set()
        with analyzer.lock:
            analyzer.collect_results()
        sys.exit(0)