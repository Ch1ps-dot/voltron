from voltron.mapper.mapper import Mapper
from voltron.producer.AsyncProducer import Generator
from voltron.executor.executor import Executor, Conversation
from voltron.analyzer.analyzer import analyzer
from voltron.scheduler.automata import MealyMachine
import random, time

random.seed(time.time())

class Havoc:
    def __init__(
        self,
        mapper: Mapper,
        exe: Executor,
        machine: MealyMachine
    ) -> None:
        self.res_trans_types: dict[str, int] = {}
        self.mapper = mapper
        self.exe = exe
        self.alphabet = []
        for msg_type in mapper.mutators.keys():
            self.alphabet.append(msg_type)
        if machine:
            self.machine = machine
            self.table = machine.table
            self.S = self.table[0]
            self.E = self.table[1]
        else:
            self.machine = None

    def select_prefix(
        self
    ) -> list[tuple[str, bytes]]:
        p = random.choice(self.S)
        w = list(p)
        gs = self.mapper.select_generators(w)
        return gs
    
    def select_mutators(
        self
    ) -> list[tuple[str, bytes]]:
        scope = random.randint(1, 10)
        for i in range(scope):
            req_type = random.choice(self.alphabet)
        ms = self.mapper.select_generators(req_type)
        return ms
    
    def run(
        self,
        times: int
    ):
        for i in range(times):
            ms = self.select_mutators()
            flag, cons = self.exe.interact(ms)
            res_types = analyzer.res_types_num()
            res_trans_types = analyzer.resp_trans_num()
            if flag and self.is_interesting(cons) and cons != None:
                cons.save_cons()
        
    def is_interesting(
        self,
        cons: Conversation | None
    ) -> bool:
        if (cons):
            return True
        else:
            return False