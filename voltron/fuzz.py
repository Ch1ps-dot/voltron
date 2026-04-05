from pathlib import Path
import yaml, time, threading, signal, sys, traceback, pickle, copy, os, atexit

from voltron.executor.conversation import Conversation

from voltron.utils.logger import logger

from voltron.llm.chatter import AsyncChater

from voltron.rfcparser.rfc_parser import AsyncRFCParser

from voltron.producer.producer import AsyncProducer

from voltron.executor.executor import Executor
from voltron.analyzer.analyzer import analyzer

from voltron.mapper.mapper import Mapper
from voltron.scheduler.havoc import Havoc
from voltron.utils.ui import ui_loop

from voltron.configs import configs

from voltron.scheduler.mlstar import MealyLstar, MembershipOracle, EquOracle, ObTable
from voltron.scheduler.automata import MealyMachine

def exit_handler():
    for thread in threading.enumerate():
        if thread.ident:
            fra = sys._current_frames().get(thread.ident)
            logger.debug('\n'.join(traceback.format_stack(fra)))
            
atexit.register(exit_handler)

class Fuzzer:
    def __init__(
            self, 
            target_name: str,
            cmdline: list[str],
            mode='fuzz'
        ) -> None:
        self.target_name = target_name
        self.cmdline = cmdline
        self.mode = mode
        
        self.load_configs()
        self.module_init()
        
    def load_configs(
        self
    ) -> None:
        self.configs_yaml: str
        try:
            with open(configs.base_path / 'configs' /'configs.yaml', 'r', encoding='utf-8') as f:
                configs_yaml = yaml.safe_load(f)
                if self.target_name not in configs_yaml.keys():
                    raise Exception(f'Fuzzer: unknown target {self.target_name}')
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
        configs.run_script = configs.base_path / 'configs' / configs.target_name / 'run.sh'
        configs.setup_script = configs.base_path / 'configs' / configs.target_name / 'setup.sh'
        configs.models_path = configs.base_path / 'component' / 'models' / configs.target_name
        configs.info_path = configs.base_path / 'configs' / configs.target_name / f'{configs.target_name}.md'
        for rfc in configs.rfc_name:
            configs.doc_paths.append(configs.base_path / 'rfcs' / f'{rfc}.txt')
        configs.pmp_path = configs.base_path / 'prompts'
        configs.base_url = configs_yaml['llm']['base_url']
        configs.api_key = configs_yaml['llm']['api_key']
        configs.model = configs_yaml['llm']['model']
        configs.async_sem = configs_yaml['llm']['async_sem']
        configs.server = configs_yaml[self.target_name]['server']
        
        current_time_struct = time.localtime()
        formatted_time = time.strftime("%m%d_%H_%M_%S", current_time_struct)
        results_dir = configs.base_path / f'results-{self.target_name}-voltron-{formatted_time}'
        if not results_dir.is_dir() and self.mode != 'replay':
            results_dir.mkdir()
            
        models_dir = configs.base_path / 'component' / 'models'
        if not models_dir.is_dir():
            models_dir.mkdir(parents=True, exist_ok=True)
            configs.models_path.mkdir(parents=True, exist_ok=True)
        
        configs.results_path = results_dir
        configs.fuzz_mode = self.mode
        
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
        analyzer.stop_event = self.stop_event
        # setup executor
        self.exe = Executor(
            mapper=self.mapper,
            cmdline=self.cmdline,
            stop_event=self.stop_event
        )
       
        print('Executor: equipment setup')

    def fuzz(
        self,
        algo: str,
        time_limit_min: int
    ):
        """Fuzz the target one
        """
        fuzz_loop = None
        self.time_limit_s = time_limit_min * 60
        configs.time_limit_s = self.time_limit_s
        
        if algo == 'rand':
            # fuzz_loop = self.rand_fuzz
            pass
        elif algo == 'state':
            fuzz_loop = self.state_fuzz
        else:
            logger.debug('Fuzzer: no algorithm') 
            return
        
        with analyzer.lock:
            analyzer.strategy = algo
            start_time = time.time()
            analyzer.start_time = start_time

        try:
            signal.signal(signal.SIGINT, self.handle_normal_fuzzer_exit)
            
            # start fuzzing and set up ui
            t_ui   = threading.Thread(target=ui_loop, args=(self.stop_event,))
            t_fuzz = threading.Thread(target=fuzz_loop, args=(self.stop_event,))

            t_fuzz.start()
            t_ui.start()

            t_fuzz.join()
            t_ui.join()
            
        except Exception as e:
            logger.debug(f'fuzzer error: {e}')
            logger.debug(traceback.format_exc())
            self.stop_event.set()
        logger.debug('Fuzzer: finish fuzzing')
        
        # collect results
        with analyzer.lock:
            analyzer.collect_results()
            
    def replay(
        self,
        res_dir: Path,
        cov_folder: Path
    ):
        """Fuzz the target one
        """
        
        with analyzer.lock:
            analyzer.strategy = 'replay'
            start_time = time.time()
            analyzer.start_time = start_time

        try:
            signal.signal(signal.SIGINT, self.handle_normal_fuzzer_exit)
            
            # start fuzzing and set up ui
            t_ui   = threading.Thread(target=ui_loop, args=(self.stop_event,))
            t_fuzz = threading.Thread(target=self.replay_process, args=(res_dir, cov_folder,))

            t_fuzz.start()
            t_ui.start()

            t_fuzz.join()
            t_ui.join()
            
        except Exception as e:
            logger.debug(f'replay error: {e}')
            logger.debug(traceback.format_exc())
            self.stop_event.set()
        logger.debug('Fuzzer: finish replay')
                       
    def state_fuzz(
        self,
        stop_event: threading.Event
    ):
        try:
            # set membership query and equivelence query method.
            mq = MembershipOracle(mapper=self.mapper, executor=self.exe)
            eq = EquOracle(mapper=self.mapper, executor=self.exe)
            
            with analyzer.lock:   
                analyzer.iter = 0
                analyzer.stage = 'model learning'
                
            if not configs.models_path.is_dir():
                configs.models_path.mkdir()
            
            # load previous automata model if it existed
            hypothesis: MealyMachine | None = None
            h_path = configs.models_path / 'evolved_hypothesis.pkl'
            if h_path.is_file():
                with open(h_path, 'rb') as f:
                    hypothesis = pickle.load(f)
            
            begin_time = time.time()
            if hypothesis is None:
                hypothesis = self.model_learning(mq, eq, stop_event)
            else:
                self.mapper.message_pool = hypothesis.map
            end_time = time.time()
            with analyzer.lock:   
                analyzer.model_learning_time_s = end_time - begin_time
            self.havoc_fuzz(hypothesis, stop_event)
                
            self.stop_event.set()
                
        except Exception as e:
            logger.debug(f'Fuzzer: exit {e}') 
            logger.debug(traceback.format_exc())
            stop_event.set()
            
    def model_learning(
        self,
        mq,
        eq,
        stop_event
    ) -> MealyMachine:
        """--- model learning ---"""
        h_lsit: list[MealyMachine] = []
        h_path = configs.models_path / 'evolved_hypothesis.pkl'
        try_limit = 3
        while not stop_event.is_set():
            try:
                cur_id = str(analyzer.iter)
                with analyzer.lock:
                    analyzer.iter += 1
                    analyzer.reset_automata_cnt()
                next_id = str(analyzer.iter)
                
                # run model learning
                with analyzer.lock:   
                    analyzer.stage = 'model learning'
                ml = MealyLstar(mq, eq, self.stop_event)
                h = ml.run(cur_id)
                
                # save and evaluate the automata
                self.mapper.register_mapper(h)
                h.res_types = analyzer.cur_res_types_cnt
                h.res_trans_types = analyzer.cur_resp_trans_cnt

                # select a better generator to evolve
                # the more states transitions the better the generator
                with analyzer.lock:   
                    analyzer.stage = 'fuzzer evolve'
                if len(h_lsit) == 0:
                    h_lsit.append(h)
                    self.producer.generator_evo(h)
                    continue
                last_trans_num = len(h_lsit[-1].res_trans_types.keys())
                cur_trans_num = len(h.res_trans_types.keys())
                
                if last_trans_num >= cur_trans_num:
                    # self.producer.generator_evo(h_lsit[-1], next_id)
                    try_limit -= 1
                    if try_limit <= 0:
                        with open(h_path, 'wb') as f:
                            pickle.dump(h, f)
                        h.graph('evolved')
                        logger.debug('ml: save evolved model')
                        break
                
                elif last_trans_num < cur_trans_num:
                    h_lsit.append(h)
                    self.producer.generator_evo(h)
                    continue

            except Exception as e:
                logger.debug(f'Fuzzer: exit {e}')
                logger.debug(traceback.format_exc())
                stop_event.set()
                sys.exit(1)
            if (configs.time_limit_s < time.time() - analyzer.start_time):
                logger.debug('Fuzzer: timeout')
                stop_event.set()
                
        return h_lsit[-1]
    
    def havoc_fuzz(
        self,
        hypothesis: MealyMachine,
        stop_event
    ):
        """--- havoc fuzzing ---"""
        with analyzer.lock:   
            analyzer.iter = 0
            analyzer.stage = 'havoc fuzzing'
            analyzer.res_types_cnt = {}
            analyzer.resp_trans_cnt = {}
        
        havoc = Havoc(self.mapper, self.exe, hypothesis)
                    
        while not stop_event.is_set():
            try:
                # init new learning process with previous model and run fuzzer

                req_res = havoc.run(500)
                self.producer.generator_mutate(req_res)
                pre_resp = analyzer.cur_res_types_cnt.keys()
                
                # save the results
                with analyzer.lock:   
                    analyzer.iter += 1
                    analyzer.reset_automata_cnt()
                analyzer.collect_results()
                
            except Exception as e:
                logger.debug(f'Fuzzer: exit {e}')
                logger.debug(traceback.format_exc())
                stop_event.set()
                
            if (configs.time_limit_s < time.time() - analyzer.start_time):
                logger.debug('Fuzzer: timeout')
                stop_event.set()
                analyzer.collect_results()
                
    def replay_process(
        self,
        res_dir: Path,
        cov_folder: Path,
    ):
        configs.cov_setup_path =  configs.base_path / 'input' / 'scripts' / configs.target_name / 'cov_setup.sh'
        configs.cov_collect_path =  configs.base_path / 'input' / 'scripts' / configs.target_name / 'cov_collect.sh'
        
        in_dir = res_dir / 'replayable_testcases'
        cov_file = res_dir / 'cov_over_time.csv'
        with analyzer.lock:   
            analyzer.stage = 'replay'
            
        file_count = 0
        try:
            file_paths = [f for f in in_dir.iterdir() if f.is_file()]
            sorted_files = sorted(
                file_paths,
                key=self.get_creation_timestamp,
                reverse=False
            )
            cons_seq: list[Conversation] = []
            file_list: list[Path] = []
            for item in sorted_files:
                if item.is_file():
                    with open(item, 'rb') as f:
                        cons = pickle.load(f)
                        cons_seq.append(cons)
                        file_list.append(item)
                    file_count += 1
            
            analyzer.set_progress('havoc', 'replay', file_count)
            self.exe.cov_setup(cov_folder, cov_file)
            for i in range(file_count):
                req_seq = []
                cons = cons_seq[i]
                for j in range(len(cons.req_seq)):
                    if cons.req_seq[j] == '-':
                        continue
                    req_seq.append((cons.req_seq[j], cons.content[j][0]))
                    
                try:
                    flag, res_cons = self.exe.interact(req_seq, poll_wait_ms=3000)
                except Exception as e:
                    logger.debug(f'replayer: exit {e}')
                    logger.debug(traceback.format_exc())

                with analyzer.lock:
                    analyzer.finished += 1
                    
                self.exe.cov_collect(cov_folder, cov_file, file_list[i])
            self.stop_event.set()
        except Exception as e:
            logger.debug(f'replayer: exit {e}')
            logger.debug(traceback.format_exc())

    def handle_normal_fuzzer_exit(
        self,
        signal_num, 
        frame
    ):
        # Handle normal exit of fuzzer Ctrl+C
        if analyzer.sut_proc != None:
            os.killpg(analyzer.sut_proc.pid, signal.SIGKILL)
            
        # logger.debug('Fuzzer: caught interrupt signal, exiting gracefully...')
        # for thread in threading.enumerate():
        #     if thread.ident:
        #         fra = sys._current_frames().get(thread.ident)
        #         logger.debug('\n'.join(traceback.format_stack(fra)))
        
        self.stop_event.set()
        if self.mode != 'replay':
            with analyzer.lock:
                analyzer.collect_results()
        sys.exit(1)
        
    def get_creation_timestamp(
        self, 
        file: Path
    ) -> float:
        try:
            return file.stat().st_birthtime
        except AttributeError:
            return file.stat().st_ctime