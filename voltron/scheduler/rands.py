from voltron.mapper.mapper import Mapper
from voltron.producer.AsyncProducer import Generator
import random, time

random.seed(time.time())

class Rands:
    def __init__(
            self,
            mapper: Mapper
    ) -> None:
        self.mapper = mapper
        self.req_types = mapper.req_types

    def select(
            self,
            num:int
    ) -> list[Generator]:
        gs = []
        for i in range(num):
            randkey =random.choice(self.req_types)
            gs.append(self.mapper.generators[randkey][0])
        
        return gs