from voltron.executor.executor import Executor
from voltron.executor.conversation import Conversation
from voltron.executor.mapper import Mapper
from voltron.analyzer.analyzer import analyzer
from voltron.scheduler.seed_retention import SeedRetentionPolicy
from voltron.utils.logger import logger_fuzz as logger
from voltron.configs import configs
import pprint
from voltron.learner.partial_guidance import (
    ModelLearningThreshold,
    PartialTraceRecorder,
)

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
        executor: Executor,
        seed_retention: SeedRetentionPolicy | None = None,
        trace_recorder: PartialTraceRecorder | None = None,
        threshold_tracker: ModelLearningThreshold | None = None,
    ) -> None:
        self.mapper = mapper
        self.executor = executor
        self.alphabet = list(mapper.request_types)
        self.seed_retention = seed_retention or SeedRetentionPolicy()
        self.trace_recorder = trace_recorder
        self.threshold_tracker = threshold_tracker
    
    def query(
        self, 
        word: tuple[str,...]
    ) -> list[str] | None:
        for i in range(3):
            msg_seq = self.mapper.select_generators(list(word), cache_mode=True, select_mode='new')
            with analyzer.lock:
                previous_response_types = analyzer.res_types_num()
                previous_transitions = analyzer.resp_trans_num()
            flag, cons = self.executor.interact(msg_seq)
            if (flag and cons):
                with analyzer.lock:
                    response_type_increment = (
                        analyzer.res_types_num() - previous_response_types
                    )
                    transition_increment = (
                        analyzer.resp_trans_num() - previous_transitions
                    )
                novelty = self.seed_retention.observe(
                    cons,
                    transition_increment,
                    response_type_increment,
                )
                if novelty.interesting:
                    self.executor.save_cons(cons)
                if self.trace_recorder is not None:
                    pair_grew = self.trace_recorder.observe(cons)
                    if self.threshold_tracker is not None:
                        self.threshold_tracker.observe(
                            self.trace_recorder,
                            pair_grew,
                        )
                logger.debug(f'sent seq -> {cons.req_seq}')
                logger.debug(f'recv seq <- {cons.res_seq}')
                return cons.res_seq
        logger.debug('mq: Failed to obtain a valid conversation after 3 attempts for input sequence')
        return None
