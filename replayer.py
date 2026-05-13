#!/bin/python3

from voltron.fuzz import Fuzzer
from voltron.configs import configs
import click, random
from pathlib import Path

@click.command(help='fuzzer')
@click.option("-s", "--sut", type=str, required=True, help="server under test")
@click.option("-d", "--dir", type=str, required=True, help="testcase input direcotory")
@click.option("-c", "--gcov_folder", type=str, required=True, help="gcov analysis directory")
def main(
    sut: str, 
    dir: str, 
    gcov_folder: str
):
    replayer = Fuzzer(
        target_name=sut,
        mode = 'replay'
    )
    replayer.replay(
        res_dir=Path(dir),
        cov_folder=Path(gcov_folder)
    )

if __name__ == '__main__':
    main()