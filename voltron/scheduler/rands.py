from voltron.mapper.mapper import Mapper
from voltron.producer.AsyncProducer import Generator
from voltron.executor.executor import Executor
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
            randkey =random.choice(self.req_types)
            gs.append(self.mapper.generators[randkey][0])
        
        return gs
    
    def run(
        self
    ) -> None:
        gs = self.select(10)
        self.exe.communicate(gs)
        