from voltron.executor.executor import Executor
from voltron.executor.mapper import Mapper
from voltron.learner.automata import MealyMachine
from collections import deque

class EquOracle:
    """Haven'd been used yet, but can be used to compare two mealy machines and find a distinguishing input sequence if they are not equivalent.
    """
    def __init__(
        self,
        mapper: Mapper,
        executor: Executor
    ) -> None:
        self.mapper = mapper
        self.executor = executor
    
    def query(
        self, 
        word: list[str]
    ):
        generators = self.mapper.select_generators(word)
        flag, cons = self.executor.interact(generators)
        if (flag and cons):
            return cons.content

    def compare_mealy(
        self,
        m1: MealyMachine, 
        m2: MealyMachine
    ):
        """Compare and find inequivelence of two mealy machine.
        """
        visited = set()
        q = deque()
        q.append((m1.start, m2.start, []))

        while q:
            s1, s2, seq = q.popleft()
            if (s1, s2) in visited:
                continue
            visited.add((s1, s2))

            for a in m1.alphabet:
                
                n1 = m1.delta[(s1, a)]
                o1 = m1.output[(s1, a)]
                
                n2 = m2.delta[(s2, a)]
                o2 = m2.output[(s2, a)]

                if o1 != o2:
                    return seq + [a]  # distinguishing input

                q.append((n1, n2, seq + [a]))

        return None  # equivalent
