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
        self.alphabet = list(mapper.request_types)
    
    def query(
        self, 
        word: tuple[str,...]
    ) -> list[str] | None:
        msg_seq = self.mapper.select_generators(list(word), cache_mode=True, select_mode='new')
        flag, cons = self.executor.interact(msg_seq)
        if (flag and cons):
            logger.debug(f'sent seq -> {cons.req_seq}')
            logger.debug(f'recv seq <- {cons.res_seq}')
            return cons.res_seq
        return None