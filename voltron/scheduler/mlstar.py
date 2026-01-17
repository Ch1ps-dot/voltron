from voltron.mapper.mapper import Mapper
from voltron.producer.AsyncProducer import Generator, Parser
from voltron.scheduler.automata import MealyMachine
from voltron.scheduler.EquOracle import EquOracle
from voltron.scheduler.MembOracle import MembershipOracle
from voltron.utils.logger import logger
from voltron.configs import configs
from voltron.analyzer.analyzer import analyzer
import pprint, pickle, threading, sys, traceback


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
            analyzer.stage = f'init model learning'
        self._fill_table()

    def _fill_table(self):
        iter_s = 0
        logger.debug('Ob: fill table')
        with analyzer.lock:
            analyzer.show_progress = True

        for s in self.S:
            iter_s += 1
            # with analyzer.lock:
                # analyzer.prefix = f'({iter_s}/{len(self.S)}) {'/'.join(s)}'
            
            # iter_e = 0
            for e in self.E:
                if s not in self.T.keys():
                    self.T[s] = {}
                if e not in self.T[s].keys():
                    
                    if self.stop_event.is_set(): sys.exit(0)
                    
                    # iter_e += 1                   
                    out = self.mq.query(s + e)
                    if (out):
                        with analyzer.lock:
                            analyzer.sent = f'{'/'.join(s)}:{'/'.join(s)} ({iter_s}/{len(self.S)})'
                            analyzer.recv = f'{'/'.join(out)}'
                        self.T[s][e] = tuple(out[-len(e):])

        iter_s = 0
        with analyzer.lock:
            analyzer.show_progress = True         
        for s in self.S:
            for a in self.alphabet:
                iter_s += 1
                si = s + (a,) # S + i (element in alphabet)
                # with analyzer.lock:
                #     analyzer.prefix = f'({iter_s}/{len(self.S) * len(self.alphabet)}) {'/'.join(s)}'
                if si not in self.T.keys():
                    self.T[si] = {}
                    
                for e in self.E:
                    
                    if self.stop_event.is_set(): sys.exit(0)
                            
                    # connection was closed before sending suffix request
                    # in this situation, there is no more response and destroy the evaluation
                    # so we consider they are same state and jump the query
                    if(self.T[s][(a,)] == ('POLLERR',)):
                        self.T[si][e] = ('POLLERR',)
                        continue
                    
                    if e not in self.T[si].keys():
                    
                        out = self.mq.query(si + e)
                        if (out):
                            with analyzer.lock:
                                analyzer.sent = f'{'/'.join(si)}:{'/'.join(e)} ({iter_s}/{len(self.S)})'
                                analyzer.recv = f'{'/'.join(out)}'
                            self.T[si][e] = tuple(out[-len(e):])
                            # logger.debug(f'Ob: {si} + {e} = {tuple(out[-len(e):])} ')
        with analyzer.lock:
            analyzer.show_progress = False

    def row(
        self, 
        s: tuple[str, ...]
    ):
        return tuple(
            self.T[s][e]
            for e in self.E
        )

    # ---------- Closed ----------
    def is_closed(self):
        rows = {self.row(s) for s in self.S}
        for s in self.S:
            for a in self.alphabet:
                sa = s + (a,)
                if self.row(sa) not in rows:
                    return False, sa
        return True, None

    def make_close(self):
        with analyzer.lock:
            analyzer.stage = f'make close'
        logger.debug('Ob: make close')
        while True:
            if self.stop_event.is_set(): return
            closed, sa = self.is_closed()
            if closed or sa == None:
                return
            logger.debug(f'add new suffix: {sa}')
            self.S.add(sa)
            self._fill_table()

    # ---------- Consistent ----------
    def is_consistent(self):
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
        with analyzer.lock:
            analyzer.stage = f'make consistent'
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

    # ---------- Hypothesis ----------
    def build_hypothesis(self):
        states: dict = {}
        sid = 1

        for s in self.S:
            r = self.row(s)
            if r not in states:
                logger.debug(f'unique state: {s}')
                states[r] = sid
                sid += 1

        delta: dict[tuple[int, str], int] = {}
        output: dict[tuple[int, str], str] = {}

        for r, state_id in states.items():
            s = next(x for x in self.S if self.row(x) == r)
            for a in self.alphabet:
                r2 = self.row(s + (a,))
                delta[(state_id, a)] = states[r2]
                output[(state_id, a)] = ''.join(self.T[s][(a,)])

        start = states[self.row(('-',))]
        return MealyMachine(
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
        self.table = ObTable(mq, eq, stop_event)
        self.stop_event = stop_event
    
    def run(
        self
    ):
        try:
            self.table.make_close()
            self.table.make_consistent()
            h = self.table.build_hypothesis()
            with open(configs.results_path / 'model.pkl', 'wb') as f:
                pickle.dump(h, f)
            h.graph()
            self.stop_event.set()
        except Exception as e:
            logger.debug(f'LM: {e}')
            logger.debug(f'{traceback.format_exc()}')
        return h