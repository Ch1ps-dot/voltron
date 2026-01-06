from voltron.sheduler.alphabet import Symbol, Alphabet
import random

random.seed(42)

class Rands:
    def __init__(
            self,
            alphabet: Alphabet
    ) -> None:
        self.al = alphabet
        self.ins = alphabet.input_symbols
        self.outs = alphabet.output_symbols

    def select(
            self,
            num:int
    ) -> list[Symbol]:
        s = []
        for i in range(num):
            randkey =random.choice(list(self.ins.keys()))
            s.append(self.ins[randkey])
        
        return s