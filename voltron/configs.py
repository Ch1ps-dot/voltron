import yaml
from pathlib import Path
from voltron.utils.logger import logger_fuzz as logger

class Config:
    def __init__(self) -> None:
        self.base_path: Path
        self.info_path: Path
        self.run_script: Path
        self.setup_script: Path
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
