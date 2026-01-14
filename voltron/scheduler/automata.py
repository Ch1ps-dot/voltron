from voltron.analyzer.analyzer import Analyzer
from voltron.mapper.mapper import Mapper
from voltron.producer.AsyncProducer import Generator, Parser
from voltron.executor.executor import Executor

class MealyMachine:
    def __init__(
        self,
        states,
        alphabet,
        delta,
        output,
        start
    ) -> None:
        self.states = states
        self.alphabet = alphabet
        self.delta = delta
        self.output = output
        self.start = start
    
    def run(
        self, 
        word: str
    ):
        state = self.start
        outputs = []
        for a in word:
            outputs.append(self.output[(state, a)])
            state = self.delta[(state, a)]
        return outputs