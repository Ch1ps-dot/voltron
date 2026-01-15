from voltron.executor.executor import Executor
from voltron.executor.conversation import Conversation
from voltron.mapper.mapper import Mapper

class MembershipOracle:
    def __init__(
        self,
        mapper: Mapper,
        executor: Executor
    ) -> None:
        self.mapper = mapper
        self.executor = executor
        self.alphabet = mapper.res_types
    
    def query(
        self, 
        word: tuple[str,...]
    ) -> list[str] | None:
        generators = self.mapper.select_generators(list(word))
        flag, cons = self.executor.interact(generators)
        if (flag and cons):
            return cons.res_seq
        return None