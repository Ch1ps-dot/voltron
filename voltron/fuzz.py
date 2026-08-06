from pathlib import Path
import yaml, time, threading, signal, sys, traceback, pickle, copy, os, atexit, subprocess, json

from voltron.executor.conversation import Conversation

from voltron.utils.logger import configure_file_logging, logger_fuzz as logger

from voltron.llm.chatter import AsyncChater, LLMDeadlineExceeded

from voltron.rfcparser.rfc_parser import AsyncRFCParser

from voltron.synthesizer.synthesizer import AsyncProducer

from voltron.executor.executor import Executor
from voltron.analyzer.analyzer import analyzer

from voltron.executor.mapper import Mapper
from voltron.scheduler.berserker import Berserker
from voltron.scheduler.seed_retention import SeedRetentionPolicy
from voltron.utils.ui import ui_loop

from voltron.configs import configs

from voltron.learner.mlstar import (
    MealyLstar,
    MembershipOracle,
    EquOracle,
    ObTable,
    ModelLearningStopped,
    ModelLearningThresholdReached,
)
from voltron.learner.automata import MealyMachine
from voltron.learner.partial_guidance import (
    ModelLearningThreshold,
    PartialStateGraph,
    PartialTraceRecorder,
)


class NoCoverageInputError(RuntimeError):
    """Coverage replay cannot proceed because no valid testcase exists."""

def exit_handler():
    for thread in threading.enumerate():
        if thread.ident:
            fra = sys._current_frames().get(thread.ident)
            logger.debug('\n'.join(traceback.format_stack(fra)))

if os.getenv('VOLTRON_DUMP_THREADS_ON_EXIT') == '1':
    atexit.register(exit_handler)

class Fuzzer:
    def __init__(
            self, 
            target_name: str,
            cmdline: list[str] = [],
            mode='fuzz',
            output='default',
            spec_knowledge: bool = True,
            state_learning: bool = True,
            guided_scheduling: bool = True,
            compliance_analysis: bool = True,
            observer_enabled: bool = True,
        ) -> None:
        self.target_name = target_name
        self.cmdline = cmdline
        self.mode = mode
        self.output = output
        self.spec_knowledge = spec_knowledge
        self.state_learning = state_learning
        self.guided_scheduling = guided_scheduling
        self.compliance_analysis = compliance_analysis
        self.observer_enabled = observer_enabled
        self._cleanup_lock = threading.RLock()
        self._cleanup_done = False
        self._previous_sigint_handler = None
        self._signal_handler_installed = False
        self._worker_threads: list[threading.Thread] = []
        self.stop_event = threading.Event()
        analyzer.stop_event = self.stop_event
        atexit.register(self.cleanup)
        self._install_signal_handlers()

        try:
            self.load_configs()
            self.module_init()
        except BaseException:
            self.cleanup()
            raise

    def load_configs(
        self
    ) -> None:
        self.configs_yaml: str
        try:
            with open(configs.base_path / 'config' /'configs.yaml', 'r', encoding='utf-8') as f:
                configs_yaml = yaml.safe_load(f)
                if self.target_name not in configs_yaml.keys():
                    raise Exception(f'Fuzzer: unknown target {self.target_name}')
        except Exception:
            logger.exception('Fuzzer: config load failure')
            
        # key parameter of protocol
        configs.pro_name = configs_yaml[self.target_name]['protocol']
        configs.target_name = self.target_name
        configs.host = configs_yaml[self.target_name]['host']
        configs.trans_layer = configs_yaml[self.target_name]['trans_layer']
        configs.port = configs_yaml[self.target_name]['port']
        configs.rfc_name = configs_yaml[self.target_name]['rfc_name']
        configs.sut_deployment = configs_yaml[self.target_name].get(
            'sut_deployment',
            'local',
        )
        configs.monitor = configs_yaml[self.target_name].get('monitor', {})
        executor_config = configs_yaml.get('executor', {})
        target_config = configs_yaml[self.target_name]
        configs.setup_timeout_s = max(
            0.1,
            float(target_config.get(
                'setup_timeout_seconds',
                executor_config.get('setup_timeout_seconds', 30.0),
            )),
        )
        configs.readiness_timeout_s = max(
            0.1,
            float(target_config.get(
                'readiness_timeout_seconds',
                executor_config.get('readiness_timeout_seconds', 5.0),
            )),
        )
        configs.port_release_timeout_s = max(
            0.1,
            float(target_config.get(
                'port_release_timeout_seconds',
                executor_config.get('port_release_timeout_seconds', 3.0),
            )),
        )

        # some file path 
        configs.run_script = configs.base_path / 'config' / 'subjects' / configs.target_name / 'run.sh'
        configs.setup_script = configs.base_path / 'config' / 'subjects' / configs.target_name / 'setup.sh'
        readiness_script = target_config.get('readiness_script')
        configs.readiness_script = (
            configs.base_path
            / 'config'
            / 'subjects'
            / configs.target_name
            / readiness_script
            if isinstance(readiness_script, str) and readiness_script.strip()
            else None
        )
        readiness_adapter = target_config.get('readiness_adapter', '')
        configs.readiness_adapter = (
            readiness_adapter.strip()
            if isinstance(readiness_adapter, str)
            else ''
        )
        configs.models_path = configs.base_path / 'component' / 'models' / configs.target_name
        configs.info_path = configs.base_path / 'config' / 'subjects' / configs.target_name / 'info.md'
        for rfc in configs.rfc_name:
            configs.doc_paths.append(configs.base_path / 'config' / 'rfcs' / f'{rfc}.txt')
        configs.pmp_path = configs.base_path / 'skills'
        configs.base_url_doc = configs_yaml['llm_doc']['base_url']
        configs.api_key_doc = configs_yaml['llm_doc']['api_key']
        configs.model_doc = configs_yaml['llm_doc']['model']
        configs.async_sem_doc = configs_yaml['llm_doc']['async_sem']
        
        configs.base_url_fuzz = configs_yaml['llm_fuzz']['base_url']
        configs.api_key_fuzz = configs_yaml['llm_fuzz']['api_key']
        configs.model_fuzz = configs_yaml['llm_fuzz']['model']
        configs.async_sem_fuzz = configs_yaml['llm_fuzz']['async_sem']
        configs.server = configs_yaml[self.target_name]['server']
        
        current_time_struct = time.localtime()
        formatted_time = time.strftime("%m%d_%H_%M_%S", current_time_struct)
        results_dir = configs.base_path / f'results-{self.target_name}-voltron-{formatted_time}'
        if self.output != 'default':
            results_dir = configs.base_path / self.output
        if not results_dir.is_dir() and self.mode != 'replay':
            results_dir.mkdir()
            
        models_dir = configs.base_path / 'component' / 'models'
        if not models_dir.is_dir():
            models_dir.mkdir(parents=True, exist_ok=True)
            configs.models_path.mkdir(parents=True, exist_ok=True)
        
        configs.results_path = results_dir
        if self.mode != 'replay' or self.output != 'default':
            configure_file_logging(configs.results_path)
        analyzer.reset_phase_metrics()
        configs.fuzz_mode = self.mode
        configs.spec_knowledge = self.spec_knowledge
        configs.state_learning = self.state_learning
        configs.guided_scheduling = self.guided_scheduling
        configs.compliance_analysis = self.compliance_analysis
        configs.observer_enabled = self.observer_enabled
        ir_evolution = configs_yaml.get('ir_evolution', {})
        configs.ir_evolution_enabled = ir_evolution.get('enabled', True)
        configs.ir_evolution_failure_threshold = ir_evolution.get(
            'failure_threshold',
            3,
        )
        configs.ir_evolution_max_rounds_per_type = ir_evolution.get(
            'max_rounds_per_type',
            1,
        )
        generated_code = configs_yaml.get('generated_code', {})
        configs.generation_retry_limit = max(
            1,
            int(generated_code.get('retry_limit', 3)),
        )
        configs.generated_code_timeout_s = max(
            0.1,
            float(generated_code.get('timeout_seconds', 2.0)),
        )
        configs.generated_message_max_bytes = max(
            1,
            int(generated_code.get('max_message_bytes', 1024 * 1024)),
        )
        configs.prompt_context_max_chars = max(
            512,
            int(generated_code.get('prompt_context_max_chars', 12_000)),
        )
        response_components = configs_yaml.get('response_components', {})
        lazy_generation = response_components.get('lazy_generation', True)
        if not isinstance(lazy_generation, bool):
            raise TypeError(
                'response_components.lazy_generation must be a boolean'
            )
        configs.response_component_lazy_generation = lazy_generation
        prewarm_types = response_components.get('prewarm_types', [])
        if not isinstance(prewarm_types, list):
            raise TypeError('response_components.prewarm_types must be a list')
        configs.response_component_prewarm_types = [
            str(item).strip()
            for item in prewarm_types
            if str(item).strip()
        ]
        learning_config = configs_yaml.get('model_learning', {})
        partial_guidance_enabled = learning_config.get(
            'partial_guidance_enabled',
            True,
        )
        if not isinstance(partial_guidance_enabled, bool):
            raise TypeError(
                'model_learning.partial_guidance_enabled must be a boolean'
            )
        configs.partial_guidance_enabled = partial_guidance_enabled
        
        analyzer.pro_name = configs.pro_name
        analyzer.target_name = configs.target_name

    def module_init(
            self
    ) -> None:

        # llm init
        self.chater = AsyncChater(configs.base_url_doc, configs.api_key_doc, configs.model_doc)
        self.chater_fuzz = AsyncChater(configs.base_url_fuzz, configs.api_key_fuzz, configs.model_fuzz)
        print('Chater: setup')
        
        # metrics analyzer
        print('Analyzer: setup')

        # rfcparser init
        analyzer.begin_phase('doc_analysis')
        doc_phase_status = 'completed'
        try:
            self.rfcparser = AsyncRFCParser(
                chater=self.chater
            )
            self.rfcparser.run(use_spec_knowledge=self.spec_knowledge)
            print('RFCParser: setup')

            # handler init
            self.producer = AsyncProducer(
                chater=self.chater_fuzz,
                rfcp=self.rfcparser
            )
            self.producer.run()
            print('Producer: equipment setup')
        except BaseException:
            doc_phase_status = 'failed'
            raise
        finally:
            analyzer.end_phase('doc_analysis', doc_phase_status)
        
        # scheduler init
        self.mapper = Mapper(self.producer)
        
        # setup executor
        self.exe = Executor(
            mapper=self.mapper,
            cmdline=self.cmdline,
            stop_event=self.stop_event
        )
       
        print('Executor: equipment setup')

    def _request_stop(self, reason: str) -> None:
        """Set a classified stop reason and signal this fuzzer's event."""
        request_stop = getattr(analyzer, 'request_stop', None)
        if callable(request_stop):
            request_stop(reason, self.stop_event)
        else:
            self.stop_event.set()

    def _finalize_run_status(self) -> int:
        """Persist an authoritative run result and return its process code."""
        now = time.time()
        planned = float(getattr(self, 'time_limit_s', 0) or 0)
        started = getattr(analyzer, 'start_time', now)
        actual = max(0.0, now - started)
        reason = getattr(analyzer, 'stop_reason', None)
        if reason is None and planned > 0 and actual >= planned:
            reason = 'deadline'
            analyzer.stop_reason = reason

        phase_metrics = getattr(analyzer, 'phase_metrics', {})
        fuzz_phase = phase_metrics.get('fuzzing', {})
        if reason == 'deadline':
            if fuzz_phase.get('status') == 'deadline_reached':
                run_status = 'completed'
                exit_code = 0
            else:
                run_status = 'deadline_before_fuzzing'
                exit_code = 2
        elif reason in {
            'failure',
            'model_learning_failure',
            'sut_failure',
            'coverage_failure',
        }:
            run_status = 'failed'
            exit_code = 1
        elif reason in {'external_interrupt', 'cancelled'}:
            run_status = 'interrupted'
            exit_code = 130
        elif reason is None:
            run_status = 'incomplete'
            exit_code = 2
            reason = 'unknown'
            analyzer.stop_reason = reason
        else:
            run_status = 'incomplete'
            exit_code = 2

        analyzer.run_status = run_status
        analyzer.planned_duration_s = planned
        analyzer.actual_duration_s = actual
        status = {
            'run_status': run_status,
            'stop_reason': reason,
            'planned_duration_s': planned,
            'actual_duration_s': actual,
            'exit_code': exit_code,
            'target': getattr(self, 'target_name', ''),
            'algorithm': getattr(analyzer, 'strategy', ''),
            'phases': {
                name: metric.get('status')
                for name, metric in phase_metrics.items()
            },
        }
        try:
            target = configs.results_path / 'run_status.json'
            temporary = target.with_suffix('.json.tmp')
            temporary.write_text(
                json.dumps(status, indent=2, ensure_ascii=False) + '\n',
                encoding='utf-8',
            )
            temporary.replace(target)
        except Exception:
            logger.exception('Fuzzer: failed to write run status')
        return exit_code

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
            analyzer.run_status = 'running'
            analyzer.planned_duration_s = self.time_limit_s

        exit_code = 2
        run_error: BaseException | None = None
        try:
            self._install_signal_handlers()
            worker_failure: list[tuple[BaseException, str]] = []

            def run_fuzz_worker() -> None:
                try:
                    fuzz_loop(self.stop_event)
                except BaseException as error:
                    worker_failure.append((error, traceback.format_exc()))
                    self._request_stop('failure')
            
            # start fuzzing and set up ui
            t_ui = threading.Thread(
                target=ui_loop,
                args=(self.stop_event,),
                name='voltron-ui',
                daemon=True,
            )
            t_fuzz = threading.Thread(
                target=run_fuzz_worker,
                name='voltron-fuzz',
                daemon=True,
            )
            self._worker_threads = [t_fuzz, t_ui]

            t_fuzz.start()
            t_ui.start()

            t_fuzz.join()
            t_ui.join()
            if worker_failure:
                error, worker_traceback = worker_failure[0]
                raise RuntimeError(
                    'voltron-fuzz worker failed:\n'
                    f'{worker_traceback}'
                ) from error
            
        except KeyboardInterrupt:
            logger.debug('Fuzzer: interrupted')
            self._request_stop('external_interrupt')
        except BaseException as error:
            logger.exception('Fuzzer: fuzzing failed')
            self._request_stop('failure')
            run_error = error
        finally:
            exit_code = self._finalize_run_status()
            self.cleanup()
        logger.debug('Fuzzer: finish fuzzing')
        if run_error is not None:
            raise run_error
        return exit_code
            
    def replay(
        self,
        res_dir: Path,
        cov_folder: Path
    ):
        """Fuzz the target one
        """
        res_dir = res_dir.expanduser().resolve()
        cov_folder = cov_folder.expanduser().resolve()
        configs.results_path = res_dir
        configure_file_logging(configs.results_path)
        
        with analyzer.lock:
            analyzer.strategy = 'replay'
            start_time = time.time()
            analyzer.start_time = start_time

        try:
            self._install_signal_handlers()
            worker_failure: list[tuple[BaseException, str]] = []

            def run_replay_worker() -> None:
                try:
                    self.replay_process(res_dir, cov_folder)
                except BaseException as error:
                    worker_failure.append((error, traceback.format_exc()))
                    self.stop_event.set()
            
            # start fuzzing and set up ui
            t_ui = threading.Thread(
                target=ui_loop,
                args=(self.stop_event,),
                name='voltron-ui',
                daemon=True,
            )
            t_fuzz = threading.Thread(
                target=run_replay_worker,
                name='voltron-replay',
                daemon=True,
            )
            self._worker_threads = [t_fuzz, t_ui]

            t_fuzz.start()
            t_ui.start()

            t_fuzz.join()
            t_ui.join()
            if worker_failure:
                error, worker_traceback = worker_failure[0]
                raise RuntimeError(
                    'voltron-replay worker failed:\n'
                    f'{worker_traceback}'
                ) from error
            
        except KeyboardInterrupt:
            logger.debug('Replay: interrupted')
        except Exception:
            logger.exception('Fuzzer: replay failed')
            self.stop_event.set()
            raise
        finally:
            self.cleanup()
        logger.debug('Fuzzer: finish replay')
                       
    def state_fuzz(
        self,
        stop_event: threading.Event
    ):
        try:
            with analyzer.lock:   
                analyzer.iter = 0
                analyzer.stage = (
                    'model learning'
                    if self.state_learning
                    else 'model learning disabled'
                )
                
            if not configs.models_path.is_dir():
                configs.models_path.mkdir()
            
            hypothesis: MealyMachine | None = None
            self.partial_guidance: PartialStateGraph | None = None
            begin_time = time.time()
            if self.state_learning:
                analyzer.begin_phase('model_learning')
                analyzer.record_generator_checkpoint(
                    phase='model_learning',
                    checkpoint_type='model_learning_baseline',
                    phase_iteration=0,
                    baseline_operation_id='initial_generator',
                )
                model_phase_status = 'completed'
                try:
                    model_learning_seed_retention = SeedRetentionPolicy()
                    trace_recorder = PartialTraceRecorder()
                    request_types = getattr(self.mapper, 'request_types', set())
                    threshold_tracker = (
                        ModelLearningThreshold(request_types)
                        if (
                            getattr(configs, 'partial_guidance_enabled', True)
                            and request_types
                        )
                        else None
                    )
                    mq = MembershipOracle(
                        mapper=self.mapper,
                        executor=self.exe,
                        seed_retention=model_learning_seed_retention,
                        trace_recorder=trace_recorder,
                        threshold_tracker=threshold_tracker,
                    )
                    eq = EquOracle(
                        mapper=self.mapper,
                        executor=self.exe,
                        seed_retention=model_learning_seed_retention,
                    )
                    h_path = configs.models_path / 'evolved_hypothesis.pkl'
                    if h_path.is_file():
                        with open(h_path, 'rb') as f:
                            hypothesis = pickle.load(f)

                    if hypothesis is None:
                        hypothesis = self.model_learning(mq, eq, stop_event)
                        if self.partial_guidance is not None:
                            model_phase_status = 'threshold_drained_partial'
                    else:
                        self.mapper.message_pool = hypothesis.map
                except BaseException:
                    model_phase_status = 'failed'
                    raise
                finally:
                    if stop_event.is_set() and model_phase_status == 'completed':
                        model_phase_status = analyzer.phase_stop_status()
                    analyzer.end_phase('model_learning', model_phase_status)
            else:
                analyzer.record_skipped_phase('model_learning')
            end_time = time.time()
            with analyzer.lock:   
                analyzer.model_learning_time_s = end_time - begin_time
            if stop_event.is_set():
                logger.debug('Fuzzer: model learning stopped at timeout')
                return
            self.berserker_fuzz(
                hypothesis,
                stop_event,
                partial_guidance=getattr(self, 'partial_guidance', None),
            )
                
        except Exception:
            logger.exception('Fuzzer: state fuzzing failed')
            self._request_stop('failure')
            raise
            
    def model_learning(
        self,
        mq,
        eq,
        stop_event
    ) -> MealyMachine | None:
        """--- model learning ---"""
        h_lsit: list[MealyMachine] = []
        best_generators = {}
        best_parser = None
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
                iteration_start = time.time()
                with analyzer.lock:
                    analyzer.stage = 'model learning'
                ml = MealyLstar(mq, eq, self.stop_event)
                h = ml.run(cur_id)
                iteration_duration = time.time() - iteration_start
                
                # save and evaluate the automata
                self.mapper.register_mapper(h)
                h.res_types = analyzer.cur_res_types_cnt
                h.res_trans_types = analyzer.cur_resp_trans_cnt

                # select a better generator to evolve
                # the more states transitions the better the generator
                iteration_status = 'initial'
                with analyzer.lock:
                    analyzer.stage = 'fuzzer evolve'
                if len(h_lsit) == 0:
                    h_lsit.append(h)
                    best_generators, best_parser = (
                        self.producer.capture_current_equipment(
                            self.mapper.cur_parser
                        )
                    )
                    analyzer.record_model_learning_iteration(
                        iteration=int(cur_id),
                        hypothesis=h,
                        duration_s=iteration_duration,
                        status=iteration_status,
                        try_limit=try_limit,
                    )
                    if self.spec_knowledge:
                        analyzer.record_generator_checkpoint(
                            phase='model_learning',
                            checkpoint_type='before_generator_evolve',
                            phase_iteration=int(cur_id),
                            operation_id=f'evolve-{cur_id}',
                            model_id=str(h.id),
                            iteration_status=iteration_status,
                        )
                        self.producer.generator_evo(h)
                    continue
                last_trans_num = len(h_lsit[-1].res_trans_types.keys())
                cur_trans_num = len(h.res_trans_types.keys())
                
                if last_trans_num >= cur_trans_num:
                    # self.producer.generator_evo(h_lsit[-1], next_id)
                    try_limit -= 1
                    if try_limit <= 0:
                        iteration_status = 'accepted_final'
                        best_hypothesis = h_lsit[-1]
                        with open(h_path, 'wb') as f:
                            pickle.dump(best_hypothesis, f)
                        if best_parser is None:
                            raise RuntimeError(
                                'No parser was captured for the best model'
                            )
                        self.producer.save_best_equipment(
                            model_id=str(best_hypothesis.id),
                            generators=best_generators,
                            parser=best_parser,
                        )
                        best_hypothesis.graph('evolved')
                        logger.debug('ml: save evolved model')
                        analyzer.record_model_learning_iteration(
                            iteration=int(cur_id),
                            hypothesis=best_hypothesis,
                            duration_s=iteration_duration,
                            status=iteration_status,
                            try_limit=try_limit,
                        )
                        break
                    iteration_status = 'not_improved'
                    analyzer.record_model_learning_iteration(
                        iteration=int(cur_id),
                        hypothesis=h,
                        duration_s=iteration_duration,
                        status=iteration_status,
                        try_limit=try_limit,
                    )
                
                elif last_trans_num < cur_trans_num:
                    iteration_status = 'improved'
                    h_lsit.append(h)
                    best_generators, best_parser = (
                        self.producer.capture_current_equipment(
                            self.mapper.cur_parser
                        )
                    )
                    analyzer.record_model_learning_iteration(
                        iteration=int(cur_id),
                        hypothesis=h,
                        duration_s=iteration_duration,
                        status=iteration_status,
                        try_limit=try_limit,
                    )
                    if self.spec_knowledge:
                        analyzer.record_generator_checkpoint(
                            phase='model_learning',
                            checkpoint_type='before_generator_evolve',
                            phase_iteration=int(cur_id),
                            operation_id=f'evolve-{cur_id}',
                            model_id=str(h.id),
                            iteration_status=iteration_status,
                        )
                        self.producer.generator_evo(h)
                    continue

            except ModelLearningThresholdReached as reached:
                self.partial_guidance = self._save_partial_guidance(
                    mq,
                    reached.table,
                    reason='threshold_drained_partial',
                )
                logger.debug(
                    'Fuzzer: model learning threshold reached; '
                    'using %d partial traces for fuzz guidance',
                    len(self.partial_guidance.traces),
                )
                break
            except LLMDeadlineExceeded:
                logger.debug('Fuzzer: model learning stopped')
                self._request_stop('deadline')
                break
            except ModelLearningStopped:
                logger.debug('Fuzzer: model learning stopped')
                if getattr(analyzer, 'stop_reason', None) is None:
                    self._request_stop('model_learning_failure')
                break
            except Exception as error:
                logger.exception('Fuzzer: model learning failed')
                self._request_stop('model_learning_failure')
                raise RuntimeError('model learning failed') from error
            if (configs.time_limit_s < time.time() - analyzer.start_time):
                logger.debug('Fuzzer: timeout')
                self._request_stop('deadline')
                
        return h_lsit[-1] if h_lsit else None

    def _partial_guidance_fingerprint(self) -> dict[str, object]:
        """Bind partial traces to the components that produced their bytes."""
        parser = getattr(self.mapper, 'cur_parser', None)
        generators = getattr(self.mapper, 'generators', {})
        return {
            'target': getattr(
                self,
                'target_name',
                getattr(configs, 'target_name', ''),
            ),
            'protocol': getattr(configs, 'pro_name', ''),
            'endpoint': f'{getattr(configs, "host", "")}:{getattr(configs, "port", "")}',
            'parser': getattr(parser, 'name', str(parser) if parser else ''),
            'generators': {
                str(symbol): getattr(generator, 'name', str(generator))
                for symbol, generator in sorted(generators.items())
            },
        }

    def _save_partial_guidance(
        self,
        mq,
        table: ObTable,
        reason: str,
    ) -> PartialStateGraph:
        recorder = getattr(mq, 'trace_recorder', None)
        if recorder is None:
            raise RuntimeError('partial guidance requires an MQ trace recorder')
        table_snapshot = (
            copy.deepcopy(table.S),
            copy.deepcopy(table.E),
            copy.deepcopy(table.T),
        )
        graph = recorder.snapshot(
            self._partial_guidance_fingerprint(),
            table_snapshot,
            reason,
        )
        for folder in (configs.models_path, configs.results_path):
            folder.mkdir(parents=True, exist_ok=True)
            with (folder / 'partial_guidance.pkl').open('wb') as stream:
                pickle.dump(graph, stream)
        return graph
    
    def berserker_fuzz(
        self,
        hypothesis: MealyMachine | None,
        stop_event,
        partial_guidance: PartialStateGraph | None = None,
    ):
        """--- berserker fuzzing ---"""
        with analyzer.lock:   
            analyzer.iter = 0
            analyzer.stage = 'berserker fuzzing'
            analyzer.res_types_cnt = {}
            analyzer.resp_trans_cnt = {}

        analyzer.record_generator_checkpoint(
            phase='fuzzing',
            checkpoint_type='fuzzing_baseline',
            phase_iteration=0,
            baseline_operation_id='initial_mutator',
        )
        
        berserker = Berserker(
            self.mapper,
            self.exe,
            hypothesis,
            use_guidance=self.guided_scheduling,
            partial_guidance=(
                partial_guidance if self.guided_scheduling else None
            ),
        )

        analyzer.begin_phase('fuzzing')
        fuzz_phase_status = 'completed'
        try:
            while not stop_event.is_set():
                try:
                    # init new learning process with previous model and run fuzzer

                    req_res = berserker.run(500)
                    if self.spec_knowledge:
                        self.producer.generator_mutate(
                            req_res,
                            iteration=analyzer.iter,
                        )
                    pre_resp = analyzer.cur_res_types_cnt.keys()

                    # save the results
                    with analyzer.lock:
                        analyzer.iter += 1
                        analyzer.reset_automata_cnt()
                    analyzer.collect_results()

                except Exception:
                    fuzz_phase_status = 'failed'
                    logger.exception('Fuzzer: berserker fuzzing failed')
                    self._request_stop('failure')
                    raise

                if (configs.time_limit_s < time.time() - analyzer.start_time):
                    logger.debug('Fuzzer: timeout')
                    self._request_stop('deadline')
                    analyzer.collect_results()
        finally:
            analyzer.finalize_generator_metrics(
                phase_iteration=analyzer.iter,
            )
            if stop_event.is_set() and fuzz_phase_status == 'completed':
                fuzz_phase_status = analyzer.phase_stop_status()
            analyzer.end_phase('fuzzing', fuzz_phase_status)
                
    def replay_process(
        self,
        res_dir: Path,
        cov_folder: Path,
    ):
        configs.cov_setup_path =  configs.base_path / 'config' / 'subjects' / configs.target_name / 'cov_setup.sh'
        configs.cov_collect_path =  configs.base_path / 'config' / 'subjects' / configs.target_name / 'cov_collect.sh'
        
        in_dir = res_dir / 'replayable_testcases'
        cov_file = res_dir / 'cov_over_time.csv'
        with analyzer.lock:   
            analyzer.stage = 'replay'
            
        file_count = 0
        try:
            file_paths = [
                path
                for path in in_dir.iterdir()
                if path.is_file() and path.suffix == '.pkl'
            ]
            sorted_files = sorted(
                file_paths,
                key=self.get_creation_timestamp,
                reverse=False
            )
            cons_seq: list[Conversation] = []
            file_list: list[Path] = []
            for item in sorted_files:
                try:
                    with open(item, 'rb') as f:
                        cons = pickle.load(f)
                    if not isinstance(cons, Conversation):
                        raise TypeError(
                            f'expected Conversation, got {type(cons).__name__}'
                        )
                    cons_seq.append(cons)
                    file_list.append(item)
                    file_count += 1
                except Exception:
                    logger.exception(
                        f'Fuzzer: skip invalid replay testcase {item}'
                    )

            if file_count == 0:
                status_path = res_dir / 'coverage_replay_status.json'
                status_path.write_text(
                    json.dumps({
                        'status': 'NO_COVERAGE_INPUT',
                        'valid_testcase_count': 0,
                        'input_directory': str(in_dir),
                    }, indent=2),
                    encoding='utf-8',
                )
                raise NoCoverageInputError(
                    f'no valid replay testcase found under {in_dir}'
                )
            
            analyzer.set_progress('berserker', 'replay', file_count)
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
                except Exception:
                    logger.exception('Fuzzer: testcase replay failed')
                    continue

                with analyzer.lock:
                    analyzer.finished += 1

                if flag:
                    self.exe.cov_collect(cov_folder, cov_file, file_list[i])
        except NoCoverageInputError:
            logger.error('Fuzzer: coverage replay has no valid input')
            raise
        except Exception:
            logger.exception('Fuzzer: replay processing failed')
        finally:
            self.stop_event.set()

    def handle_normal_fuzzer_exit(
        self,
        signal_num, 
        frame
    ):
        # Handle normal exit of fuzzer Ctrl+C
        logger.debug(f'Fuzzer: caught signal {signal_num}, stopping')
        self._request_stop('external_interrupt')
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        self._terminate_active_sut(signal.SIGTERM, timeout=0.5)
        raise KeyboardInterrupt

    def _install_signal_handlers(
        self
    ) -> None:
        if self._signal_handler_installed:
            return
        self._previous_sigint_handler = signal.getsignal(signal.SIGINT)
        signal.signal(signal.SIGINT, self.handle_normal_fuzzer_exit)
        self._signal_handler_installed = True

    def _restore_signal_handlers(
        self
    ) -> None:
        if self._previous_sigint_handler is not None:
            try:
                signal.signal(signal.SIGINT, self._previous_sigint_handler)
            except Exception:
                logger.exception('Fuzzer: restore signal handler failure')
            self._previous_sigint_handler = None
        self._signal_handler_installed = False

    def cleanup(
        self
    ) -> None:
        """Run process-exit cleanup once for normal, interrupted, and atexit paths."""
        with self._cleanup_lock:
            if self._cleanup_done:
                return
            self._cleanup_done = True

            try:
                self.stop_event.set()
            except Exception:
                pass

            self._terminate_active_sut(signal.SIGTERM, timeout=3)
            self._join_worker_threads(timeout=1)

            try:
                mapper = getattr(self, 'mapper', None)
                if mapper is not None:
                    mapper.close()
            except Exception:
                logger.exception('Fuzzer: mapper close failure')

            if self.mode != 'replay':
                self._collect_results()

            self._restore_signal_handlers()

    def _join_worker_threads(self, timeout: float) -> None:
        """Wait briefly for cooperative workers before collecting results."""
        deadline = time.monotonic() + timeout
        current = threading.current_thread()
        for thread in self._worker_threads:
            if thread is current or not thread.is_alive():
                continue
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            thread.join(timeout=remaining)

        alive = [
            thread.name
            for thread in self._worker_threads
            if thread is not current and thread.is_alive()
        ]
        if alive:
            logger.debug(
                f'Fuzzer: worker shutdown timeout; alive={alive}'
            )

    def _terminate_active_sut(
        self,
        sig: signal.Signals,
        timeout: float
    ) -> None:
        proc = analyzer.sut_proc
        if proc is None:
            return

        try:
            if proc.poll() is None:
                os.killpg(proc.pid, sig)
                proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait(timeout=1)
            except Exception:
                logger.exception('Fuzzer: SUT kill failure')
        except ProcessLookupError:
            pass
        except Exception:
            logger.exception('Fuzzer: SUT terminate failure')
        finally:
            if analyzer.sut_proc is proc:
                analyzer.sut_proc = None

    def _collect_results(
        self
    ) -> None:
        if not hasattr(analyzer, 'start_time') or not hasattr(configs, 'results_path'):
            return
        try:
            analyzer.finalize_open_phase()
            analyzer.finalize_generator_metrics(
                phase_iteration=analyzer.iter,
            )
            analyzer.collect_results()
        except Exception:
            logger.exception('Fuzzer: collect results failure')
        
    def get_creation_timestamp(
        self, 
        file: Path
    ) -> float:
        try:
            return file.stat().st_birthtime
        except AttributeError:
            return file.stat().st_ctime
