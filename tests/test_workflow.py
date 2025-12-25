from voltron.rfcparser.rfcparser import RFCParser
from voltron.utils.logger import logger
from pathlib import Path
from voltron.fuzz import Fuzzer
import time

def test_anno():
    fuzzer = Fuzzer(
        stype='tcp',
        port=80,
        host='127.0.0.1',
        pro_name='ftp',
        rfc_name='rfc959',
        doc_path=Path('./tests/docs/rfc959.txt').resolve()
    )

def test_ir():
    fuzzer = Fuzzer(
        stype='tcp',
        port=80,
        host='127.0.0.1',
        pro_name='ftp',
        rfc_name='rfc959',
        doc_path=Path('./tests/docs/rfc959.txt').resolve()
    )

def test_gen():
    fuzzer = Fuzzer(
        stype='tcp',
        port=80,
        host='127.0.0.1',
        pro_name='ftp',
        rfc_name='rfc959',
        doc_path=Path('./tests/docs/rfc959.txt').resolve()
    )

    for i in fuzzer.handler.inputs.keys(): 
        logger.debug(fuzzer.handler.message_gen(i))
