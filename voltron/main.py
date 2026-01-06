from voltron.fuzz import Fuzzer

def test_lightftp():
    fuzzer = Fuzzer(
        target='lightftp',
        time_limit=10
    )
    fuzzer.fuzz(
        algo='rand'
    )

def main():
    test_lightftp()