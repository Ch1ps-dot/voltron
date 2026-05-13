from dataclasses import dataclass, asdict, field
@dataclass
class Generator:
    """Generator of request message

    msg_type: message type
    name: name of the generator
    path: the path of the generator, used to locate the generator
    other atributes haved been used
    """
    msg_type: str
    name: str
    evolved_from: str
    path: str
    cur_res: list[str] = field(default_factory=list)
    pre_res: list[str] = field(default_factory=list)
    fut_res: list[str] = field(default_factory=list)
    was_used: int = 0
    broken: bool = True
    
    # def __post_init__(self):
    #     if self.cur_res is None:
    #         self.cur_res = []
    #     if self.pre_res is None:
    #         self.pre_res = []
    #     if self.fut_res is None:
    #         self.fut_res = []