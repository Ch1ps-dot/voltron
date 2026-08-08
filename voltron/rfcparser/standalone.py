from dataclasses import dataclass
from pathlib import Path

from voltron.configs import configs
from voltron.config_loader import load_runtime_config
from voltron.llm.chatter import AsyncChater
from voltron.rfcparser.rfc_parser import AsyncRFCParser


@dataclass(frozen=True)
class SectionTreeParseResult:
    rfc_name: str
    output_path: Path
    source: str


def _configure_rfc_parser(target_name: str) -> None:
    """Load only the configuration required by the RFC parser."""
    config_dir = configs.base_path / 'config'
    config_path = config_dir / 'configs.yaml'
    config_data = load_runtime_config(config_dir)

    if not isinstance(config_data, dict):
        raise ValueError(f'invalid configuration mapping: {config_path}')
    target = config_data.get(target_name)
    if not isinstance(target, dict):
        raise ValueError(f'unknown target: {target_name}')

    protocol = target.get('protocol')
    rfc_names = target.get('rfc_name')
    llm_doc = config_data.get('llm_doc')
    if not isinstance(protocol, str) or not protocol:
        raise ValueError(f'target {target_name} has no protocol')
    if (
        not isinstance(rfc_names, list)
        or not rfc_names
        or not all(isinstance(name, str) and name for name in rfc_names)
    ):
        raise ValueError(f'target {target_name} has no valid RFC list')
    if not isinstance(llm_doc, dict):
        raise ValueError('missing llm_doc configuration')

    required_llm_fields = ('base_url', 'api_key', 'model', 'async_sem')
    missing_fields = [
        field for field in required_llm_fields if field not in llm_doc
    ]
    if missing_fields:
        raise ValueError(
            'llm_doc configuration is missing: '
            + ', '.join(missing_fields)
        )

    configs.target_name = target_name
    configs.pro_name = protocol
    configs.rfc_name = list(rfc_names)
    configs.doc_paths = [
        configs.base_path / 'config' / 'rfcs' / f'{name}.txt'
        for name in rfc_names
    ]
    configs.pmp_path = configs.base_path / 'skills'
    configs.base_url_doc = str(llm_doc['base_url'])
    configs.api_key_doc = str(llm_doc['api_key'])
    configs.model_doc = str(llm_doc['model'])
    configs.async_sem_doc = int(llm_doc['async_sem'])


def parse_target_section_trees(
    target_name: str,
) -> list[SectionTreeParseResult]:
    """Parse one target's configured RFC documents without starting a fuzzer."""
    _configure_rfc_parser(target_name)
    chater = AsyncChater(
        configs.base_url_doc,
        configs.api_key_doc,
        configs.model_doc,
    )
    parser = AsyncRFCParser(chater=chater)
    parsed = parser.parse_section_trees()
    return [
        SectionTreeParseResult(
            rfc_name=name,
            output_path=parser.tree_path / f'{name}.pkl',
            source=source,
        )
        for name, source in parsed
    ]


def generate_target_ir(target_name: str) -> Path:
    """Parse one target's RFC documents and generate its protocol IR."""
    _configure_rfc_parser(target_name)
    chater = AsyncChater(
        configs.base_url_doc,
        configs.api_key_doc,
        configs.model_doc,
    )
    parser = AsyncRFCParser(chater=chater)
    parser.run()
    return parser.ir_path
