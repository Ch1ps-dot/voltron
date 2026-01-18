from voltron.producer.AsyncProducer import Generator, Parser

class Suite:
    def __init__(
        self,
        gs: dict[str, Generator]
    ) -> None:
        self.gs: dict[str, Generator] = {}