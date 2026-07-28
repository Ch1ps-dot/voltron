import csv
from datetime import datetime
import threading, time, pprint
from pathlib import Path
from voltron.utils.logger import logger_fuzz as logger
from voltron.configs import configs
import threading, subprocess

class Analyzer:
    def __init__(
            self
    ) -> None:
        
        # counters for metric
        self.req_types_cnt: dict[str, int] = {}
        self.res_types_cnt: dict[str, int] = {}
        self.cur_res_types_cnt: dict[str, int] = {}
        self.resp_trans_cnt: dict[str, int] = {}
        self.cur_resp_trans_cnt: dict[str, int] = {}
        self.req_num = 0
        self.res_num = 0
        self.path_num = 0
        self.timeout_num = 0
        self.pollerr_num = 0
        self.crash_num = 0
        self.crash_num = 0
        self.rclose_num = 0
        self.non_compliant_num = 0

        # information of fuzzer
        self.target_name: str
        self.pro_name: str
        self.start_time: float
        self.strategy = ''
        self.stage = ''
        self.current_operation = ''
        
        # communication info
        self.sent = ''
        self.recv = ''
        self.last_sent = '-'
        self.last_recv = '-'
        self.useful_cons: int = 0

        self.autamata = None
        self.state = 0
        self.lock: threading.RLock = threading.RLock()

        # UI progress
        self.show_progress: str = ''
        self.progress_desc = ''
        self.total: int = 0
        self.finished: int = 0
        self.progress_bar: dict[str, str] = {}
        
        self.model_learning_time_s:float = 0
        self.chat_time_s:float = 0
        self.chat_token = 0

        # Per-stage wall-clock and LLM token metrics.
        self.phase_metrics: dict[str, dict] = {}
        self.active_phase: str | None = None
        self.phase_metrics_path: Path | None = None
        self.model_learning_iteration_path: Path | None = None
        
        self.iter = 0 # fuzzer generation iteration
        
        self.stop_event: threading.Event
        
        self.sut_proc: subprocess.Popen | None = None
        self._metric_series_path: Path | None = None
        self._metric_series_last_minute: int | None = None

    def reset_phase_metrics(
            self
    ) -> None:
        with self.lock:
            self.phase_metrics = {}
            self.active_phase = None
            self.phase_metrics_path = None
            self.model_learning_iteration_path = None
            try:
                csv_path = configs.results_path / 'phase_metrics.csv'
                csv_path.unlink(missing_ok=True)
                iteration_csv_path = (
                    configs.results_path
                    / 'model_learning_iterations.csv'
                )
                iteration_csv_path.unlink(missing_ok=True)
            except Exception:
                logger.exception('Analyzer: reset phase metrics failure')

    def _new_phase_metric(
            self,
            phase: str
    ) -> dict:
        return {
            'phase': phase,
            'status': 'running',
            'start_time': time.time(),
            'end_time': None,
            'duration_s': 0.0,
            'chat_time_s': 0.0,
            'llm_calls': 0,
            'prompt_tokens': 0,
            'completion_tokens': 0,
            'total_tokens': 0,
            'written': False,
        }

    def begin_phase(
            self,
            phase: str
    ) -> None:
        with self.lock:
            if self.active_phase == phase:
                return
            if self.active_phase is not None:
                self._end_phase_unlocked(self.active_phase, 'interrupted')

            metric = self._new_phase_metric(phase)
            self.phase_metrics[phase] = metric
            self.active_phase = phase
            logger.debug(f'Analyzer: begin phase {phase}')

    def end_phase(
            self,
            phase: str,
            status: str = 'completed'
    ) -> None:
        with self.lock:
            self._end_phase_unlocked(phase, status)

    def record_skipped_phase(
            self,
            phase: str
    ) -> None:
        with self.lock:
            metric = self._new_phase_metric(phase)
            metric['status'] = 'skipped'
            metric['end_time'] = metric['start_time']
            metric['duration_s'] = 0.0
            self.phase_metrics[phase] = metric
            self._write_phase_metric_unlocked(metric)

    def finalize_open_phase(
            self,
            status: str = 'interrupted'
    ) -> None:
        with self.lock:
            if self.active_phase is not None:
                self._end_phase_unlocked(self.active_phase, status)

    def record_llm_usage(
            self,
            duration_s: float,
            prompt_tokens: int = 0,
            completion_tokens: int = 0,
            total_tokens: int = 0
    ) -> None:
        with self.lock:
            phase = self.active_phase or self._phase_from_stage()
            if phase is None:
                return
            metric = self.phase_metrics.get(phase)
            if metric is None or metric.get('written'):
                metric = self._new_phase_metric(phase)
                self.phase_metrics[phase] = metric
            metric['chat_time_s'] += duration_s
            metric['llm_calls'] += 1
            metric['prompt_tokens'] += prompt_tokens
            metric['completion_tokens'] += completion_tokens
            metric['total_tokens'] += total_tokens

    def _phase_from_stage(
            self
    ) -> str | None:
        stage = self.stage.lower()
        if 'model learning' in stage or 'fuzzer evolve' in stage:
            return 'model_learning'
        if 'berserker' in stage or 'fuzz' in stage:
            return 'fuzzing'
        return None

    def _end_phase_unlocked(
            self,
            phase: str,
            status: str
    ) -> None:
        metric = self.phase_metrics.get(phase)
        if metric is None or metric.get('written'):
            if self.active_phase == phase:
                self.active_phase = None
            return

        end_time = time.time()
        metric['status'] = status
        metric['end_time'] = end_time
        metric['duration_s'] = max(0.0, end_time - metric['start_time'])
        self._write_phase_metric_unlocked(metric)
        if self.active_phase == phase:
            self.active_phase = None
        logger.debug(f'Analyzer: end phase {phase} status={status}')

    def _write_phase_metric_unlocked(
            self,
            metric: dict
    ) -> None:
        try:
            csv_path = configs.results_path / 'phase_metrics.csv'
            if self.phase_metrics_path != csv_path:
                self.phase_metrics_path = csv_path

            write_header = (
                not csv_path.is_file()
                or csv_path.stat().st_size == 0
            )
            with csv_path.open(mode='a', encoding='utf-8', newline='') as f:
                fieldnames = [
                    'phase',
                    'status',
                    'start_time',
                    'end_time',
                    'duration_s',
                    'chat_time_s',
                    'llm_calls',
                    'prompt_tokens',
                    'completion_tokens',
                    'total_tokens',
                ]
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                if write_header:
                    writer.writeheader()
                writer.writerow({
                    'phase': metric['phase'],
                    'status': metric['status'],
                    'start_time': self._format_time(metric['start_time']),
                    'end_time': self._format_time(metric['end_time']),
                    'duration_s': f"{metric['duration_s']:.6f}",
                    'chat_time_s': f"{metric['chat_time_s']:.6f}",
                    'llm_calls': metric['llm_calls'],
                    'prompt_tokens': metric['prompt_tokens'],
                    'completion_tokens': metric['completion_tokens'],
                    'total_tokens': metric['total_tokens'],
                })
            metric['written'] = True
        except Exception:
            logger.exception('Analyzer: write phase metrics failure')

    def _format_time(
            self,
            timestamp: float | None
    ) -> str:
        if timestamp is None:
            return ''
        return datetime.fromtimestamp(timestamp).isoformat(timespec='seconds')

    def record_model_learning_iteration(
            self,
            iteration: int,
            hypothesis,
            duration_s: float,
            status: str,
            try_limit: int,
    ) -> None:
        try:
            table_s, table_e, table_t = getattr(
                hypothesis,
                'table',
                ([], [], {}),
            )
            state_count = len(getattr(hypothesis, 'states', []))
            alphabet_count = len(getattr(hypothesis, 'alphabet', []))
            transition_count = len(getattr(hypothesis, 'delta', {}))
            output_count = len(getattr(hypothesis, 'output', {}))
            table_s_count = len(table_s)
            table_e_count = len(table_e)
            table_t_count = len(table_t)

            csv_path = configs.results_path / 'model_learning_iterations.csv'
            write_header = (
                not csv_path.is_file()
                or csv_path.stat().st_size == 0
            )
            self.model_learning_iteration_path = csv_path
            with csv_path.open(mode='a', encoding='utf-8', newline='') as f:
                fieldnames = [
                    'iteration',
                    'status',
                    'duration_s',
                    'try_limit',
                    'automata_states',
                    'automata_transitions',
                    'automata_outputs',
                    'alphabet_symbols',
                    'observation_table_s',
                    'observation_table_e',
                    'observation_table_t',
                    'current_response_types',
                    'current_response_type_events',
                    'current_response_transitions',
                    'current_response_transition_events',
                    'total_response_types',
                    'total_response_transitions',
                ]
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                if write_header:
                    writer.writeheader()
                writer.writerow({
                    'iteration': iteration,
                    'status': status,
                    'duration_s': f'{duration_s:.6f}',
                    'try_limit': try_limit,
                    'automata_states': state_count,
                    'automata_transitions': transition_count,
                    'automata_outputs': output_count,
                    'alphabet_symbols': alphabet_count,
                    'observation_table_s': table_s_count,
                    'observation_table_e': table_e_count,
                    'observation_table_t': table_t_count,
                    'current_response_types': len(self.cur_res_types_cnt),
                    'current_response_type_events': sum(
                        self.cur_res_types_cnt.values()
                    ),
                    'current_response_transitions': len(
                        self.cur_resp_trans_cnt
                    ),
                    'current_response_transition_events': sum(
                        self.cur_resp_trans_cnt.values()
                    ),
                    'total_response_types': len(self.res_types_cnt),
                    'total_response_transitions': len(self.resp_trans_cnt),
                })
        except Exception:
            logger.exception(
                'Analyzer: write model learning iteration metrics failure'
            )

    def collect_results(
            self
    ):  
        status_file = configs.results_path / f'fuzzer_status'
        try:
            with status_file.open(mode='w', encoding='utf-8') as f:
                f.write(f'{"start_time":<15}: {self.start_time}\n')
                f.write(f'{"running_time":<15}: {self.seconds_to_hms(time.time() - self.start_time)}\n')
                f.write(f'{"target_name":<15}: {self.target_name}\n')
                f.write(f'{"protocol_name":<15}: {self.pro_name}\n')
                f.write(f'{"exec_path_num":<15}: {self.path_num}\n')
                f.write(f'{"sent_request":<15}: {self.req_num}\n')
                f.write(f'{"recv_resp":<15}: {self.res_num}\n')
                f.write(f'{"distinct_resp":<15}: {self.res_types_num()}\n')
                f.write(f'{"resp_transitions":<15}: {self.resp_trans_num()}\n')
                f.write(f'{"crash_num":<15}: {self.crash_num}\n')
                f.write(
                    f'{"non_compliant":<15}: '
                    f'{self.non_compliant_num}\n'
                )
                f.write(f'{"model_learn_time_s":<15}: {self.seconds_to_hms(self.model_learning_time_s)}\n')
                f.write(f'{"chat_time_s":<15}: {self.seconds_to_hms(self.chat_time_s)}\n')
                f.write(f'{"chat_token":<15}: {self.chat_token}\n')
        except Exception:
            logger.exception('Analyzer: collect status results failure')

        self.collect_metric_series()
            
        states_file = configs.results_path / f'states_info'
        try:
            with states_file.open(mode='w', encoding='utf-8') as f:
                f.write(f'{"response types":<15}:\n')
                pprint.pprint(
                    self.res_types_cnt.keys(),
                    stream=f
                )
                f.write(f'{"response transitions":<15}:\n')
                pprint.pprint(
                    self.resp_trans_cnt.keys(),
                    stream=f
                )
        except Exception:
            logger.exception('Analyzer: collect state results failure')

    def collect_metric_series(
            self
    ):
        series_file = configs.results_path / 'states.csv'
        try:
            if self._metric_series_path != series_file:
                self._metric_series_path = series_file
                self._metric_series_last_minute = None

            elapsed_minute = int((time.time() - self.start_time) // 60)
            start_minute = 0
            if self._metric_series_last_minute is not None:
                start_minute = self._metric_series_last_minute + 1

            if start_minute > elapsed_minute:
                return

            write_header = not series_file.is_file() or series_file.stat().st_size == 0
            with series_file.open(mode='a', encoding='utf-8', newline='') as f:
                writer = csv.DictWriter(
                    f,
                    fieldnames=['subject', 'fuzzer', 'data_type', 'time', 'data']
                )
                if write_header:
                    writer.writeheader()

                for minute in range(start_minute, elapsed_minute + 1):
                    writer.writerow({
                        'subject': self.target_name,
                        'fuzzer': 'voltron',
                        'data_type': 'nodes',
                        'time': minute,
                        'data': self.res_types_num()
                    })
                    writer.writerow({
                        'subject': self.target_name,
                        'fuzzer': 'voltron',
                        'data_type': 'edges',
                        'time': minute,
                        'data': self.resp_trans_num()
                    })

            self._metric_series_last_minute = elapsed_minute
        except Exception:
            logger.exception('Analyzer: collect metric series failure')

    def req_types_update(
            self,
            req_code: str
    ):
        if req_code in self.req_types_cnt.keys():
            self.req_types_cnt[req_code] += 1
        else:
            self.req_types_cnt[req_code] = 1

    def res_types_update(
            self,
            res_code: str
    ):
        if res_code in self.res_types_cnt.keys():
            self.res_types_cnt[res_code] +=  1
        else:
            self.res_types_cnt[res_code] = 1
            logger.debug(f'Analyzer: new reply {res_code}')
            
        if res_code in self.cur_res_types_cnt.keys():
            self.cur_res_types_cnt[res_code] +=  1
        else:
            self.cur_res_types_cnt[res_code] = 1

    def resp_trans_update(
            self,
            trans: str
    ):
        if trans in self.resp_trans_cnt.keys():
            self.resp_trans_cnt[trans] += 1
        else:
            self.resp_trans_cnt[trans] = 1
            logger.debug(f'Analyzer: new transition {trans}')
            
        if trans in self.cur_resp_trans_cnt.keys():
            self.cur_resp_trans_cnt[trans] +=  1
        else:
            self.cur_resp_trans_cnt[trans] = 1

    
    def req_types_num(
            self
    ):
        return len(self.req_types_cnt.keys())
    
    def res_types_num(
            self
    ):
        return len(self.res_types_cnt.keys())
    
    def resp_trans_num(
            self
    ):
        return len(self.resp_trans_cnt.keys())
    
    def unseen_res_types(
        self
    ) -> list:
        return [res_type for res_type in self.req_types_cnt if self.req_types_cnt[res_type] == 0]
    
    def seconds_to_hms(
            self, 
            seconds: float
        ) -> str:
        total_seconds = int(seconds)
        remaining_seconds = seconds - total_seconds
        
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        secs = total_seconds % 60
        
        if remaining_seconds > 0:
            return f"{hours:02d}:{minutes:02d}:{secs + remaining_seconds:.1f}"
        else:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        
    def clean_progress(self):
        self.finished = 0
        self.total = 0
        self.show_progress =''
        self.sent = ''
        self.recv = ''
        
    def reset_automata_cnt(self):
        self.state = 0
        self.cur_res_types_cnt = {}
        self.cur_resp_trans_cnt = {}
        
    def set_progress(
        self,
        progress: str,
        desc: str,
        total: int
    ):
        self.show_progress = progress
        self.progress_desc = desc
        self.total = total
        self.finished = 0
        
    def add_progress_bar(
        self,
        desc: str,
        total: int
    ):
        self.progress_bar[desc] = f'0/{total}'
        
    def update_progress_bar(
        self,
        desc: str,
        inc: int
    ):
        finished, total = self.progress_bar[desc].split('/')
        finished = str(int(finished) + inc)
        self.progress_bar[desc] = f'{finished}/{total}'
        
    def delete_progress_bar(
        self,
        desc: str
    ):
        self.progress_bar.pop(desc)
        
analyzer = Analyzer()
    
