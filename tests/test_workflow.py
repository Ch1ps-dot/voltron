from voltron.rfcparser.rfcparser import RFCParser
from voltron.utils.logger import logger
from pathlib import Path
from voltron.fuzz import Fuzzer
import time

def test_http():
    fuzzer = Fuzzer(
        target='http',
        time_limit=10
    )
    fuzzer.fuzz(
        algo='rand'
    )

def test_lightftp():
    fuzzer = Fuzzer(
        target='lightftp',
        time_limit=10
    )
    fuzzer.fuzz(
        algo='rand'
    )