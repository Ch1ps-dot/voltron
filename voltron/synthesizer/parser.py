from dataclasses import dataclass, asdict, field
@dataclass
class Parser:
    """Generator of request message

    msg_type: message type
    """
    evolved_from: str
    name: str
    parsed_res: list[str] = field(default_factory=list)
    
    # def __post_init__(self):
    #     if self.cur_res is None:
    #         self.cur_res = []