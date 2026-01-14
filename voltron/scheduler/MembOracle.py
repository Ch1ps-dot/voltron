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
        word: str
    ) -> str | None:
        req_seq = word.split('/')
        generators = self.mapper.select_generators(req_seq)
        flag, cons = self.executor.interact(generators)
        if (flag and cons):
            if cons.req_res_pair[-1][1]:
                return cons.req_res_pair[-1][1]
        return None