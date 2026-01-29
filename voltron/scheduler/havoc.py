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
        req_types = []
        for i in range(scope):
            req_types.append(random.choice(self.alphabet))
        ms = self.mapper.select_generators(req_types)
        return ms
    
    def run(
        self,
        times: int
    ):
        for i in range(times):
            
            last_resp_num = analyzer.res_types_num()
            last_trans_nums = analyzer.resp_trans_num()
            
            prefix = self.select_prefix()
            ms = self.select_mutators()
            req_seq = ms + prefix
            flag, cons = self.exe.interact(req_seq, poll_wait_ms=1000)
            
            cur_trans_nums = analyzer.resp_trans_num()
            cur_resp_num = analyzer.res_types_num()
            if flag and self.is_interesting(cur_trans_nums - last_trans_nums, cur_resp_num - last_resp_num) and cons != None:
                cons.save_cons()
        
    def is_interesting(
        self,
        trans_inc: int,
        type_inc: int
    ) -> bool:
        if trans_inc > 0 or type_inc > 0:
            return True
        else:
            return False