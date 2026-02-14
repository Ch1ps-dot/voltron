import yaml
from pathlib import Path
from voltron.utils.logger import logger

class Config:
    def __init__(self) -> None:
        self.base_path: Path
        self.info_path: Path
        self.pre_script: Path
        self.post_script: Path
        self.models_path: Path
        self.doc_paths: list[Path] = []
        self.pmp_path: Path
        self.results_path: Path
        self.cov_setup_path: Path
        self.cov_collect_path: Path
        self.fuzz_mode: str
        
        self.target_name: str
        self.trans_layer: str
        self.pro_name: str
        self.port: int
        self.host: str
        self.rfc_name: str
        
        self.base_url: str
        self.api_key: str
        self.model: str
        self.async_sem: int
        
        self.server: str
        
        self.time_limit_s: int

configs = Config()
configs.base_path = Path(__file__).resolve().parents[1]