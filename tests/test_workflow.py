from voltron.utils.rfcparser import RFCParser
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
        doc_path=Path('./tests/docs/rfc959.txt').resolve()
    )

def test_ir():
    fuzzer = Fuzzer(
        stype='tcp',
        port=80,
        host='127.0.0.1',
        pro_name='ftp',
        doc_path=Path('./tests/docs/rfc959.txt').resolve()
    )
