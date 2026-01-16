from voltron.mapper.mapper import Mapper
from voltron.producer.AsyncProducer import Generator, Parser
from voltron.scheduler.automata import MealyMachine
from voltron.scheduler.EquOracle import EquOracle
from voltron.scheduler.MembOracle import MembershipOracle
from voltron.utils.logger import logger
from voltron.configs import configs
from voltron.analyzer.analyzer import analyzer
import pprint, pickle


class ObTable:
    def __init__(
        self,
        mq: MembershipOracle,
        eq: EquOracle
    ) -> None:
        self.alphabet: list[str] = mq.alphabet # request symbol
        
        self.S: set[tuple[str,...]] = {('',)} # prefix of request symbols
        self.E: set[tuple[str,...]] = {(a,) for a in self.alphabet} # suffix of request symbols
        
        self.T: dict[tuple[str,...], dict[tuple[str,...], tuple[str,...]]] = {} # (s, a, e) -> output. Transition
        
        self.mq = mq
        self.eq = eq
        
        self._fill_table()

    def _fill_table(self):
        iter = 0
        for s in self.S:
            iter += 1
            with analyzer.lock:
                analyzer.stage = f'fill s table: {iter}/{len(s)}'
            for e in self.E:
                if s not in self.T.keys():
                    self.T[s] = {}
                if e not in self.T[s].keys():
                    # with open(configs.results_path / 'ml', 'a', encoding='utf-8') as f:
                    #     f.write(f'--Query--\ns: {s}\ne: {e}\n')
                    with analyzer.lock:
                        analyzer.mq = f'{' '.join(s)}//{' '.join(e)}'
                    out = self.mq.query(s + e)
                    if (out):
                        with analyzer.lock:
                            analyzer.out = f'{' '.join(out)}'
                        self.T[s][e] = tuple(out[-len(e):])
                       
        iter = 0                
        for s in self.S:
            for a in self.alphabet:
                with analyzer.lock:
                    iter += 1
                    analyzer.stage = f'fill si table: {iter}/{len(s)*len(self.alphabet)}'
                for e in self.E:
                    si = s + (a,) # S + i (element in alphabet)
                    if si not in self.T.keys():
                        self.T[si] = {}
                    if e not in self.T[si].keys():
                        # with open(configs.results_path / 'ml', 'a', encoding='utf-8') as f:
                        #     f.write(f'--Query--\ns: {si} e: {e}\n')
                        with analyzer.lock:
                            analyzer.mq = f'{' '.join(si)}//{' '.join(e)}'
                        out = self.mq.query(si + e)
                        if (out):
                            with analyzer.lock:
                                analyzer.out = f'{' '.join(out)}'
                            self.T[si][e] = tuple(out[-len(e):])

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
        while True:
            closed, sa = self.is_closed()
            if closed or sa == None:
                return
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
                                return False, (s1, s2, a, e)
        return True, None

    def make_consistent(self):
        while True:
            ok, data = self.is_consistent()
            if ok or data == None:
                return
            s1, s2, a, e = data
            self.E.add((a,) + e)
            self._fill_table()

    # ---------- Hypothesis ----------
    def build_hypothesis(self):
        states: dict[tuple[tuple[str,...],...], int] = {(('',),): 0}
        sid = 1

        for s in self.S:
            r = self.row(s)
            if r not in states:
                logger.debug(r)
                states[r] = sid
                sid += 1

        delta: dict[tuple[int, str], int] = {}
        output: dict[tuple[int, str], str] = {}

        for r, state_id in states.items():
            s = next(x for x in self.S if self.row(x) == r)
            for a in self.alphabet:
                r2 = self.row(s + (a,))
                delta[(state_id, a)] = states[r2]
                output[(state_id, a)] = str(self.T[s][(a,)])

        start = states[self.row(('',))]
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
        eq
    ) -> None:
        self.table = ObTable(mq, eq)
    
    def run(
        self
    ):
        self.table.make_close()
        self.table.make_consistent()
        h = self.table.build_hypothesis()
        with open(configs.results_path / 'model.pkl', 'wb') as f:
            pickle.dump(h, f)
        return h