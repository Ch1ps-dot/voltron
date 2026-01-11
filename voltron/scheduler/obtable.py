from voltron.mapper.mapper import Mapper
from voltron.producer.AsyncProducer import Generator, Parser
from voltron.scheduler.automata import MealyMachine

class ObTable:
    def __init__(
        self,
        mapper: Mapper,
        automata: MealyMachine
    ) -> None:
        self.alphabet = mapper.req_types # request symbol
        
        self.S = {''} # prefix of request symbols
        self.E = {''} # suffix of request symbols
        
        self.T = {} # (s, a, e) -> output. Transition
        
        self.automata = automata
        
        self._fill_table()

    def _fill_table(self):
        for s in self.S:
            for a in self.alphabet:
                for e in self.E:
                    key = (s, a, e)
                    if key not in self.T:
                        out = self.automata.mem_query(s + a + e)[len(s)]
                        self.T[key] = out

    def row(self, s):
        return tuple(
            self.T[(s, a, e)]
            for a in self.alphabet
            for e in self.E
        )

    # ---------- Closed ----------
    def is_closed(self):
        rows = {self.row(s) for s in self.S}
        for s in list(self.S):
            for a in self.alphabet:
                sa = s + a
                if self.row(sa) not in rows:
                    return False, sa
        return True, None

    def close(self):
        while True:
            closed, sa = self.is_closed()
            if closed:
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
                            if self.T[(s1, a, e)] != self.T[(s2, a, e)]:
                                return False, s1, s2, a, e
        return True, None

    def make_consistent(self):
        while True:
            ok, data = self.is_consistent()
            if ok:
                return
            s1, s2, a, e = data
            self.E.add(a + e)
            self._fill_table()

    # ---------- Hypothesis ----------
    def build_hypothesis(self):
        states = {}
        sid = 0

        for s in self.S:
            r = self.row(s)
            if r not in states:
                states[r] = sid
                sid += 1

        delta = {}
        output = {}

        for r, state_id in states.items():
            s = next(x for x in self.S if self.row(x) == r)
            for a in self.alphabet:
                r2 = self.row(s + a)
                delta[(state_id, a)] = states[r2]
                output[(state_id, a)] = self.T[(s, a, "")]

        start = states[self.row("")]
        return MealyMachine(
            states=set(states.values()),
            alphabet=self.alphabet,
            delta=delta,
            output=output,
            start=start
        )