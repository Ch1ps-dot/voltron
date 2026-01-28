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
        self.mapper = mapper
        self.exe = exe
        self.alphabet = []
        for msg_type in mapper.mutators.keys():
            self.alphabet.append(msg_type)
        if machine:
            self.machine = machine
        else:
            self.machine = None

    def select(
        self
    ) -> list[tuple[str, bytes]]:
        ms = []
        scope = random.randint(1, 10)
        for i in range(scope):
            req_type =random.choice(self.alphabet)
        ms = self.mapper.select_generators(req_type)
        return ms
    
    def run(
        self,
        times: int
    ):
        for i in range(times):
            ms = self.select()
            flag, cons = self.exe.interact(ms)
            res_types = analyzer.cur_res_types_cnt
            res_trans_types = analyzer.cur_resp_trans_cnt
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