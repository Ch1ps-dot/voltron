from voltron.executor.executor import Executor
from voltron.executor.mapper import Mapper
from voltron.analyzer.analyzer import analyzer
from voltron.learner.automata import MealyMachine
from voltron.scheduler.seed_retention import SeedRetentionPolicy
from collections import deque

class EquOracle:
    """Haven'd been used yet, but can be used to compare two mealy machines and find a distinguishing input sequence if they are not equivalent.
    """
    def __init__(
        self,
        mapper: Mapper,
        executor: Executor,
        seed_retention: SeedRetentionPolicy | None = None,
    ) -> None:
        self.mapper = mapper
        self.executor = executor
        self.seed_retention = seed_retention or SeedRetentionPolicy()
    
    def query(
        self, 
        word: list[str]
    ):
        generators = self.mapper.select_generators(word)
        with analyzer.lock:
            previous_response_types = analyzer.res_types_num()
            previous_transitions = analyzer.resp_trans_num()
        flag, cons = self.executor.interact(generators)
        if (flag and cons):
            with analyzer.lock:
                response_type_increment = (
                    analyzer.res_types_num() - previous_response_types
                )
                transition_increment = (
                    analyzer.resp_trans_num() - previous_transitions
                )
            novelty = self.seed_retention.observe(
                cons,
                transition_increment,
                response_type_increment,
            )
            if novelty.interesting:
                self.executor.save_cons(cons)
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
