from pathlib import Path
from pprint import pprint
from voltron.utils.logger import logger
from  voltron.llm.chat import Chater

def save_to_file(str):
    f = open( 'test.txt', 'w+')
    f.write(str)
    f.close()

def test_gen():
    ct = Chater(Path('./prompts').resolve())
    logger.debug(ct.llm_gen_input(pro_name="MQTT", msg_type="publish"))


def test_ir():
    ct = Chater(Path('./prompts').resolve())
    logger.debug(ct.llm_ir_generation(pro_name='ftp', message_name='CWD'))