from voltron.executor.executor import Executor
from voltron.executor.conversation import Conversation
from voltron.executor.mapper import Mapper
from voltron.utils.logger import logger
from voltron.configs import configs
import pprint

class MembershipOracle:
    """Membership Oracle for querying the SUT with sequences of requests and obtaining the corresponding responses.
    
    Attributes:
        mapper: An instance of Mapper used to select the appropriate generators for the given input sequences.
        executor: An instance of Executor used to interact with the SUT and obtain the conversations (request and response sequences).
        alphabet: A list of input symbols (requests) that can be sent to the SUT, derived from the request types defined in the mapper.
    """
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
        for i in range(3):
            msg_seq = self.mapper.select_generators(list(word), cache_mode=True, select_mode='new')
            flag, cons = self.executor.interact(msg_seq)
            if (flag and cons):
                logger.debug(f'sent seq -> {cons.req_seq}')
                logger.debug(f'recv seq <- {cons.res_seq}')
                return cons.res_seq
        logger.debug('mq: Failed to obtain a valid conversation after 3 attempts for input sequence')
        return None