from voltron.analyzer.analyzer import Analyzer
from voltron.mapper.mapper import Mapper
from voltron.producer.AsyncProducer import Generator, Parser
from voltron.executor.executor import Executor
from voltron.configs import configs
from graphviz import Digraph

class MealyMachine:
    def __init__(
        self,
        states,
        alphabet,
        delta,
        output,
        start
    ) -> None:
        self.states: dict[tuple[tuple[str,...],...], int] = states
        self.alphabet: set[str] = alphabet
        self.delta: dict[tuple[int, str], int] = delta
        self.output: dict[tuple[int, str], str] = output
        self.start: int = start
    
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
    
    def graph(
        self
    ):
        g = Digraph(comment='automata')
        for sid in self.states.values():
            g.node(str(sid), str(sid))
        for k, v in self.delta.items():
            g.edge(str(k[0]), str(v), label=f'{k[1]}/{self.output[k]}')
                     
        g.save(
            filename='model',
            directory=configs.results_path
        )