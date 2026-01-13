import yaml
from pathlib import Path
from voltron.utils.logger import logger

def load_config():
    base_path = Path(__file__).resolve().parents[1]

    configs: dict
    with open(base_path / 'configs.yaml', 'r', encoding='utf-8') as f:
        configs = yaml.safe_load(f)
        return configs
    if(configs == None):
        logger.debug('No Configs') 

configs = load_config()
base_path = base_path = Path(__file__).resolve().parents[1]