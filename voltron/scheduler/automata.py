from voltron.analyzer.analyzer import Analyzer
from voltron.mapper.mapper import Mapper
from voltron.producer.AsyncProducer import Generator, Parser

class MealyMachine:
    def __init__(
        self,
        states,
        alphabet,
        delta,
        output,
        start,
        executor
    ) -> None:
        pass

    def mem_query(
        self,
        word: str
    ):
        req_seq = word.split('-')
        return self.run
    
    def equ_query(
        self
    ):
        pass
    
    def run(
        self,
        req_seq: list[str]
    ):
        pass