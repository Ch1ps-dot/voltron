from voltron.configs import configs
from graphviz import Digraph

class MealyMachine:
    """Mealy machine implementation for modeling the sut's behavior.
    
    Attributes:
        id: Identifier for the automaton.
        states: A set of states in the automaton.
        alphabet: A set of input symbols (requests).
        delta: A transition function mapping (state, input) pairs to the next state.
        output: An output function mapping (state, input) pairs to the corresponding output (response).
        start: The initial state of the automaton.
        map: A mapping from request types to their possible responses and corresponding byte representations.
        res_types: A mapping from response types to their appearance counts.
        res_trans_types: A mapping from response transition types to their appearance counts.
        table: A tuple representing the transition table for the automaton. 
    """
    def __init__(
        self,
        id: str,
        states: set[int],
        alphabet: set[str],
        delta: dict[tuple[int, str], int],
        output: dict[tuple[int, str], str],
        start: int,
        table: tuple
    ) -> None:
        self.id = id
        self.states: set[int] = states
        self.alphabet: set[str] = alphabet
        self.delta: dict[tuple[int, str], int] = delta
        self.output: dict[tuple[int, str], str] = output
        self.start: int = start
        self.map: dict[str, dict[str, bytes]] = {}
        self.res_types: dict[str, int] = {}
        self.res_trans_types: dict[str, int] = {}
        self.table = table
    
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
        """Generate a graph representation of the automaton using Graphviz.
        
        Args:
            name: The name to be used for the generated graph file.
        """
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
        """Get the relation between two requests based on the transitions and outputs of the automaton.
        
        Args:
            last_request: The last request made to the system.
            current_request: The current request being analyzed.
            
        Returns:
            A string representation of the relation between the two requests, showing the transitions and outputs for each state in the automaton.
        """
        ans = set()
        for s1 in self.states:
            s2 = self.delta[(s1, last_request)]
            out1 = self.output[(s1, last_request)]
            out2 = self.output[(s2, current_request)]
            ans.add(f'( {last_request} / {out1} )->( {current_request} / {out2} )')
        return '\n'.join(ans)
    
    