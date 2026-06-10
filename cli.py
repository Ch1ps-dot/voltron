#!/bin/python3

from voltron.fuzz import Fuzzer
from voltron.configs import configs
import click, random

@click.command(help='fuzzer')
@click.option("-s", "--sut", type=str, required=True, help="server under test")
@click.option("-a", "--algorithm", type=str, default='state', help="fuzzing algorithm")
@click.option("-t", "--time", type=str, required=True, help="fuzzing time (minute)")
@click.option("-c", "--cmdline", type=str, default='auto', help="cmd line to invoke target")
@click.option("-o", "--output", type=str, default='default', help="output path for fuzzing results")
@click.option(
    "--spec-knowledge/--no-spec-knowledge",
    default=True,
    show_default=True,
    help="Enable RFC/IR knowledge. Disabled mode requires cached seed generators and parser.",
)
@click.option(
    "--state-learning/--no-state-learning",
    default=True,
    show_default=True,
    help="Enable active Mealy-machine learning before fuzzing.",
)
@click.option(
    "--guided-scheduling/--no-guided-scheduling",
    default=True,
    show_default=True,
    help="Enable state/dependency-guided scheduling and feedback-based energy.",
)
def main(
    sut: str, 
    algorithm: str, 
    time: str, 
    cmdline: str,
    output: str,
    spec_knowledge: bool,
    state_learning: bool,
    guided_scheduling: bool,
):
    if cmdline == 'auto':
        with open(configs.base_path / 'config' / 'subjects' / sut / 'run.sh', 'r') as f:
            cmdline = f.read()
    fuzzer = Fuzzer(
        target_name=sut,
        cmdline=cmdline.split(' '),
        output=output,
        spec_knowledge=spec_knowledge,
        state_learning=state_learning,
        guided_scheduling=guided_scheduling,
    )
    fuzzer.fuzz(
        algo=algorithm,
        time_limit_min=int(time)
    )

if __name__ == '__main__':
    main()
