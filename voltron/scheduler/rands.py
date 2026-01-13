from voltron.mapper.mapper import Mapper
from voltron.producer.AsyncProducer import Generator
from voltron.executor.executor import Executor, Conversation
import random, time

random.seed(time.time())

class Rands:
    def __init__(
        self,
        mapper: Mapper,
        executor: Executor,
    ) -> None:
        self.mapper = mapper
        self.req_types = mapper.req_types
        self.exe: Executor = executor

    def select(
        self,
        num:int
    ) -> list[Generator]:
        gs = []
        for i in range(num):
            req_type =random.choice(self.req_types)
            gs.append(self.mapper.select_generator(req_type))
        return gs
    
    def run(
        self
    ) -> None:
        gs = self.select(10)
        _, cons = self.exe.interact(gs)
        if(self.is_interesting(cons) and cons):
            self.exe.save_cons(cons)
        
    def is_interesting(
        self,
        cons: Conversation | None
    ) -> bool:
        if (cons):
            return True
        else:
            return False