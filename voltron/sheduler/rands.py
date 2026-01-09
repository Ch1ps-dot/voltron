from voltron.sheduler.mapper import InputSymbol, Mapper
import random, time

random.seed(time.time())

class Rands:
    def __init__(
            self,
            mapper: Mapper
    ) -> None:
        self.mapper = mapper
        self.ins = mapper.input_symbols
        self.outs = mapper.output_symbols

    def select(
            self,
            num:int
    ) -> list[InputSymbol]:
        s = []
        for i in range(num):
            randkey =random.choice(list(self.ins.keys()))
            s.append(self.ins[randkey])
        
        return s