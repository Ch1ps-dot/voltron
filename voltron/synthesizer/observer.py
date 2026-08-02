from dataclasses import dataclass, field


@dataclass
class ResponseObserver:
    """Generated response semantic observer metadata."""

    msg_type: str
    name: str
    path: str
    state_field: str = ''
    contract_version: str = ''
    ir_sha256: str = ''
    evolved_from: str = 'init'
    sample_observations: list[str] = field(default_factory=list)
