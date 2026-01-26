from voltron.mapper.mapper import Mapper
from voltron.producer.AsyncProducer import Generator, Parser
from voltron.scheduler.automata import MealyMachine
from voltron.scheduler.EquOracle import EquOracle
from voltron.scheduler.MembOracle import MembershipOracle
from voltron.utils.logger import logger
from voltron.configs import configs
from voltron.analyzer.analyzer import analyzer
import pprint, pickle, threading, sys, traceback, time


class ObTable:
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
        
        with analyzer.lock:
            analyzer.stage = f'init ObTable'
        self._fill_table()

    def _fill_table(self):
        
        iter_s = 0
        logger.debug('Ob: fill table')
        with analyzer.lock:
            analyzer.set_progress('Obtable', desc='fill s table', total=1)

        # fill (s, e) table entry
        for s in self.S:
            
            iter_s += 1
            
            for e in self.E:
                if s not in self.T.keys():
                    self.T[s] = {}
                if e not in self.T[s].keys():
                    
                    if (configs.time_limit_s < time.time() - analyzer.start_time):
                        self.stop_event.set()
                        logger.debug('Fuzzer: timeout')
                    if self.stop_event.is_set(): 
                        sys.exit(0)
                                    
                    out = self.mq.query(s + e)
                    if (out):
                        with analyzer.lock:
                            analyzer.sent = f'{'/'.join(s)}:{'/'.join(e)} ({iter_s}/{len(self.S)})'
                            analyzer.recv = f'{'/'.join(out)}'
                        self.T[s][e] = tuple(out[-len(e):])

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
                        self.stop_event.set()
                        logger.debug('Fuzzer: timeout')
                        
                    if self.stop_event.is_set(): 
                        sys.exit(0)
                    
                    # connection was closed before sending suffix request
                    # in this situation, there is no more response and destroy the evaluation
                    # so we just consider they are transfering to same state and jump the query
                    if e not in self.T[si].keys():
                        if(self.T[s][(a,)] == ('CLOSED',)):
                            self.T[si][e] = ('CLOSED',)
                            continue
                        if(self.T[s][(a,)] == ('CRASH',)):
                            self.T[si][e] = ('CRASH',)
                            continue
                        if(self.T[s][(a,)] == ('TIMEOUT',)):
                            self.T[si][e] = ('TIMEOUT',)
                            continue
                        
                        while(True):
                            out = self.mq.query(si + e)
                            if (out):
                                # sometimes the randomness of server will cause timeout
                                # when output is inconsistent with previous results, just try again
                                if len(si) > 0:
                                    if 'TIMEOUT' == out[-1] and len(out) < len(si):
                                        logger.debug('fill table: try again')
                                        continue
                                
                                with analyzer.lock:
                                    analyzer.sent = f'{'/'.join(s)}:{a}:{'/'.join(e)} ({iter_si}/{len(self.S) * len(self.alphabet) * len(self.E)})'
                                    analyzer.recv = f'{'/'.join(out)}'
                                self.T[si][e] = tuple(out[-len(e):])
                                break
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
        id: int
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
            start=start
        )
        
class MealyLstar:
    def __init__(
        self,
        mq,
        eq,
        stop_event: threading.Event
    ) -> None:
        self.mq = mq
        self.eq = eq
        self.stop_event = stop_event
        self.table = ObTable(self.mq, self.eq, self.stop_event)
    
    def run(
        self,
        id: int
    ):
        try:
            with analyzer.lock:
                analyzer.stage = f'make close'
            self.table.make_close()
            with analyzer.lock:
                analyzer.stage = f'make consistent'
            self.table.make_consistent()
            h = self.table.build_hypothesis(id)
        except Exception as e:
            logger.debug(f'LM: {e}')
            logger.debug(f'{traceback.format_exc()}')
        return h
    
    def havoc_run(
        self,
        id: int
    ):
        try:
            # extend mutated alphabet
            self.table.alphabet
            with analyzer.lock:
                analyzer.stage = f'[havoc] make close'
            self.table.make_close()
            with analyzer.lock:
                analyzer.stage = f'[havoc] make consistent'
            self.table.make_consistent()
            h = self.table.build_hypothesis(id)
        except Exception as e:
            logger.debug(f'LM: {e}')
            logger.debug(f'{traceback.format_exc()}')
        return h
    