from voltron.executor.executor import Executor
from voltron.mapper.mapper import Mapper

class EquOracle:
    def __init__(
        self,
        mapper: Mapper,
        executor: Executor
    ) -> None:
        self.mapper = mapper
        self.executor = executor
    
    def query(
        self, 
        word: list[str]
    ):
        generators = self.mapper.select_generators(word)
        flag, cons = self.executor.interact(generators)
        if (flag and cons):
            return cons.content