from voltron.fuzz import Fuzzer

def test_lightftp():
    fuzzer = Fuzzer(
        target_name='lightftp',
        time_limit=10
    )
    fuzzer.fuzz(
        algo='rand'
    )

def main():
    test_lightftp()

if __name__ == '__main__':
    main()