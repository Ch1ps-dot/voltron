from voltron.rfcparser.rfcparser import RFCParser
from voltron.utils.logger import logger
from pathlib import Path
from voltron.fuzz import Fuzzer
import time

def test_gen():
    fuzzer = Fuzzer(
        pro_name='ftp',
        time_limit=10
    )

def test_alpha():
    fuzzer = Fuzzer(
        pro_name='ftp',
        time_limit=10
    )
    fuzzer.alphabet.show()

def test_rand():
    fuzzer = Fuzzer(
        pro_name='ftp',
        time_limit=10
    )
    fuzzer.fuzz(
        algo='rand'
    )

def test_http():
    fuzzer = Fuzzer(
        pro_name='http',
        time_limit=10
    )
    fuzzer.fuzz(
        algo='rand'
    )
