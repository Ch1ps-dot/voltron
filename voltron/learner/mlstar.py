from voltron.executor.mapper import Mapper
from voltron.synthesizer.synthesizer import Generator, Parser
from voltron.learner.automata import MealyMachine
from voltron.learner.equ_oracle import EquOracle
from voltron.learner.mem_oracle import MembershipOracle
from voltron.utils.logger import logger
from voltron.configs import configs
from voltron.analyzer.analyzer import analyzer
import pprint, pickle, threading, sys, traceback, time, copy


class ObTable:
    """Oberservation Table for LM* algorithm, which is used to learn the Mealy machine model of the SUT.
    
    Attributes:
        alphabet: A list of input symbols (requests) that can be sent to the SUT.
        S: A set of tuples representing the prefixes of input sequences observed so far.
        E: A set of tuples representing the suffixes of input sequences observed so far.
        T: A dictionary mapping tuples of prefixes and suffixes to the corresponding outputs (responses) observed from the SUT.
        mq: An instance of MembershipOracle used to query the SUT for responses to input sequences.
        eq: An instance of EquOracle used to compare the learned Mealy machine with the actual behavior of the SUT and find distinguishing input sequences if they are not equivalent
    """
    def __init__(
        self,
        mq: MembershipOracle,
        eq: EquOracle,
        stop_event: threading.Event
    ) -> None:
        self.alphabet: list[str] = mq.alphabet # request symbol
        
        self.S: set[tuple[str,...]] = {('-',)} # prefix of request symbols
        self.E: set[tuple[str,...]] = {(a,) for a in self.alphabet} # suffix of request symbols
        
        self.T: dict[tuple[str,...], dict[tuple[str,...], tuple[str,...]]] = {} # (s, a, e) -> output. Transition
        
        self.mq = mq
        self.eq = eq
        self.stop_event = stop_event
        
    def table_init(self):
        self._fill_table()

    def _fill_table(self):
        
        iter_s = 0
        logger.debug('Ob: fill table')
        with analyzer.lock:
            analyzer.set_progress('Obtable', desc='fill s table', total=1)

        # fill (s, e) table entry
        for s in self.S:

            for e in self.E:
                iter_s += 1
                if s not in self.T.keys():
                    self.T[s] = {}
                
                if e in self.T[s].keys():
                    logger.debug(f'existed entry: {s}:{e} => {self.T[s][e]}')
                    continue    
                
                else:
                    
                    if (configs.time_limit_s < time.time() - analyzer.start_time):
                        logger.debug('Fuzzer: timeout')
                        self.stop_event.set()
                    if self.stop_event.is_set(): 
                        sys.exit(0)
                        
                    if(len(s) != 1 and self.T[s[:-1]][s[-1:]] == ('CLOSED',)):
                        self.T[s][e] = ('CLOSED',)
                        continue
                    if(len(s) != 1 and self.T[s[:-1]][s[-1:]] == ('CRASH',)):
                        self.T[s][e] = ('CRASH',)
                        continue
                    if(len(s) != 1 and self.T[s[:-1]][s[-1:]] == ('TIMEOUT',)):
                        self.T[s][e] = ('TIMEOUT',)
                        continue
                                    
                    out = self.mq.query(s + e)
                    
                    if (out):
                        if len(s) > 0:
                            if 'TIMEOUT' == out[-1] and len(out) < len(s):
                                logger.debug('fill table: try again')
                                continue
                        with analyzer.lock:
                            analyzer.sent = f'{'/'.join(s)}:{'/'.join(e)} ({iter_s}/{len(self.S) * len(self.E)})'
                            analyzer.recv = f'{'/'.join(out)}'
                            
                        self.T[s][e] = tuple(out[-len(e):])
                        logger.debug(f'query entry: {s}:{e} => {self.T[s][e]}')
                    else:
                        logger.debug('fill table: no out')
                        sys.exit(0)
                        

        with analyzer.lock:
            analyzer.set_progress('Obtable', desc='fill si table', total=1)
        iter_si = 0
        
        # fill (s+a, e) entry
        for s in self.S:
            for a in self.alphabet:
                
                si = s + (a,) # S + i (element in alphabet)
                
                if si not in self.T.keys():
                    self.T[si] = {}
                    
                for e in self.E:
                    iter_si += 1
                    if (configs.time_limit_s < time.time() - analyzer.start_time):
                        logger.debug('Fuzzer: timeout')
                        self.stop_event.set()
                        
                    if self.stop_event.is_set(): 
                        sys.exit(0)
                        
                    if e in self.T[si].keys():
                        logger.debug(f'existed entry: {si}:{e} => {self.T[si][e]}')
                        continue
                    
                    # connection was closed before sending suffix request
                    # in this situation, there is no more response and destroy the evaluation
                    # so we just consider they are transfering to same state and jump the query
                    else:
                        if(self.T[s][(a,)] == ('CLOSED',)):
                            self.T[si][e] = ('CLOSED',)
                            continue
                        if(self.T[s][(a,)] == ('CRASH',)):
                            self.T[si][e] = ('CRASH',)
                            continue
                        if(self.T[s][(a,)] == ('TIMEOUT',)):
                            self.T[si][e] = ('TIMEOUT',)
                            continue
                        
                        try_times = 3
                        out = []
                        while True:
                            out = self.mq.query(si + e)
                            if (out):
                                # sometimes the randomness of server will cause timeout
                                # when output is inconsistent with previous results, just try again
                                if len(si) > 0:
                                    if 'TIMEOUT' == out[-1] and len(out) < len(si):
                                        logger.debug('fill table: try again')
                                        try_times -= 1
                                        if try_times <= 0:
                                            self.T[si[:len(out)-1]][si[-1:]] = ('TIMEOUT',)
                                        else:
                                            continue
                                
                                self.T[si][e] = tuple(out[-len(e):])
                                
                                with analyzer.lock:
                                    analyzer.sent = f'{'/'.join(s)}:{a}:{'/'.join(e)} ({iter_si}/{len(self.S) * len(self.alphabet) * len(self.E)})'
                                    analyzer.recv = f'{'/'.join(out)}'
                                logger.debug(f'query entry: {s}:{a}:{e} => {self.T[si][e]}')
                                break
                            else:
                                logger.debug('fill table: no out')
                                sys.exit(0)
        with analyzer.lock:
            analyzer.clean_progress()

    def row(
        self, 
        s: tuple[str, ...]
    ):
        """Query row(s)
        """
        return tuple(
            self.T[s][e]
            for e in self.E
        )
            
    def is_closed(self):
        """Check closeness of table
        """
        rows = {self.row(s) for s in self.S}

        for s in self.S:
            for a in self.alphabet:
                sa = s + (a,)
                if self.row(sa) not in rows:
                    return False, sa
       
        return True, None

    def make_close(self):
        """Make table close
        """
        logger.debug('Ob: make close')
        while True:
            if self.stop_event.is_set(): return
            closed, sa = self.is_closed()
            if closed or sa == None:
                return
            logger.debug(f'add new prefix: {sa}')
            self.S.add(sa)
            with analyzer.lock:
                analyzer.state += 1
            self._fill_table()

    def is_consistent(self):
        """Check consistent of table
        """
        for s1 in self.S:
            for s2 in self.S:
                if self.row(s1) == self.row(s2):
                    for a in self.alphabet:
                        for e in self.E:
                            if self.T[s1 + (a,)][e] != self.T[s2 + (a,)][e]:
                                logger.debug(f'Ob: inconsistent {'/'.join(s1)} and {'/'.join(s2)}')
                                return False, (s1, s2, a, e)
        return True, None

    def make_consistent(self):
        """Make table consistence
        """
        logger.debug('Ob: make consistent')
        while True:
            if self.stop_event.is_set(): 
                sys.exit(0)
            ok, data = self.is_consistent()
            if ok or data == None:
                return
            s1, s2, a, e = data
            self.E.add((a,) + e)
            self._fill_table()

    def build_hypothesis(
        self,
        id: str
    ):
        """ Construct hypothesis for mealy machine
        """
        states: dict = {}
        sid = 1

        # record unique state and corresponding row in ObTable
        for s in self.S:
            r = self.row(s)
            if r not in states:
                logger.debug(f'unique state: {s}')
                states[r] = sid
                sid += 1

        # state transition function (cur_state, input) -> next_state
        delta: dict[tuple[int, str], int] = {}
        
        # output function (cur_state, input) -> output
        output: dict[tuple[int, str], str] = {}

        # construct transitions
        for r, state_id in states.items():
            s = next(x for x in self.S if self.row(x) == r)
            for a in self.alphabet:
                r2 = self.row(s + (a,))
                delta[(state_id, a)] = states[r2]
                output[(state_id, a)] = ''.join(self.T[s][(a,)])

        start = states[self.row(('-',))]
        return MealyMachine(
            id,
            states=set(states.values()),
            alphabet=set(self.alphabet),
            delta=delta,
            output=output,
            start=start,
            table=(copy.deepcopy(self.S), copy.deepcopy(self.E), copy.deepcopy(self.T))
        )
        
class MealyLstar:
    def __init__(
        self,
        mq,
        eq,
        stop_event: threading.Event,
        table: tuple | None = None
    ) -> None:
        self.mq = mq
        self.eq = eq
        self.stop_event = stop_event
        if table is None:
            self.table = ObTable(self.mq, self.eq, self.stop_event)
            self.table.table_init()
        else:
            self.table = ObTable(self.mq, self.eq, self.stop_event)
            self.table.S = table[0]
            self.table.E = table[1]
            self.table.T = table[2]
    
    def run(
        self,
        id: str
    ):
        try:
            self.table.make_close()
            self.table.make_consistent()
            h = self.table.build_hypothesis(id)
        except Exception as e:
            logger.debug(f'LM: {e}')
            logger.debug(f'{traceback.format_exc()}')
        return h
    
    def havoc_run(
        self,
        id: str
    ):
        """Run mutator to cover edge case and unexpectional condition
        
        id: name of hypothesis
        """
        try:
            # extend mutated alphabet
            additional_symbol = []
            for a in self.table.alphabet:
                additional_symbol.append(f'{a}[m]')
                
            self.table.alphabet += additional_symbol
            for a in additional_symbol:
                self.table.E.add((a,))
            
            # run model learning
            self.table.table_init()
            self.table.make_close()
            self.table.make_consistent()
            h = self.table.build_hypothesis(id)
        except Exception as e:
            logger.debug(f'LM: {e}')
            logger.debug(f'{traceback.format_exc()}')
        return h
    