from voltron.analyzer.analyzer import Analyzer
from voltron.mapper.mapper import Mapper
from voltron.producer.AsyncProducer import Generator, Parser
from voltron.executor.executor import Executor

class MealyMachine:
    def __init__(
        self,
        states,
        alphabet,
        delta,
        output,
        start,
        executor: Executor,
        mapper: Mapper
    ) -> None:
        self.exe = executor
        self.mapper = mapper

    def mem_query(
        self,
        word: str
    ):
        req_seq = word.split('-')
        return self.run(req_seq=req_seq)
    
    def equ_query(
        self
    ):
        pass
    
    def run(
        self,
        req_seq: list[str]
    ):
        gs = self.mapper