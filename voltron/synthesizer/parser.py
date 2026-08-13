from dataclasses import dataclass, field, fields
from typing import Any, Mapping


@dataclass
class Parser:
    """Generator of request message

    msg_type: message type
    """
    evolved_from: str
    name: str
    state_field: str = ''
    parsed_res: list[str] = field(default_factory=list)

    @classmethod
    def from_metadata(cls, metadata: Mapping[str, Any]) -> 'Parser':
        """Build a runtime parser while ignoring persisted-only metadata.

        Model-equipment manifests retain fields such as ``path`` so an
        imported snapshot can locate its source file.  Those fields are not
        part of the runtime parser value object and must not be passed to the
        dataclass constructor.
        """
        allowed = {item.name for item in fields(cls)}
        return cls(**{
            key: value for key, value in metadata.items() if key in allowed
        })
    
    # def __post_init__(self):
    #     if self.cur_res is None:
    #         self.cur_res = []
