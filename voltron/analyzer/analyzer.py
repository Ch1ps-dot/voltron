import csv
from datetime import datetime
import json
import os
import threading, time, pprint
from pathlib import Path
from voltron.utils.logger import logger_fuzz as logger
from voltron.utils.result_layout import diagnostics_path
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
        # Whole-process counters. Unlike the phase counters above, these are
        # never reset when model learning or fuzzing starts a new iteration.
        self.lifetime_res_types_cnt: dict[str, int] = {}
        self.lifetime_resp_trans_cnt: dict[str, int] = {}
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
        self.llm_usage_metrics: dict[tuple[str, str], dict] = {}
        self.llm_usage_metrics_path: Path | None = None
        self.llm_response_validation_path: Path | None = None
        self.model_learning_iteration_path: Path | None = None
        self.generator_iteration_metrics_path: Path | None = None
        self.iteration_state_metrics_path: Path | None = None
        self._recorded_iteration_state_metrics: set[tuple[str, int]] = set()
        self._generator_checkpoint_id = 0
        self._last_generator_checkpoint: dict | None = None
        self._last_generator_operation_id: str | None = None
        self._generator_metrics_finalized = False
        
        self.iter = 0 # fuzzer generation iteration
        
        self.stop_event: threading.Event
        # A stop event alone cannot distinguish a deadline, cancellation, or
        # an internal failure.  Keep that reason alongside the event.
        self.stop_reason: str | None = None
        self.run_status: str = 'not_started'
        self.planned_duration_s: float | None = None
        self.actual_duration_s: float | None = None
        # ``fuzzer_status`` is read by external monitors while the fuzzer is
        # running.  Serialize snapshot writers so an older heartbeat can
        # never replace a newer final status.
        self._status_snapshot_lock = threading.RLock()
        self.status_snapshot_sequence = 0
        self.status_last_update_timestamp: float | None = None
        self.offline_mutation_attempts = 0
        self.offline_mutation_applied = 0
        self.offline_mutation_bytes_added = 0
        self.offline_mutation_bytes_removed = 0
        self.offline_mutation_operators = {}
        
        self.sut_proc: subprocess.Popen | None = None
        self._state_snapshot_path: Path | None = None
        # Context is set by the fuzzer and Executor immediately before a
        # response can change the state graph.  It is copied into every row
        # of one discovery snapshot, never reconstructed from newer
        # components at CSV-write time.
        self._state_snapshot_phase = ''
        self._state_snapshot_phase_iteration: int | None = None
        self._state_snapshot_components: tuple[dict[str, str], ...] = ()
        self._state_snapshot_request_type = ''
        self._state_snapshot_parser_version = ''

    def reset_phase_metrics(
            self
    ) -> None:
        with self.lock:
            self.phase_metrics = {}
            self.active_phase = None
            self.phase_metrics_path = None
            self.llm_usage_metrics = {}
            self.llm_usage_metrics_path = None
            self.llm_response_validation_path = None
            self.model_learning_iteration_path = None
            self.generator_iteration_metrics_path = None
            self.iteration_state_metrics_path = None
            self._recorded_iteration_state_metrics = set()
            self._generator_checkpoint_id = 0
            self._last_generator_checkpoint = None
            self._last_generator_operation_id = None
            self._generator_metrics_finalized = False
            self._state_snapshot_path = None
            self._state_snapshot_phase = ''
            self._state_snapshot_phase_iteration = None
            self._state_snapshot_components = ()
            self._state_snapshot_request_type = ''
            self._state_snapshot_parser_version = ''
            self.lifetime_res_types_cnt = {}
            self.lifetime_resp_trans_cnt = {}
            self.stop_reason = None
            self.run_status = 'not_started'
            self.planned_duration_s = None
            self.actual_duration_s = None
            self.status_snapshot_sequence = 0
            self.status_last_update_timestamp = None
            self.offline_mutation_attempts = 0
            self.offline_mutation_applied = 0
            self.offline_mutation_bytes_added = 0
            self.offline_mutation_bytes_removed = 0
            self.offline_mutation_operators = {}
            try:
                csv_path = configs.results_path / 'phase_metrics.csv'
                csv_path.unlink(missing_ok=True)
                usage_csv_path = (
                    configs.results_path
                    / 'llm_usage_metrics.csv'
                )
                usage_csv_path.unlink(missing_ok=True)
                validation_path = diagnostics_path(
                    configs.results_path,
                    'events',
                    'llm_response_validation.jsonl',
                )
                validation_path.unlink(missing_ok=True)
                iteration_csv_path = (
                    configs.results_path
                    / 'model_learning_iterations.csv'
                )
                iteration_csv_path.unlink(missing_ok=True)
                generator_csv_path = (
                    configs.results_path
                    / 'generator_iteration_metrics.csv'
                )
                generator_csv_path.unlink(missing_ok=True)
                iteration_state_csv_path = (
                    configs.results_path
                    / 'iteration_state_metrics.csv'
                )
                iteration_state_csv_path.unlink(missing_ok=True)
            except Exception:
                logger.exception('Analyzer: reset phase metrics failure')

    def request_stop(
            self,
            reason: str,
            event: threading.Event | None = None,
    ) -> None:
        """Set the stop reason once, then signal the shared stop event."""
        with self.lock:
            if self.stop_reason is None:
                self.stop_reason = reason
            stop_event = event or getattr(self, 'stop_event', None)
        if stop_event is not None:
            stop_event.set()

    def phase_stop_status(
            self,
            default: str = 'stopped',
    ) -> str:
        """Map a run stop reason to an unambiguous phase status."""
        reason = self.stop_reason
        if reason == 'deadline':
            return 'deadline_reached'
        if reason in {'external_interrupt', 'cancelled'}:
            return 'interrupted'
        if reason in {
            'failure',
            'model_learning_failure',
            'sut_failure',
            'coverage_failure',
        }:
            return 'failed'
        return default

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
            total_tokens: int = 0,
            usage: str = '',
            model: str = '',
            tokens_reported: bool = True,
            response_valid: bool | None = None,
            validation_reason: str = '',
            response_contract: str = '',
            response_chars: int = 0,
            response_sha256: str = '',
    ) -> None:
        with self.lock:
            phase = self.active_phase or self._phase_from_stage()
            if phase is not None:
                metric = self.phase_metrics.get(phase)
                if metric is None or metric.get('written'):
                    metric = self._new_phase_metric(phase)
                    self.phase_metrics[phase] = metric
                metric['chat_time_s'] += duration_s
                metric['llm_calls'] += 1
                metric['prompt_tokens'] += prompt_tokens
                metric['completion_tokens'] += completion_tokens
                metric['total_tokens'] += total_tokens

            usage_name = str(usage).strip()
            if not usage_name:
                return
            model_name = str(model).strip()
            key = (usage_name, model_name)
            usage_metric = self.llm_usage_metrics.get(key)
            if usage_metric is None:
                usage_metric = {
                    'usage': usage_name,
                    'model': model_name,
                    'llm_calls': 0,
                    'token_reported_calls': 0,
                    'chat_time_s': 0.0,
                    'prompt_tokens': 0,
                    'completion_tokens': 0,
                    'total_tokens': 0,
                    'max_prompt_tokens': 0,
                    'max_completion_tokens': 0,
                    'max_total_tokens': 0,
                    'valid_responses': 0,
                    'invalid_responses': 0,
                    'empty_responses': 0,
                    'schema_failures': 0,
                    'truncated_responses': 0,
                    'discarded_completion_tokens': 0,
                }
                self.llm_usage_metrics[key] = usage_metric
            usage_metric['llm_calls'] += 1
            if tokens_reported:
                usage_metric['token_reported_calls'] += 1
            usage_metric['chat_time_s'] += duration_s
            usage_metric['prompt_tokens'] += prompt_tokens
            usage_metric['completion_tokens'] += completion_tokens
            usage_metric['total_tokens'] += total_tokens
            usage_metric['max_prompt_tokens'] = max(
                usage_metric['max_prompt_tokens'],
                prompt_tokens,
            )
            usage_metric['max_completion_tokens'] = max(
                usage_metric['max_completion_tokens'],
                completion_tokens,
            )
            usage_metric['max_total_tokens'] = max(
                usage_metric['max_total_tokens'],
                total_tokens,
            )
            if response_valid is True:
                usage_metric['valid_responses'] += 1
            elif response_valid is False:
                usage_metric['invalid_responses'] += 1
                usage_metric['discarded_completion_tokens'] += (
                    completion_tokens
                )
                if validation_reason == 'empty_response':
                    usage_metric['empty_responses'] += 1
                elif validation_reason == 'truncated_response':
                    usage_metric['truncated_responses'] += 1
                else:
                    usage_metric['schema_failures'] += 1
            self._write_llm_usage_metrics_unlocked()
            if response_valid is not None:
                self._write_llm_response_validation_unlocked({
                    'timestamp': datetime.now().astimezone().isoformat(),
                    'usage': usage_name,
                    'model': model_name,
                    'contract': str(response_contract),
                    'status': 'valid' if response_valid else 'invalid',
                    'reason': str(validation_reason),
                    'response_chars': max(0, int(response_chars)),
                    'response_sha256': str(response_sha256),
                    'completion_tokens': max(0, int(completion_tokens)),
                })

    def _write_llm_usage_metrics_unlocked(self) -> None:
        """Persist current per-usage aggregates atomically."""
        try:
            csv_path = configs.results_path / 'llm_usage_metrics.csv'
            self.llm_usage_metrics_path = csv_path
            temporary = csv_path.with_suffix('.csv.tmp')
            fieldnames = [
                'usage',
                'model',
                'llm_calls',
                'token_reported_calls',
                'chat_time_s',
                'prompt_tokens',
                'completion_tokens',
                'total_tokens',
                'avg_prompt_tokens',
                'avg_completion_tokens',
                'avg_total_tokens',
                'max_prompt_tokens',
                'max_completion_tokens',
                'max_total_tokens',
                'valid_responses',
                'invalid_responses',
                'empty_responses',
                'schema_failures',
                'truncated_responses',
                'discarded_completion_tokens',
            ]
            with temporary.open(
                mode='w',
                encoding='utf-8',
                newline='',
            ) as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for key in sorted(self.llm_usage_metrics):
                    metric = self.llm_usage_metrics[key]
                    token_calls = metric['token_reported_calls']
                    token_divisor = token_calls or 1
                    writer.writerow({
                        **metric,
                        'chat_time_s': f"{metric['chat_time_s']:.6f}",
                        'avg_prompt_tokens': (
                            f"{metric['prompt_tokens'] / token_divisor:.3f}"
                        ),
                        'avg_completion_tokens': (
                            f"{metric['completion_tokens'] / token_divisor:.3f}"
                        ),
                        'avg_total_tokens': (
                            f"{metric['total_tokens'] / token_divisor:.3f}"
                        ),
                    })
            temporary.replace(csv_path)
        except Exception:
            logger.exception('Analyzer: write LLM usage metrics failure')

    def _write_llm_response_validation_unlocked(
            self,
            record: dict,
    ) -> None:
        """Append response-validation metadata without storing model content."""
        try:
            path = diagnostics_path(
                configs.results_path,
                'events',
                'llm_response_validation.jsonl',
            )
            self.llm_response_validation_path = path
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('a', encoding='utf-8') as stream:
                stream.write(json.dumps(record, ensure_ascii=False))
                stream.write('\n')
        except Exception:
            logger.exception('Analyzer: write LLM response validation failure')

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
                    'lifetime_response_types',
                    'lifetime_response_type_events',
                    'lifetime_response_transitions',
                    'lifetime_response_transition_events',
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
                    'lifetime_response_types': (
                        self.lifetime_res_types_num()
                    ),
                    'lifetime_response_type_events': (
                        self.lifetime_res_events_num()
                    ),
                    'lifetime_response_transitions': (
                        self.lifetime_resp_trans_num()
                    ),
                    'lifetime_response_transition_events': (
                        self.lifetime_resp_trans_events_num()
                    ),
                })
            self.record_iteration_state_metrics(
                phase='model_learning',
                iteration=iteration,
                sample_point='learning_iteration_end',
                status=status,
            )
        except Exception:
            logger.exception(
                'Analyzer: write model learning iteration metrics failure'
            )

    def record_iteration_state_metrics(
            self,
            phase: str,
            iteration: int,
            sample_point: str,
            status: str,
            *,
            skip_if_iteration_recorded: bool = False,
    ) -> bool:
        """Persist one algorithm-iteration snapshot of response-graph size.

        Unlike ``states.csv``, this table is emitted once at a defined outer
        loop boundary.  ``nodes`` and ``edges`` therefore retain the existing
        phase-cumulative response-graph meaning, while the ``iteration_*``
        columns describe only work observed in the completed iteration.
        """
        try:
            iteration = int(iteration)
        except (TypeError, ValueError):
            logger.warning(
                'Analyzer: skip iteration state metrics with invalid '
                'iteration=%r',
                iteration,
            )
            return False

        with self.lock:
            key = (phase, iteration)
            if (
                skip_if_iteration_recorded
                and key in self._recorded_iteration_state_metrics
            ):
                return False

            csv_path = configs.results_path / 'iteration_state_metrics.csv'
            write_header = (
                not csv_path.is_file()
                or csv_path.stat().st_size == 0
            )
            now = time.time()
            started = getattr(self, 'start_time', now)
            fieldnames = [
                'phase',
                'iteration',
                'sample_point',
                'status',
                'elapsed_seconds',
                'nodes',
                'edges',
                'iteration_nodes',
                'iteration_edges',
                'lifetime_nodes',
                'lifetime_edges',
            ]
            try:
                with csv_path.open(mode='a', encoding='utf-8', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    if write_header:
                        writer.writeheader()
                    writer.writerow({
                        'phase': phase,
                        'iteration': iteration,
                        'sample_point': sample_point,
                        'status': status,
                        'elapsed_seconds': (
                            f'{max(0.0, now - started):.6f}'
                        ),
                        'nodes': self.res_types_num(),
                        'edges': self.resp_trans_num(),
                        'iteration_nodes': len(self.cur_res_types_cnt),
                        'iteration_edges': len(self.cur_resp_trans_cnt),
                        'lifetime_nodes': self.lifetime_res_types_num(),
                        'lifetime_edges': self.lifetime_resp_trans_num(),
                    })
                self.iteration_state_metrics_path = csv_path
                if sample_point != 'run_final':
                    self._recorded_iteration_state_metrics.add(key)
                return True
            except Exception:
                logger.exception(
                    'Analyzer: write iteration state metrics failure'
                )
                return False

    def record_generator_checkpoint(
            self,
            phase: str,
            checkpoint_type: str,
            phase_iteration: int | None = None,
            operation_id: str = '',
            model_id: str = '',
            iteration_status: str = '',
            mutated_types: list[str] | None = None,
            baseline_operation_id: str = '',
            mutator_round_limit: int | None = None,
            mutator_rounds_attempted: int | None = None,
            published_mutator_types: list[str] | None = None,
    ) -> None:
        """Persist one whole-run response snapshot around generator updates."""
        with self.lock:
            if (
                checkpoint_type == 'run_final'
                and self._generator_metrics_finalized
            ):
                return

            now = time.time()
            current = {
                'response_events': self.lifetime_res_events_num(),
                'response_types': self.lifetime_res_types_num(),
                'transition_events': (
                    self.lifetime_resp_trans_events_num()
                ),
                'response_transitions': (
                    self.lifetime_resp_trans_num()
                ),
            }
            is_baseline = checkpoint_type.endswith('_baseline')
            previous = self._last_generator_checkpoint
            if previous is None or is_baseline:
                deltas = {
                    'response_events': 0,
                    'response_types': 0,
                    'transition_events': 0,
                    'response_transitions': 0,
                }
            else:
                deltas = {
                    key: current[key] - previous[key]
                    for key in current
                }

            evaluated_operation_id = (
                baseline_operation_id
                if is_baseline
                else (self._last_generator_operation_id or '')
            )
            csv_path = (
                configs.results_path
                / 'generator_iteration_metrics.csv'
            )
            write_header = (
                not csv_path.is_file()
                or csv_path.stat().st_size == 0
            )
            fieldnames = [
                'checkpoint_id',
                'timestamp',
                'elapsed_s',
                'phase',
                'checkpoint_type',
                'phase_iteration',
                'operation_id',
                'evaluated_operation_id',
                'model_id',
                'iteration_status',
                'mutated_types',
                'lifetime_response_events',
                'lifetime_response_types',
                'delta_response_events',
                'delta_response_types',
                'lifetime_transition_events',
                'lifetime_response_transitions',
                'delta_transition_events',
                'delta_response_transitions',
                'mutator_round_limit',
                'mutator_rounds_attempted',
                'published_mutator_types',
            ]
            try:
                with csv_path.open(
                    mode='a',
                    encoding='utf-8',
                    newline='',
                ) as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    if write_header:
                        writer.writeheader()
                    writer.writerow({
                        'checkpoint_id': self._generator_checkpoint_id,
                        'timestamp': self._format_time(now),
                        'elapsed_s': (
                            f'{max(0.0, now - self.start_time):.6f}'
                        ),
                        'phase': phase,
                        'checkpoint_type': checkpoint_type,
                        'phase_iteration': (
                            '' if phase_iteration is None else phase_iteration
                        ),
                        'operation_id': operation_id,
                        'evaluated_operation_id': evaluated_operation_id,
                        'model_id': model_id,
                        'iteration_status': iteration_status,
                        'mutated_types': json.dumps(
                            mutated_types or [],
                            separators=(',', ':'),
                        ),
                        'lifetime_response_events': (
                            current['response_events']
                        ),
                        'lifetime_response_types': (
                            current['response_types']
                        ),
                        'delta_response_events': (
                            deltas['response_events']
                        ),
                        'delta_response_types': (
                            deltas['response_types']
                        ),
                        'lifetime_transition_events': (
                            current['transition_events']
                        ),
                        'lifetime_response_transitions': (
                            current['response_transitions']
                        ),
                        'delta_transition_events': (
                            deltas['transition_events']
                        ),
                        'delta_response_transitions': (
                            deltas['response_transitions']
                        ),
                        'mutator_round_limit': (
                            ''
                            if mutator_round_limit is None
                            else mutator_round_limit
                        ),
                        'mutator_rounds_attempted': (
                            ''
                            if mutator_rounds_attempted is None
                            else mutator_rounds_attempted
                        ),
                        'published_mutator_types': json.dumps(
                            published_mutator_types or [],
                            separators=(',', ':'),
                        ),
                    })
                    f.flush()
            except Exception:
                logger.exception(
                    'Analyzer: write generator iteration metrics failure'
                )
                return

            self.generator_iteration_metrics_path = csv_path
            self._generator_checkpoint_id += 1
            self._last_generator_checkpoint = current
            if is_baseline:
                self._last_generator_operation_id = (
                    baseline_operation_id or None
                )
            elif operation_id:
                self._last_generator_operation_id = operation_id
            if checkpoint_type == 'run_final':
                self._generator_metrics_finalized = True

    def finalize_generator_metrics(
            self,
            phase_iteration: int | None = None,
    ) -> None:
        """Record the final delta once, if generator metrics were started."""
        with self.lock:
            if (
                self._last_generator_checkpoint is None
                or self._generator_metrics_finalized
            ):
                return
        self.record_generator_checkpoint(
            phase='final',
            checkpoint_type='run_final',
            phase_iteration=phase_iteration,
        )

    def write_status_snapshot(
            self,
            reason: str = 'event',
    ) -> bool:
        """Atomically write one lightweight runtime status snapshot.

        This method deliberately writes only ``fuzzer_status``.  It is safe
        to call from a periodic heartbeat while model learning is blocked and
        avoids repeatedly rewriting state/metric artifacts on that path.
        """
        results_path = getattr(configs, 'results_path', None)
        if not isinstance(results_path, Path):
            return False

        with self._status_snapshot_lock:
            now = time.time()
            with self.lock:
                start_time = getattr(self, 'start_time', now)
                if not isinstance(start_time, (int, float)):
                    start_time = now
                active_phase = self.active_phase or ''
                phase_metric = self.phase_metrics.get(active_phase, {})
                phase_start = phase_metric.get('start_time')
                phase_elapsed = (
                    max(0.0, now - phase_start)
                    if isinstance(phase_start, (int, float))
                    else 0.0
                )
                self.status_snapshot_sequence += 1
                sequence = self.status_snapshot_sequence
                self.status_last_update_timestamp = now
                fields = [
                    ('start_time', start_time),
                    ('running_time', self.seconds_to_hms(
                        max(0.0, now - start_time)
                    )),
                    ('stop_reason', self.stop_reason or 'unknown'),
                    ('run_status', self.run_status),
                    ('planned_duration_s', (
                        self.planned_duration_s
                        if self.planned_duration_s is not None else ''
                    )),
                    ('actual_duration_s', (
                        self.actual_duration_s
                        if self.actual_duration_s is not None else ''
                    )),
                    ('active_phase', active_phase or 'none'),
                    ('stage', self.stage or 'none'),
                    ('phase_elapsed_seconds', f'{phase_elapsed:.6f}'),
                    ('last_update_timestamp', f'{now:.6f}'),
                    ('status_sequence', sequence),
                    ('snapshot_reason', reason or 'event'),
                    ('target_name', getattr(self, 'target_name', '')),
                    ('protocol_name', getattr(self, 'pro_name', '')),
                    ('exec_path_num', self.path_num),
                    ('sent_request', self.req_num),
                    ('recv_resp', self.res_num),
                    ('distinct_resp', self.res_types_num()),
                    ('resp_transitions', self.resp_trans_num()),
                    ('lifetime_resp_events', self.lifetime_res_events_num()),
                    ('lifetime_distinct_resp', self.lifetime_res_types_num()),
                    ('lifetime_resp_transition_events', (
                        self.lifetime_resp_trans_events_num()
                    )),
                    ('lifetime_resp_transitions', (
                        self.lifetime_resp_trans_num()
                    )),
                    ('crash_num', self.crash_num),
                    ('non_compliant', self.non_compliant_num),
                    ('offline_mutation_attempts', self.offline_mutation_attempts),
                    ('offline_mutation_applied', self.offline_mutation_applied),
                    ('offline_mutation_bytes_added', self.offline_mutation_bytes_added),
                    ('offline_mutation_bytes_removed', self.offline_mutation_bytes_removed),
                    ('offline_mutation_operators', json.dumps(self.offline_mutation_operators, sort_keys=True)),
                    ('model_learn_time_s', self.seconds_to_hms(
                        self.model_learning_time_s
                    )),
                    ('chat_time_s', self.seconds_to_hms(self.chat_time_s)),
                    ('chat_token', self.chat_token),
                ]

            status_file = diagnostics_path(
                results_path, 'status', 'fuzzer_status'
            )
            temporary_file = status_file.with_name(
                f'.{status_file.name}.{os.getpid()}.'
                f'{threading.get_ident()}.tmp'
            )
            try:
                status_file.parent.mkdir(parents=True, exist_ok=True)
                with temporary_file.open(mode='w', encoding='utf-8') as f:
                    for name, value in fields:
                        width = (
                            15
                            if name in {
                                'start_time',
                                'running_time',
                                'stop_reason',
                                'run_status',
                                'target_name',
                                'protocol_name',
                                'exec_path_num',
                                'sent_request',
                                'recv_resp',
                                'distinct_resp',
                                'resp_transitions',
                                'crash_num',
                                'non_compliant',
                                'model_learn_time_s',
                                'chat_time_s',
                                'chat_token',
                            }
                            else 21
                            if name in {
                                'planned_duration_s',
                                'actual_duration_s',
                            }
                            else 31
                        )
                        f.write(f'{name:<{width}}: {value}\n')
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(temporary_file, status_file)
                return True
            except Exception:
                temporary_file.unlink(missing_ok=True)
                logger.exception('Analyzer: write fuzzer status failure')
                return False

    def collect_results(
            self
    ):
        self.write_status_snapshot(reason='collect_results')

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
                f.write(f'{"lifetime response types":<31}:\n')
                pprint.pprint(
                    self.lifetime_res_types_cnt.keys(),
                    stream=f
                )
                f.write(f'{"lifetime response transitions":<31}:\n')
                pprint.pprint(
                    self.lifetime_resp_trans_cnt.keys(),
                    stream=f
                )
        except Exception:
            logger.exception('Analyzer: collect state results failure')

    def collect_metric_series(
            self
    ):
        """Retained for callers that collect results at shutdown.

        State metrics are written immediately when a newly discovered response
        type or response transition changes the state graph.  Writing the
        final counters once for every elapsed minute would fabricate a time
        series, so shutdown does not append synthetic backfilled samples.
        """
        return

    def set_state_snapshot_phase(
            self,
            phase: str,
            phase_iteration: int | None,
    ) -> None:
        """Set phase-local provenance for subsequent state discoveries."""
        with self.lock:
            self._state_snapshot_phase = str(phase or '')
            self._state_snapshot_phase_iteration = phase_iteration

    def set_state_snapshot_components(
            self,
            components: list[dict[str, object]],
            request_type: str,
            parser_version: str,
    ) -> None:
        """Freeze the components that produced the response being counted."""
        normalized: list[dict[str, str]] = []
        for component in components:
            if not isinstance(component, dict):
                continue
            normalized.append({
                'request_type': str(component.get('request_type', '')),
                'kind': str(component.get('kind', '')),
                'version': str(component.get('version', '')),
                'evolve_round': str(component.get('evolve_round', '')),
            })
        with self.lock:
            self._state_snapshot_components = tuple(normalized)
            self._state_snapshot_request_type = str(request_type or '')
            self._state_snapshot_parser_version = str(parser_version or '')

    def _record_state_snapshot(
            self,
            event: str,
            event_value: str,
    ) -> None:
        """Append one timestamped state-graph snapshot for a new discovery."""
        results_path = getattr(configs, 'results_path', None)
        start_time = getattr(self, 'start_time', None)
        if (
            not isinstance(results_path, Path)
            or not results_path.is_dir()
            or not isinstance(start_time, (int, float))
        ):
            return

        with self.lock:
            timestamp = time.time()
            elapsed_seconds = max(0.0, timestamp - start_time)
            series_file = results_path / 'states.csv'
            write_header = (
                self._state_snapshot_path != series_file
                or not series_file.is_file()
                or series_file.stat().st_size == 0
            )
            fieldnames = [
                'subject',
                'fuzzer',
                'data_type',
                'time',
                'data',
                'event',
                'event_value',
                'event_timestamp',
                'elapsed_seconds',
                'phase',
                'phase_iteration',
                'evolve_round',
                'generator',
                'version',
                'component_kind',
                'request_type',
                'parser_version',
                'component_versions',
            ]
            components = self._state_snapshot_components
            active_component = components[-1] if components else {}
            component_versions = json.dumps(
                list(components),
                ensure_ascii=False,
                sort_keys=True,
                separators=(',', ':'),
            )
            values = (
                ('nodes', self.res_types_num()),
                ('edges', self.resp_trans_num()),
                ('lifetime_response_events', self.lifetime_res_events_num()),
                ('lifetime_response_types', self.lifetime_res_types_num()),
                (
                    'lifetime_response_transition_events',
                    self.lifetime_resp_trans_events_num(),
                ),
                (
                    'lifetime_response_transitions',
                    self.lifetime_resp_trans_num(),
                ),
            )
            try:
                with series_file.open(
                    mode='a', encoding='utf-8', newline=''
                ) as stream:
                    writer = csv.DictWriter(stream, fieldnames=fieldnames)
                    if write_header:
                        writer.writeheader()
                    for data_type, data in values:
                        writer.writerow({
                            'subject': getattr(self, 'target_name', ''),
                            'fuzzer': 'voltron',
                            # Keep the historical minute-based field for
                            # existing result consumers.  Exact ordering is
                            # available through the new elapsed/timestamp
                            # columns.
                            'time': int(elapsed_seconds // 60),
                            'data_type': data_type,
                            'data': data,
                            'event': event,
                            'event_value': event_value,
                            'event_timestamp': f'{timestamp:.6f}',
                            'elapsed_seconds': f'{elapsed_seconds:.6f}',
                            'phase': self._state_snapshot_phase,
                            'phase_iteration': (
                                ''
                                if self._state_snapshot_phase_iteration is None
                                else self._state_snapshot_phase_iteration
                            ),
                            'evolve_round': active_component.get(
                                'evolve_round',
                                '',
                            ),
                            'generator': active_component.get(
                                'request_type',
                                '',
                            ),
                            'version': active_component.get('version', ''),
                            'component_kind': active_component.get('kind', ''),
                            'request_type': self._state_snapshot_request_type,
                            'parser_version': self._state_snapshot_parser_version,
                            'component_versions': component_versions,
                        })
                self._state_snapshot_path = series_file
            except Exception:
                logger.exception('Analyzer: write state snapshot failure')

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
        is_new_lifetime_type = res_code not in self.lifetime_res_types_cnt
        if res_code in self.res_types_cnt.keys():
            self.res_types_cnt[res_code] +=  1
        else:
            self.res_types_cnt[res_code] = 1
            logger.debug(f'Analyzer: new reply {res_code}')
            
        if res_code in self.cur_res_types_cnt.keys():
            self.cur_res_types_cnt[res_code] +=  1
        else:
            self.cur_res_types_cnt[res_code] = 1

        if res_code in self.lifetime_res_types_cnt:
            self.lifetime_res_types_cnt[res_code] += 1
        else:
            self.lifetime_res_types_cnt[res_code] = 1
        if is_new_lifetime_type:
            self._record_state_snapshot('new_response_type', res_code)

    def resp_trans_update(
            self,
            trans: str
    ):
        is_new_lifetime_transition = trans not in self.lifetime_resp_trans_cnt
        if trans in self.resp_trans_cnt.keys():
            self.resp_trans_cnt[trans] += 1
        else:
            self.resp_trans_cnt[trans] = 1
            logger.debug(f'Analyzer: new transition {trans}')
            
        if trans in self.cur_resp_trans_cnt.keys():
            self.cur_resp_trans_cnt[trans] +=  1
        else:
            self.cur_resp_trans_cnt[trans] = 1

        if trans in self.lifetime_resp_trans_cnt:
            self.lifetime_resp_trans_cnt[trans] += 1
        else:
            self.lifetime_resp_trans_cnt[trans] = 1
        if is_new_lifetime_transition:
            self._record_state_snapshot('new_response_transition', trans)

    
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

    def lifetime_res_events_num(
            self
    ):
        return sum(self.lifetime_res_types_cnt.values())

    def lifetime_res_types_num(
            self
    ):
        return len(self.lifetime_res_types_cnt)

    def lifetime_resp_trans_events_num(
            self
    ):
        return sum(self.lifetime_resp_trans_cnt.values())

    def lifetime_resp_trans_num(
            self
    ):
        return len(self.lifetime_resp_trans_cnt)
    
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
    
