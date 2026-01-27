from voltron.configs import configs
from graphviz import Digraph

class MealyMachine:
    def __init__(
        self,
        id: str,
        states: set[int],
        alphabet: set[str],
        delta: dict[tuple[int, str], int],
        output: dict[tuple[int, str], str],
        start: int,
    ) -> None:
        self.id = id
        self.states: set[int] = states
        self.alphabet: set[str] = alphabet
        self.delta: dict[tuple[int, str], int] = delta
        self.output: dict[tuple[int, str], str] = output
        self.start: int = start
        self.map: dict[str, bytes] = {}
        self.res_types: dict[str, int] = {}
        self.res_trans_types: dict[str, int] = {}
    
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
        self,
        name
    ):
        g = Digraph(comment='automata')
        for sid in self.states:
            g.node(str(sid), str(sid))
        for k, v in self.delta.items():
            g.edge(str(k[0]), str(v), label=f'{k[1]}/{self.output[k]}')
                     
        g.save(
            filename=f'automata_{name}',
            directory=configs.results_path
        )
        
    def get_relation(
        self,
        last_request,
        current_request
    ):
        ans = []
        for s1 in self.states:
            s2 = self.delta[(s1, last_request)]
            out1 = self.output[(s1, last_request)]
            out2 = self.output[(s2, current_request)]
            ans.append(f'( {last_request} / {out1} )->( {current_request} / {out2} )')
        return '\n'.join(ans)
    
    