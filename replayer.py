#!/bin/python3

from voltron.fuzz import Fuzzer
import click, random
from pathlib import Path

@click.command(help='fuzzer')
@click.option("-s", "--sut", type=str, required=True, help="server under test")
@click.option("-i", "--input", type=str, required=True, help="input direcotory")
@click.option("-o", "--output", type=str, required=True, help="fuzzing time (minute)")
def main(sut, input, output):
    supported_sut = {'lightftp','pureftpd','kamailio', 'live555', 'exim'}
    if sut in supported_sut:
        replayer = Fuzzer(
            target_name=sut
        )
        replayer.replay(
            input=Path(input),
            output=Path(output)
        )
    else:
        print('Unkown Target')

if __name__ == '__main__':
    main()