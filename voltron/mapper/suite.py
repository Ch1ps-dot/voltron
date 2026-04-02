from voltron.producer.producer import Generator, Parser

"""TODO: maybe use this class to manage generator
"""
class Suite:
    def __init__(
        self,
        gs: dict[str, list[Generator]]
    ) -> None:
        self.gs = gs
        
    def order_list(
        self,
        num: int
    ) -> dict[str, Generator]:
        g: dict[str, Generator] = {}
        for g_type, list in self.gs.items():
            g[g_type] = list[num]
        return g