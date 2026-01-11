from voltron.utils.logger import logger
from pathlib import Path
from voltron.fuzz import Fuzzer
import time

def test_http():
    fuzzer = Fuzzer(
        target_name='http',
        time_limit_min=10
    )
    # fuzzer.fuzz(
    #     algo='rand'
    # )

def test_lightftp():
    fuzzer = Fuzzer(
        target_name='lightftp',
        time_limit_min=10
    )
    # fuzzer.fuzz(
    #     algo='rand'
    # )