from dataclasses import dataclass, field


@dataclass
class ResponseObserver:
    """Generated response semantic observer metadata."""

    msg_type: str
    name: str
    path: str
    state_field: str = ''
    evolved_from: str = 'init'
    sample_hashes: list[str] = field(default_factory=list)
