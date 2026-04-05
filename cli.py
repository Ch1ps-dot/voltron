#!/bin/python3

from voltron.fuzz import Fuzzer
from voltron.configs import configs
import click, random

@click.command(help='fuzzer')
@click.option("-s", "--sut", type=str, required=True, help="server under test")
@click.option("-a", "--algorithm", type=str, default='state', help="fuzzing algorithm")
@click.option("-t", "--time", type=str, required=True, help="fuzzing time (minute)")
@click.option("-c", "--cmdline", type=str, default='auto', help="cmd line to invoke target")
def main(
    sut: str, 
    algorithm: str, 
    time: str, 
    cmdline: str
):
    if cmdline == 'auto':
        with open(configs.base_path / 'configs' / sut / 'run.sh', 'r') as f:
            cmdline = f.read()
    fuzzer = Fuzzer(
        target_name=sut,
        cmdline=cmdline.split(' ')
    )
    fuzzer.fuzz(
        algo=algorithm,
        time_limit_min=int(time)
    )

if __name__ == '__main__':
    main()