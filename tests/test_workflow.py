from voltron.rfcparser.rfcparser import RFCParser
from voltron.utils.logger import logger
from pathlib import Path
from voltron.fuzz import Fuzzer
import time

def test_gen():
    fuzzer = Fuzzer(
        trans='tcp',
        port=80,
        host='127.0.0.1',
        pro_name='ftp',
        rfc_name='rfc959',
        doc_path=Path('./rfcs/rfc959.txt').resolve()
    )

def test_alpha():
    fuzzer = Fuzzer(
        trans='tcp',
        port=80,
        host='127.0.0.1',
        pro_name='ftp',
        rfc_name='rfc959',
        doc_path=Path('./rfcs/rfc959.txt').resolve()
    )
    fuzzer.alphabet.show()

def test_rand():
    fuzzer = Fuzzer(
        trans='tcp',
        port=80,
        host='127.0.0.1',
        pro_name='ftp',
        rfc_name='rfc959',
        doc_path=Path('./rfcs/rfc959.txt').resolve()
    )
    fuzzer.fuzz(
        algo='rand'
    )
