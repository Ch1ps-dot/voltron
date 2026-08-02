from dataclasses import dataclass, field


@dataclass
class Checker:
    """Generated response conformance checker metadata."""

    msg_type: str
    evolved_from: str
    name: str
    path: str
    state_field: str = ''
    contract_version: str = ''
    ir_sha256: str = ''
    checked_res: list[str] = field(default_factory=list)
