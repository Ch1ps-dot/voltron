#!/bin/python3

from voltron.fuzz import Fuzzer
import click
from pathlib import Path

@click.command(help='fuzzer')
@click.option("-s", "--sut", type=str, required=True, help="server under test")
@click.option(
    "-d",
    "--dir",
    "result_dir",
    type=click.Path(path_type=Path),
    required=True,
    help="testcase input directory",
)
@click.option(
    "-c",
    "--gcov_folder",
    type=click.Path(path_type=Path),
    required=True,
    help="gcov analysis directory",
)
def main(
    sut: str,
    result_dir: Path,
    gcov_folder: Path,
):
    result_dir = result_dir.expanduser().resolve()
    gcov_folder = gcov_folder.expanduser().resolve()
    replayer = Fuzzer(
        target_name=sut,
        mode='replay',
        output=str(result_dir),
    )
    replayer.replay(
        res_dir=result_dir,
        cov_folder=gcov_folder,
    )

if __name__ == '__main__':
    main()
