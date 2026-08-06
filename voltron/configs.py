import yaml
from pathlib import Path
from voltron.utils.logger import logger_fuzz as logger

class Config:
    def __init__(self) -> None:
        self.base_path: Path
        self.info_path: Path
        self.run_script: Path
        self.setup_script: Path
        self.readiness_script: Path | None = None
        self.readiness_adapter: str = ''
        self.setup_timeout_s: float = 30.0
        self.readiness_timeout_s: float = 5.0
        self.port_release_timeout_s: float = 3.0
        self.models_path: Path
        self.doc_paths: list[Path] = []
        self.pmp_path: Path
        self.results_path: Path
        self.cov_setup_path: Path
        self.cov_collect_path: Path
        self.fuzz_mode: str
        self.spec_knowledge: bool = True
        self.state_learning: bool = True
        self.guided_scheduling: bool = True
        self.compliance_analysis: bool = True
        self.observer_enabled: bool = True
        self.ir_evolution_enabled: bool = True
        self.ir_evolution_failure_threshold: int = 3
        self.ir_evolution_max_rounds_per_type: int = 1
        self.generation_retry_limit: int = 3
        self.generated_code_timeout_s: float = 2.0
        self.generated_message_max_bytes: int = 1024 * 1024
        # Bound variable RFC/IR/code context inserted into LLM prompts.  The
        # prompt template and its instructions are preserved in full.
        self.prompt_context_max_chars: int = 12_000
        # Response checkers/observers are generated on demand.  Only the
        # protocol-wide fallback and explicitly configured high-value types
        # are prepared before fuzzing starts.
        self.response_component_lazy_generation: bool = True
        self.response_component_prewarm_types: list[str] = []
        # Stop model learning after input/output-scaled MQ stagnation and
        # preserve replayable traces for partial fuzz guidance.
        self.partial_guidance_enabled: bool = True
        
        self.target_name: str
        self.trans_layer: str
        self.pro_name: str
        self.port: int
        self.host: str
        self.rfc_name: list[str]
        
        self.base_url_doc: str
        self.api_key_doc: str
        self.model_doc: str
        self.async_sem_doc: int
        
        self.base_url_fuzz: str
        self.api_key_fuzz: str
        self.model_fuzz: str
        self.async_sem_fuzz: int

        self.base_url_compliance: str
        self.api_key_compliance: str
        self.model_compliance: str
        self.async_sem_compliance: int
        
        self.server: str
        self.sut_deployment: str = 'local'
        self.monitor: dict = {}
        
        self.time_limit_s: int

configs = Config()
configs.base_path = Path(__file__).resolve().parents[1]
