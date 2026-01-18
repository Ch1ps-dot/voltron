from voltron.executor.executor import Executor
from voltron.executor.conversation import Conversation
from voltron.mapper.mapper import Mapper
from voltron.utils.logger import logger
from voltron.configs import configs
import pprint

class MembershipOracle:
    def __init__(
        self,
        mapper: Mapper,
        executor: Executor
    ) -> None:
        self.mapper = mapper
        self.executor = executor
        self.alphabet = mapper.request_types
    
    def query(
        self, 
        word: tuple[str,...]
    ) -> list[str] | None:
        
        msg_seq = self.mapper.select_generators(list(word), True)
        flag, cons = self.executor.interact(msg_seq)
        if (flag and cons):
            return cons.res_seq
        return None