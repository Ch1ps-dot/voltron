from voltron.executor.executor import Executor
from voltron.executor.conversation import Conversation
from voltron.mapper.mapper import Mapper
from voltron.utils.logger import logger
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
        logger.debug(f'Learner: query {pprint.pformat(word)}')
        generators = self.mapper.select_generators(list(word))
        flag, cons = self.executor.interact(generators)
        if (flag and cons):
            return cons.res_seq
        return None