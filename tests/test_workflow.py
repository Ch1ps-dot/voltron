from voltron.rfcparser.rfcparser import RFCParser
from voltron.utils.logger import logger
from pathlib import Path
from voltron.fuzz import Fuzzer
import time

def test_gen():
    fuzzer = Fuzzer(
        pro_name='ftp'
    )

def test_alpha():
    fuzzer = Fuzzer(
        pro_name='ftp'
    )
    fuzzer.alphabet.show()

def test_rand():
    fuzzer = Fuzzer(
        pro_name='ftp'
    )
    fuzzer.fuzz(
        algo='rand'
    )
