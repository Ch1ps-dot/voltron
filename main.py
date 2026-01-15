from voltron.fuzz import Fuzzer

def test_lightftp():
    fuzzer = Fuzzer(
        target_name='lightftp',
        time_limit_min=10
    )
    fuzzer.fuzz(
        algo='rand'
    )
    
def test_state():
    fuzzer = Fuzzer(
        target_name='lightftp',
        time_limit_min=10
    )
    fuzzer.fuzz(
        algo='state'
    )

def main():
    test_state()

if __name__ == '__main__':
    main()