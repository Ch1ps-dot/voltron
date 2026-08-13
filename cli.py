#!/bin/python3

from voltron.fuzz import Fuzzer
from voltron.configs import configs
from voltron.rfcparser.standalone import (
    generate_target_ir,
    parse_target_section_trees,
)
from voltron.config_loader import load_runtime_config
from voltron.learning_bundle import import_learning_bundle as stage_learning_bundle, LearningBundleError
from pathlib import Path
import json
import click

@click.command(help='fuzzer')
@click.option("-s", "--sut", type=str, required=True, help="server under test")
@click.option("-a", "--algorithm", type=str, default='state', help="fuzzing algorithm")
@click.option(
    "-t",
    "--time",
    type=click.IntRange(min=1),
    help="fuzzing time (minute; minimum 1)",
)
@click.option("-c", "--cmdline", type=str, default='auto', help="cmd line to invoke target")
@click.option("-o", "--output", type=str, default='default', help="output path for fuzzing results")
@click.option(
    "--rfc-parser",
    is_flag=True,
    help=(
        "Only parse the target's configured RFC documents into SectionTree "
        "cache files"
    ),
)
@click.option(
    "--generate-ir",
    is_flag=True,
    help=(
        "Only parse the target's protocol specifications and generate its IR"
    ),
)
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
@click.option(
    "--compliance-analysis/--no-compliance-analysis",
    default=False,
    show_default=True,
    help=(
        "Review checker rejections with the compliance LLM and evolve "
        "false-positive checkers (disabled by default)."
    ),
)
@click.option(
    "--observer/--no-observer",
    default=True,
    show_default=True,
    help=(
        "Enable generated semantic response observers and their runtime "
        "evolution."
    ),
)
@click.option(
    "--load-aflnet-seeds/--no-load-aflnet-seeds",
    default=True,
    show_default=True,
    help=(
        "Load converted raw AFLNet seeds after model learning as interesting "
        "fuzzing sequences by default; they stay outside the learned alphabet."
    ),
)
@click.option(
    "--learn-and-export",
    is_flag=True,
    help="Only synthesize components and learn/export a reusable learning bundle.",
)
@click.option(
    "--import-learning-bundle",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Verify a trusted learning bundle in staging for this target.",
)
@click.option(
    "--activate-import",
    is_flag=True,
    help="Atomically activate a verified imported bundle after staging.",
)
@click.option(
    "--batch-id",
    type=str,
    help=(
        "Optional safe name for an activated imported batch. Requires "
        "--import-learning-bundle and --activate-import."
    ),
)
@click.option(
    "--model-batch",
    type=str,
    help=(
        "Use one imported model batch under component/models/<sut>/<batch>. "
        "Its model and equipment are loaded together."
    ),
)
def main(
    sut: str, 
    algorithm: str, 
    time: int | None,
    cmdline: str,
    output: str,
    rfc_parser: bool,
    generate_ir: bool,
    spec_knowledge: bool,
    state_learning: bool,
    guided_scheduling: bool,
    compliance_analysis: bool,
    observer: bool,
    load_aflnet_seeds: bool,
    learn_and_export: bool,
    import_learning_bundle: Path | None,
    activate_import: bool,
    batch_id: str | None,
    model_batch: str | None,
):
    if rfc_parser and generate_ir:
        raise click.UsageError(
            "--rfc-parser and --generate-ir cannot be used together."
        )

    if activate_import and import_learning_bundle is None:
        raise click.UsageError('--activate-import requires --import-learning-bundle.')
    if batch_id is not None and import_learning_bundle is None:
        raise click.UsageError('--batch-id requires --import-learning-bundle.')
    if batch_id is not None and not activate_import:
        raise click.UsageError('--batch-id requires --activate-import.')
    if model_batch is not None and import_learning_bundle is not None:
        raise click.UsageError(
            '--model-batch cannot be combined with --import-learning-bundle.'
        )
    if import_learning_bundle is not None:
        runtime = load_runtime_config(configs.base_path / 'config')
        if sut not in runtime:
            raise click.ClickException(f'Unknown SUT: {sut}')
        try:
            staging, report = stage_learning_bundle(
                bundle=import_learning_bundle,
                staging_root=configs.base_path / 'component' / 'import-staging',
                target=sut,
                protocol=runtime[sut]['protocol'],
                activate=activate_import,
                base_path=configs.base_path,
                batch_id=batch_id,
            )
        except (LearningBundleError, OSError, ValueError) as exc:
            raise click.ClickException(str(exc)) from exc
        click.echo(json.dumps({'staging': str(staging), **report}, ensure_ascii=False))
        return

    if rfc_parser:
        try:
            results = parse_target_section_trees(sut)
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            raise click.ClickException(str(exc)) from exc
        for result in results:
            click.echo(
                f'{result.rfc_name}: {result.source} -> '
                f'{result.output_path}'
            )
        return

    if generate_ir:
        try:
            ir_path = generate_target_ir(sut)
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            raise click.ClickException(str(exc)) from exc
        click.echo(f"IR generated for {sut} -> {ir_path}")
        return

    if time is None:
        raise click.UsageError(
            'Missing option "-t" / "--time" for fuzzing mode.'
        )
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
        compliance_analysis=compliance_analysis,
        observer_enabled=observer,
        aflnet_seed_loading=load_aflnet_seeds,
        learning_only=learn_and_export,
        model_batch=model_batch,
    )
    exit_code = fuzzer.fuzz(
        algo=algorithm,
        time_limit_min=time
    )
    if exit_code:
        raise click.exceptions.Exit(exit_code)

if __name__ == '__main__':
    main()
