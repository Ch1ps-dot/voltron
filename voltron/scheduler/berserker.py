from voltron.executor.mapper import Mapper
from voltron.synthesizer.synthesizer import Generator
from voltron.executor.executor import Executor, Conversation
from voltron.analyzer.analyzer import analyzer
from voltron.learner.automata import MealyMachine
from voltron.configs import configs
from voltron.scheduler.seed_retention import SeedRetentionPolicy
from voltron.learner.partial_guidance import PartialStateGraph
from voltron.utils.logger import logger_fuzz as logger
from voltron.scheduler.offline_mutator import OfflineMutator
from typing import TypedDict
import random, time, threading, os, math


class StateStats(TypedDict):
    state_id: int
    depth: int
    call_count: int
    total_reward: float
    out_degree: int
    covered_transitions: set[str]
    last_score: float


class Berserker:
    """Berserker scheduler implementation for fuzzing the system under test (SUT) with random sequences of requests, aiming to explore the state space and find interesting behaviors.
    
    Attributes:
        unique_resp: A set of unique responses observed during fuzzing.
        max_unique_resp_num: The maximum number of unique responses observed so far.
        unique_resp_trans: A set of unique response transitions observed during fuzzing.
        useful_msg: A list of useful messages (request-response pairs) that have been observed during fuzzing.
        useful_seq: A list of useful sequences of request-response pairs that have been observed during fuzzing.
        max_seq_len: The maximum length of request-response sequences observed so far.
        mapper: An instance of the Mapper class for selecting generators and mutators based on request sequences.
        exe: An instance of the Executor class for interacting with the SUT and obtaining responses.
        alphabet: A list of request types that can be used for generating test sequences.
        req_dep: A dictionary representing the dependencies between requests and their possible responses, used for generating dependent sequences.
        dep_alphabet: A list of request types that have dependencies, used for generating dependent sequences.
        req_res: A dictionary mapping request types to the set of response types observed for those requests
    """
    BUG_RESPONSES = {'CRASH'}

    def __init__(
        self,
        mapper: Mapper,
        exe: Executor,
        machine: MealyMachine | None,
        use_guidance: bool = True,
        partial_guidance: PartialStateGraph | None = None,
        interesting_seed_sequences: list[list[tuple[str, bytes]]] | None = None,
        replay_imported_seed_sequences: bool = True,
        controller=None,
    ) -> None:
        self.seed_retention = SeedRetentionPolicy()
        self.unique_resp = self.seed_retention.unique_responses
        self.max_unique_resp_num = 0
        self.unique_resp_trans: set[str] = set()
        self.useful_msg: list[tuple[str, bytes]] = []
        self.useful_seq: list[list[tuple[str, bytes]]] = []
        self.partial_guidance = partial_guidance if use_guidance else None
        self.partial_seed_sequences: list[list[tuple[str, bytes]]] = (
            self.partial_guidance.seed_sequences()
            if self.partial_guidance is not None
            else []
        )
        # Reuse partial traces through the existing interesting-seed path as
        # well as the explicit prefix path below.  They remain ordinary fuzz
        # seeds, never inferred machine states.
        self.useful_seq.extend(self.partial_seed_sequences)
        # Imported AFLNet traffic is already a concrete, replayable request
        # sequence.  Treat it as interesting seed material, not as a mapper
        # symbol or a model-learning trace.
        self.imported_seed_sequences = [
            list(sequence)
            for sequence in (interesting_seed_sequences or [])
            if sequence
        ]
        self.replay_imported_seed_sequences = bool(
            replay_imported_seed_sequences
        )
        self.imported_seed_replay_complete = False
        self.useful_seq.extend(self.imported_seed_sequences)
        self.seed_prefix_sequences = (
            self.partial_seed_sequences + self.imported_seed_sequences
        )
        self.selected_partial_prefix = False
        self.selected_imported_seed_prefix = False
        self.partial_prefix_attempts = 0
        self.max_seq_len = 0
        self.seen_req_res_pairs = self.seed_retention.seen_request_response_pairs

        self.mapper = mapper
        self.exe = exe
        self.controller = controller
        self.alphabet = list(mapper.request_types)
        self.use_guidance = use_guidance
        self.req_dep: dict[str, dict[str, dict]] = (
            mapper.req_dep if use_guidance else {}
        )
        self.dep_alphabet = list(self.req_dep.keys())
        
        self.req_res: dict[str, set[str]] = {}
        
        self.rand = random.Random( time.time_ns() ^ os.getpid() ^ threading.get_ident())
        self.offline_mutator = OfflineMutator(
            enabled=getattr(configs, 'offline_mutation_enabled', True),
            probability=getattr(configs, 'offline_mutation_probability', 0.3),
            max_mutated_packets_per_sequence=getattr(
                configs, 'offline_mutation_max_mutated_packets_per_sequence', 3,
            ),
            max_mutations_per_packet=getattr(
                configs, 'offline_mutation_max_mutations_per_packet', 4,
            ),
            max_delta_bytes=getattr(configs, 'offline_mutation_max_delta_bytes', 4),
            max_message_length=getattr(
                configs, 'offline_mutation_max_message_length', 65536,
            ),
            extreme_message_length=getattr(
                configs, 'offline_mutation_extreme_message_length', 4096,
            ),
            seed=getattr(configs, 'offline_mutation_seed', 0),
            mutate_imported_seeds=getattr(configs, 'offline_mutation_imported_seeds', True),
            protected_types=getattr(configs, 'offline_mutation_protected_types', []),
            aflnet_single_packet=getattr(
                configs, 'offline_mutation_aflnet_single_packet', True,
            ),
            aflnet_dictionary=getattr(
                configs, 'offline_mutation_aflnet_dictionary', []
            ),
            aflnet_havoc_stack=getattr(
                configs, 'offline_mutation_aflnet_havoc_stack', 4,
            ),
        )
        
        # Define the methods and modes for selecting prefixes, mutators, and suffixes during fuzzing
        # cat: concatenate prefix, mutators, and suffix; 
        # int: interleave prefix and mutators, then concatenate with suffix
        self.methods = ['cat', 'int']
        
         # new: select new sequences or messages that have not been observed before; 
        # generic: select from the useful sequences or messages observed so far; 
        # dependent: select sequences or messages based on the dependencies between requests
        self.mutated_seq_mode = ['random', 'interesting', 'specific']
        self.base_state_mode = ['random', 'priority', 'specific']

        if not use_guidance:
            self.mutated_seq_mode = ['random']
            self.base_state_mode = ['random']
        
        # Initialize the automaton and related sets based on the provided Mealy machine, if available
        self.machine = machine
        self.states: list[tuple[str, ...]] = []
        self.state_stats: dict[tuple[str, ...], StateStats] = {}
        self.selected_base_state: tuple[str, ...] | None = None
        self.selected_base_state_mode = ''
        self.visited_machine_states: set[int] = set()
        self.transit: list[tuple[str, ...]] = []
        if machine and use_guidance:
            self.machine = machine
            self.table = machine.table
            self.trans = list(self.table[1])
            self.T = self.table[2]

            candidate_states = []
            for p in list(self.table[0]):
                if len(p) == 1:
                    candidate_states.append(p)
                elif len(p) > 1 and self.T[p[:-1]][p[-1:]] != 'CRASH' and self.T[p[:-1]][p[-1:]] != 'TIMEOUT':
                    candidate_states.append(p)

            access_sequences: dict[int, tuple[str, ...]] = {}
            for state in sorted(
                candidate_states,
                key=lambda item: (sum(symbol != '-' for symbol in item), item),
            ):
                state_id = self._machine_state_after(state)
                if state_id is not None and state_id not in access_sequences:
                    access_sequences[state_id] = state

            self.states = list(access_sequences.values())
            self.visited_machine_states.add(machine.start)

            self.state_stats = {
                state: {
                    'state_id': state_id,
                    'depth': sum(symbol != '-' for symbol in state),
                    'call_count': 0,
                    'total_reward': 0.0,
                    'out_degree': len(self._outgoing_symbols(state_id)),
                    'covered_transitions': set(),
                    'last_score': 0.0,
                }
                for state_id, state in access_sequences.items()
            }

    def _should_stop(self) -> bool:
        """Check the global controller before starting more scheduler work."""
        controller = self.controller
        if controller is None:
            controller = getattr(self.exe, 'run_controller', None)
        should_stop = getattr(controller, 'should_stop', None)
        if callable(should_stop):
            return bool(should_stop())
        stop_event = getattr(self.exe, 'stop_event', None)
        return bool(stop_event is not None and stop_event.is_set())

    @property
    def max_seq_len(self) -> int:
        return self.seed_retention.max_sequence_length

    @max_seq_len.setter
    def max_seq_len(self, value: int) -> None:
        self.seed_retention.max_sequence_length = value

    @property
    def max_unique_resp_num(self) -> int:
        return self.seed_retention.max_unique_response_count

    @max_unique_resp_num.setter
    def max_unique_resp_num(self, value: int) -> None:
        self.seed_retention.max_unique_response_count = value

    def _machine_state_after(
        self,
        access_sequence: tuple[str, ...],
    ) -> int | None:
        if self.machine is None:
            return None

        state_id = self.machine.start
        try:
            for symbol in access_sequence:
                if symbol != '-':
                    state_id = self.machine.delta[(state_id, symbol)]
        except KeyError:
            logger.debug(
                'Berserker: access sequence is absent from machine delta: '
                f'{access_sequence}'
            )
            return None
        return state_id

    def _outgoing_symbols(self, state_id: int) -> set[str]:
        if self.machine is None:
            return set()
        return {
            symbol
            for source, symbol in self.machine.delta
            if source == state_id
        }

    def calculate_state_priority(
        self,
        state: tuple[str, ...],
    ) -> float:
        """Calculate the equally weighted reward, exploration, and structure score."""
        stats = self.state_stats[state]
        total_calls = sum(
            item['call_count'] for item in self.state_stats.values()
        )
        average_rewards = {
            candidate: item['total_reward'] / max(item['call_count'], 1)
            for candidate, item in self.state_stats.items()
        }
        explorations = {
            candidate: math.sqrt(
                math.log(total_calls + 1) / (item['call_count'] + 1)
            )
            for candidate, item in self.state_stats.items()
        }
        max_average_reward = max(average_rewards.values(), default=0.0)
        max_exploration = max(explorations.values(), default=0.0)
        normalized_reward = (
            average_rewards[state] / max_average_reward
            if max_average_reward > 0.0
            else 0.0
        )
        normalized_exploration = (
            explorations[state] / max_exploration
            if max_exploration > 0.0
            else 0.0
        )

        max_depth = max(
            (item['depth'] for item in self.state_stats.values()),
            default=0,
        )
        max_out_degree = max(
            (item['out_degree'] for item in self.state_stats.values()),
            default=0,
        )
        depth = stats['depth'] / max(max_depth, 1)
        uncovered = (
            stats['out_degree'] - len(stats['covered_transitions'])
        ) / max(max_out_degree, 1)
        structure = (depth + uncovered) / 2
        score = (
            normalized_reward + normalized_exploration + structure
        ) / 3
        stats['last_score'] = score
        return score

    def select_priority_state(self) -> tuple[str, ...] | None:
        if not self.states:
            return None

        scores = {
            state: self.calculate_state_priority(state)
            for state in self.states
        }
        best_score = max(scores.values())
        candidates = [
            state
            for state, score in scores.items()
            if math.isclose(score, best_score, rel_tol=1e-12, abs_tol=1e-12)
        ]
        return self.rand.choice(candidates)

    def _use_machine_state(
        self,
        state: tuple[str, ...],
        mode: str,
    ) -> list[tuple[str, bytes]]:
        self.selected_base_state = state
        self.selected_base_state_mode = mode
        self.state_stats[state]['call_count'] += 1
        return self.mapper.select_generators(list(state))

    def select_random_requests(
        self,
        min_length: int = 1,
        max_length: int = 8,
    ) -> list[tuple[str, bytes]]:
        if not self.alphabet:
            return []
        length = self.rand.randint(min_length, max_length)
        request_types = [
            self.rand.choice(self.alphabet)
            for _ in range(length)
        ]
        return self.mapper.select_generators(request_types)

    def select_base_state(
        self
    ) -> list[tuple[str, bytes]]:
        """Select a prefix sequence of requests to be used for generating test sequences, based on the observed useful sequences and the dependencies between requests.
        """
        self.selected_base_state = None
        self.selected_base_state_mode = ''
        self.selected_partial_prefix = False
        self.selected_imported_seed_prefix = False
        if self.partial_seed_sequences or self.imported_seed_sequences:
            # Prefer concrete MQ prefixes often enough to preserve useful
            # learning evidence, while leaving the rest of the scheduler's
            # random/dependency behavior intact.
            if self.rand.random() < 0.5:
                self.selected_partial_prefix = True
                self.partial_prefix_attempts += 1
                selected = self.rand.choice(self.seed_prefix_sequences)
                if any(
                    selected is imported
                    for imported in self.imported_seed_sequences
                ):
                    self.selected_partial_prefix = False
                    self.selected_imported_seed_prefix = True
                return list(selected)
        mode = ''
        if len(self.useful_seq) == 0:
            mode = 'random'
        else:
            mode = self.rand.choice(self.base_state_mode)
        gs = []
        
        if mode == 'random':
            if self.states:
                p = self.rand.choice(self.states)
                gs = self._use_machine_state(p, mode)
            else:
                gs = self.select_random_requests()
            
        elif mode == 'specific':
            if len(self.dep_alphabet) > 0:
                cur_req = self.rand.choice(self.dep_alphabet)
                req_seq = []
                while True:
                    if cur_req in req_seq or cur_req not in self.dep_alphabet:
                        req_seq = [cur_req] + req_seq
                        break
                    req_seq = [cur_req] + req_seq
                    last_dict: dict[str, dict] = self.req_dep[cur_req]
                    last_req = self.rand.choice(list(last_dict.keys()))
                    cur_req = last_req
                gs = self.mapper.select_generators(req_seq)
            else:
                gs = self.rand.choice(self.useful_seq)
                
        elif mode == 'priority':
            p = self.select_priority_state()
            if p is not None:
                gs = self._use_machine_state(p, mode)
            else:
                gs = self.select_random_requests()
        
        logger.debug(f'select prefix[{mode}]: {'/'.join([g[0] for g in gs])}')
        return gs

    def replay_imported_seed_sequences_once(self) -> None:
        """Replay imported AFLNet streams exactly once before fuzz scheduling.

        This is deliberately separate from the interesting-seed path: a
        scheduler-selected seed may receive a suffix and optional offline
        mutations, while this audit replay preserves every message byte and
        sequence boundary from the imported replay asset.
        """
        if self.imported_seed_replay_complete:
            return
        self.imported_seed_replay_complete = True
        if not self.replay_imported_seed_sequences:
            return
        for sequence in self.imported_seed_sequences:
            if self._should_stop():
                return
            logger.info(
                'Berserker: exact replay of imported AFLNet seed sequence '
                '(%d messages)',
                len(sequence),
            )
            try:
                self.exe.interact(
                    list(sequence),
                    poll_wait_ms=3000,
                    run_checker=True,
                )
            except Exception:
                # An imported corpus sample is diagnostic input.  One bad
                # replay must not prevent later corpus samples or fuzzing.
                logger.exception(
                    'Berserker: imported AFLNet seed exact replay failed'
                )

    def update_state_feedback(
        self,
        request_sequence: list[tuple[str, bytes]],
        prefix_length: int,
        transition_increment: int,
        response_increment: int,
        conversation: Conversation | None,
        bug_signal: bool = False,
    ) -> None:
        """Update reward and coverage for the state selected this round."""
        state = self.selected_base_state
        if state is None:
            return

        stats = self.state_stats[state]
        state_id = stats['state_id']
        expected_prefix = [symbol for symbol in state if symbol != '-']
        actual_prefix = [
            message_type
            for message_type, _ in request_sequence[:prefix_length]
        ]
        if actual_prefix != expected_prefix:
            logger.debug(
                'Berserker: skip state feedback because the target state '
                f'was not reached; expected={expected_prefix} '
                f'actual={actual_prefix}'
            )
            return

        discovered_state = state_id not in self.visited_machine_states
        self.visited_machine_states.add(state_id)

        if prefix_length < len(request_sequence):
            outgoing_symbol = request_sequence[prefix_length][0]
            if outgoing_symbol in self._outgoing_symbols(state_id):
                stats['covered_transitions'].add(outgoing_symbol)
                if self.machine is not None:
                    destination = self.machine.delta[(state_id, outgoing_symbol)]
                    if destination not in self.visited_machine_states:
                        discovered_state = True
                        self.visited_machine_states.add(destination)

        responses = set(conversation.res_seq) if conversation is not None else set()
        crashed = bool(responses & self.BUG_RESPONSES)

        reward = (
            1.0 * discovered_state
            + 0.7 * (transition_increment > 0)
            + 0.5 * (response_increment > 0)
            + 2.0 * crashed
            + 5.0 * (crashed or bug_signal)
        )
        stats['total_reward'] += reward
        logger.debug(
            'Berserker: update state reward '
            f'state={state} reward={reward:.2f} '
            f'total={stats["total_reward"]:.2f}'
        )

    def select_suffix(
        self
    ) -> list[tuple[str, bytes]]:
        if self.transit:
            p = self.rand.choice(self.transit)
            return self.mapper.select_generators(list(p))
        return self.select_random_requests()
    
    def select_mutated_seq(
        self
    ) -> list[tuple[str, bytes]]:
        scope = self.rand.randint(1, 42)
        mut = self.rand.choice([True, False])
        ms = []
        mode = ''
        if len(self.useful_msg) == 0:
            mode = 'random'
        else:
            mode = self.rand.choice(self.mutated_seq_mode)
            
        if mode == 'random':
            req_seq = []
            for i in range(scope):
                a = self.rand.choice(self.alphabet)
                req_seq.append(a)
                
            if mut:
                ms = self.mapper.select_mutators(req_seq)
            else:
                ms = self.mapper.select_generators(req_seq)
                
        elif mode == 'interesting':
            for i in range(scope):
                a = self.rand.choice(self.useful_msg)
                ms.append(a)
            
        elif mode == 'specific':
            if len(self.dep_alphabet) > 0:
                cur_req = self.rand.choice(self.dep_alphabet)
                req_seq = []
                while True:
                    if cur_req in req_seq or cur_req not in self.dep_alphabet:
                        req_seq = [cur_req] + req_seq
                        break
                    req_seq = [cur_req] + req_seq
                    
                    last_dict: dict[str, dict] = self.req_dep[cur_req]
                    last_req = self.rand.choice(list(last_dict.keys()))
                    cur_req = last_req
                if mut:
                    ms = self.mapper.select_mutators(req_seq)
                else:
                    ms = self.mapper.select_generators(req_seq)
            else:
                for i in range(scope):
                    a = self.rand.choice(self.useful_msg)
                    ms.append(a)
                    
        logger.debug(f'select mutators[{mode}]: {'/'.join([m[0] for m in ms])}')
        return ms

    def analyze_cons(
        self,
        cons: Conversation,
        trans_inc: int,
        type_inc: int
    ):
        """Analyze the conversation obtained from interacting with the SUT.
        
        Args:
            cons: The conversation object containing the request and response sequences, as well as the content of the responses
            trans_inc: The increment in the number of response transitions observed compared to the last interaction
            type_inc: The increment in the number of unique response types observed compared to the last interaction
        """
        novelty = self.seed_retention.observe(cons, trans_inc, type_inc)
        self.max_seq_len = self.seed_retention.max_sequence_length
        self.max_unique_resp_num = (
            self.seed_retention.max_unique_response_count
        )

        for index, _response_type in novelty.new_responses:
            content = cons.content[index] if index < len(cons.content) else None
            if content is None or index >= len(cons.req_seq):
                continue
            request_type = cons.req_seq[index]
            self.useful_msg.append((request_type, content[0]))
            sequence = []
            prefix_length = min(index + 1, len(cons.req_seq), len(cons.content))
            for prefix_index in range(prefix_length):
                if cons.req_seq[prefix_index] != '-':
                    sequence.append(
                        (cons.req_seq[prefix_index], cons.content[prefix_index][0])
                    )
            self.useful_seq.append(sequence)

        for request_type, response_type in novelty.request_response_relations:
            response_types = self.req_res.setdefault(request_type, set())
            response_types.add(response_type)

        if novelty.interesting:
            with analyzer.lock:
                analyzer.useful_cons += 1
            logger.debug('Berserker: interesting conversation')
            self.exe.save_cons(cons)
        # seq = []
        # if len(cons.res_seq) > self.max_seq_len:
        #     for i in range(len(cons.res_seq)):
        #         if cons.req_seq[i] != '-':
        #             seq.append((cons.req_seq[i], cons.content[i][0]))
        #     self.useful_seq.append(seq)
        
    def run(
        self,
        times: int
    ) -> dict[str, set[str]]:
        """fuzing the SUT with random sequences of requests.
        """
        logger.debug(self.states)
        logger.debug(self.alphabet)
        analyzer.set_progress('berserker', 'fuzz energy', times)
        energy = times
        analyzer.finished = energy
        
        # fuzzing the SUT until the energy is depleted, where energy is increased when new behaviors are observed and decreased when no new behaviors are found
        while (
            (energy >= 0 if self.use_guidance else energy > 0)
            and not self._should_stop()
        ):
            last_resp_num = analyzer.res_types_num()
            last_trans_nums = analyzer.resp_trans_num()
            last_non_compliant_num = analyzer.non_compliant_num
            
            ms = []
            prefix = self.select_base_state()
            if self.mapper.mutators != {}:
                ms = self.select_mutated_seq()
            suffix = self.select_suffix()
            ms = ms + suffix
            req_seq = []
            
            method = (
                'cat'
                if (
                    self.selected_base_state is not None
                    or self.selected_partial_prefix
                    or self.selected_imported_seed_prefix
                )
                else self.rand.choice(self.methods)
            )
            if (method == 'cat'):
                req_seq = prefix + ms + suffix
            elif (method == 'int'):
                len_p = len(prefix)
                len_m = len(ms)
                max_len = max(len_p, len_m)
                for i in range(max_len):
                    if (i < len_p):
                        req_seq.append(prefix[i])
                    if (i < len_m):
                        req_seq.append(ms[i])

            imported = self.selected_imported_seed_prefix
            protected_prefix_length = len(prefix)
            if imported and self.offline_mutator.mutate_imported_seeds:
                # Imported AFLNet traffic is a concrete fuzz seed, not an
                # access sequence that must remain intact to reach a model
                # state.  Its dedicated option therefore overrides the
                # general prefix protection policy.
                protected_prefix_length = 0
            req_seq, offline_changes = self.offline_mutator.mutate_sequence(
                req_seq,
                prefix_length=protected_prefix_length,
                imported=imported,
            )
            if offline_changes:
                for index, operator, _delta in offline_changes:
                    msg_type, message = req_seq[index]
                    remember = getattr(self.mapper, '_remember_message_provenance', None)
                    if callable(remember):
                        remember(message, request_type=msg_type, kind='offline', version=f'offline:{operator}')
                stats = self.offline_mutator.stats
                with analyzer.lock:
                    analyzer.offline_mutation_attempts = stats.attempts
                    analyzer.offline_mutation_applied = stats.applied
                    analyzer.offline_mutation_bytes_added = stats.bytes_added
                    analyzer.offline_mutation_bytes_removed = stats.bytes_removed
                    analyzer.offline_mutation_operators = dict(stats.operators)
            elif self.offline_mutator.stats.attempts:
                stats = self.offline_mutator.stats
                with analyzer.lock:
                    analyzer.offline_mutation_attempts = stats.attempts

            flag, cons = self.exe.interact(
                req_seq,
                poll_wait_ms=3000,
                run_checker=True,
            )
            if self._should_stop():
                break
            cur_trans_nums = analyzer.resp_trans_num()
            cur_resp_num = analyzer.res_types_num()
            transition_increment = cur_trans_nums - last_trans_nums
            response_increment = cur_resp_num - last_resp_num

            self.update_state_feedback(
                request_sequence=req_seq,
                prefix_length=len(prefix),
                transition_increment=transition_increment,
                response_increment=response_increment,
                conversation=cons,
                bug_signal=(
                    analyzer.non_compliant_num > last_non_compliant_num
                ),
            )
            
            if cons != None:
                self.analyze_cons(
                    cons,
                    transition_increment,
                    response_increment,
                )
                analyzer.sent = '/'.join([msg_type for msg_type, _ in req_seq]) + f'({method})'
                analyzer.recv = '/'.join(cons.res_seq)
                logger.debug(f'sent({method}) -> {analyzer.sent}')
                logger.debug(f'recv({method}) <- {analyzer.recv}')
            else:
                analyzer.sent = '/'.join([msg_type for msg_type, _ in req_seq])
                analyzer.recv = 'None'
            
            if not self.use_guidance:
                energy -= 1
                with analyzer.lock:
                    analyzer.finished -= 1
            elif cur_trans_nums <= last_trans_nums:
                energy -= 1
                with analyzer.lock:
                    analyzer.finished -= 1
            else:
                energy += 1
                with analyzer.lock:
                    analyzer.finished += 1
                
        
        analyzer.clean_progress()
        return self.req_res
        
    def is_interesting(
        self,
        trans_inc: int,
        type_inc: int,
        len_inc: int,
        unique_res_inc: int,
        req_res_inc: int
    ) -> bool:
        """Check whether the conversation exposes any new protocol behavior.
        
        Args:
            trans_inc: The increment in the number of response transitions observed.
            type_inc: The increment in the number of unique response types observed.
            len_inc: The increment in sequence length, retained for telemetry.
            unique_res_inc: The increment in distinct response types, retained
                for telemetry.
            req_res_inc: The number of newly observed request-response type
                relations in the current conversation.
        """
        if SeedRetentionPolicy.is_interesting(
            trans_inc,
            type_inc,
            len_inc,
            unique_res_inc,
            req_res_inc,
        ):
            with analyzer.lock:
                analyzer.useful_cons += 1
            logger.debug(
                'Berserker: interesting conversation '
                f'trans={trans_inc} types={type_inc} length={len_inc} '
                f'unique_responses={unique_res_inc} '
                f'request_response_relations={req_res_inc}'
            )
            return True
        else:
            return False
