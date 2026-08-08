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
        self.compliance_analysis: bool = False
        self.observer_enabled: bool = True
        self.ir_evolution_enabled: bool = True
        self.ir_evolution_failure_threshold: int = 3
        self.ir_evolution_max_rounds_per_type: int = 1
        self.generation_retry_limit: int = 3
        self.generated_code_timeout_s: float = 2.0
        self.ir_generation_timeout_s: float = 300.0
        self.generated_message_max_bytes: int = 1024 * 1024
        self.parser_validation_samples: tuple[bytes, ...] = ()
        # Bound variable RFC/IR/code context inserted into LLM prompts.  The
        # prompt template and its instructions are preserved in full.
        self.prompt_context_max_chars: int = 12_000
        # Reject unexpectedly large model responses before parsing or storing
        # them as generated artifacts.
        self.llm_response_max_chars: int = 100_000
        # Response checkers/observers are generated on demand.  Only the
        # protocol-wide fallback and explicitly configured high-value types
        # are prepared before fuzzing starts.
        self.response_component_lazy_generation: bool = True
        self.response_component_prewarm_types: list[str] = []
        # Stop model learning after input/output-scaled MQ stagnation and
        # preserve replayable traces for partial fuzz guidance.
        self.partial_guidance_enabled: bool = True
        # A threshold ends one observation-table attempt, not the whole
        # learning phase.  Regenerate components and start this many fresh
        # learning attempts before falling back to partial guidance.
        self.threshold_relearn_limit: int = 3
        self.bootstrap_partial_evolution: bool = True
        # Empty membership-query outputs are commonly transient around a SUT
        # restart.  Retry them locally before declaring model learning failed.
        self.model_learning_empty_response_retries: int = 3
        # A complete interaction startup/readiness attempt can also race a
        # freshly restarted local target.  These retries are per interaction,
        # not additional experiment rounds.
        self.sut_interaction_retry_limit: int = 3
        self.sut_interaction_retry_delay_s: float = 0.1
        
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
        # At most this fraction of request types is evolved into mutators in
        # one fuzzing round.  The LLM concurrency remains a separate cap.
        self.mutator_round_ratio: float = 0.25
        # Bound LLM-driven mutator evolution for one fuzzing phase.  Zero is
        # the explicit opt-out for experiments that require an unlimited run.
        self.mutator_round_limit: int = 12

        self.base_url_compliance: str
        self.api_key_compliance: str
        self.model_compliance: str
        self.async_sem_compliance: int
        
        self.server: str
        self.sut_deployment: str = 'local'
        self.monitor: dict = {}
        
        self.time_limit_s: int
        # Assigned by ``Fuzzer.fuzz`` for one active fuzzing run.  Runtime
        # components intentionally treat it as optional for standalone use.
        self.run_controller = None

configs = Config()
configs.base_path = Path(__file__).resolve().parents[1]
