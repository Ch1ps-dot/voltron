from pathlib import Path
from lxml import etree # type: ignore
from tqdm import tqdm
import json, asyncio, hashlib, math, threading, time, queue, re
from collections.abc import Callable
from tqdm.asyncio import tqdm_asyncio

from voltron.synthesizer.generator import Generator
from voltron.synthesizer.parser import Parser
from voltron.synthesizer.checker import Checker
from voltron.synthesizer.observer import ResponseObserver
from voltron.synthesizer.code_validation import (
    RAW_SHA256_OBSERVER,
    validate_generated_code,
)
from voltron.synthesizer.component_paths import (
    component_type_dir,
    path_within,
    type_to_slug,
)
from voltron.rfcparser.rfc_parser import AsyncRFCParser
from voltron.utils.logger import logger_fuzz as logger
from voltron.configs import configs
from voltron.analyzer.analyzer import analyzer
from voltron.analyzer.compliance import (
    build_compliance_prompt,
    collect_response_sections,
    parse_compliance_result,
    retrieve_response_sections,
)
from voltron.llm.chatter import (
    AsyncChater,
    CandidateSourceValidationError,
    LLMDeadlineExceeded,
)
from voltron.learner.automata import MealyMachine
from dataclasses import dataclass, asdict, field
    


class AsyncProducer:
    """Prepare message producer, parser, mutator, and response checker.
    
    Atrributes:
        *_path: lots of file path
        chater: the chater to call LLM
        rfcp: the RFC parser to provide IR and dependency information
        req_types: the types of request messages
        res_types: the types of response messages
        req_dep: the dependency between request messages
        poss_response: possible response for each request message
        generators: the generated input generators
        parsers: the generated packet parsers
        checkers: the generated response conformance checkers
        mutators: the generated mutators
    """

    RESPONSE_COMPONENT_CONTRACT_VERSION = 'response-components-v1'

    def __init__(
            self,
            chater: AsyncChater,
            rfcp: AsyncRFCParser,
    ) -> None:
        if rfcp.req_ir != None:
            self.req_ir = rfcp.req_ir.getroot()
        if rfcp.res_ir != None:
            self.res_ir = rfcp.res_ir.getroot()

        self.equipment_path = getattr(
            configs,
            'equipment_path',
            configs.base_path / 'component' / 'equipment',
        )
        # A selected imported batch already scopes equipment to one target.
        self.synthesizer_path = (
            self.equipment_path
            if getattr(configs, 'model_batch', None) is not None
            else (
                self.equipment_path / configs.target_name / 'llm-type-only'
                if not getattr(configs, 'spec_knowledge', True)
                else self.equipment_path / configs.target_name
            )
        )
        self.generator_path = self.synthesizer_path / 'generators'
        self.mutator_path = self.synthesizer_path / 'mutators'
        self.parser_path = self.synthesizer_path / 'parsers'
        self.checker_path = self.synthesizer_path / 'checkers'
        self.observer_path = self.synthesizer_path / 'observers'
        self.legacy_observer_path = self.synthesizer_path / 'hashers'
        self.best_equipment_path = configs.models_path / 'best_equipment'
        self.best_generator_path = self.best_equipment_path / 'generators'
        self.best_parser_path = self.best_equipment_path / 'parser.py'
        self.best_equipment_info_path = (
            self.best_equipment_path / 'best_equipment.json'
        )
        self.info_path = configs.info_path
        
        self.generator_info_path = self.generator_path / 'generator_info.json'
        self.parser_info_path = self.parser_path / 'parser_info.json'
        self.checker_info_path = self.checker_path / 'checker_info.json'
        self.observer_info_path = self.observer_path / 'observer_info.json'
        self.legacy_observer_info_path = (
            self.legacy_observer_path / 'hasher_info.json'
        )
        self.mutator_info_path = self.mutator_path / 'mutator_info.json'
        self.type_path_map_path = self.synthesizer_path / 'type_path_map.json'
        self._type_path_map_lock = threading.RLock()
        self._type_path_map: dict[str, str] = {}
        self._type_path_map_loaded = False
        self.generation_manifest_path = (
            configs.results_path / 'generation_manifest.jsonl'
        )
        self._generation_manifest_lock = threading.Lock()
        
        for path in (
            self.generator_path,
            self.parser_path,
            self.checker_path,
            self.observer_path,
            self.mutator_path,
        ):
            path.mkdir(parents=True, exist_ok=True)

        self.chater = chater
        self.rfcp = rfcp
        
        # types of symbols
        self.req_types: set[str] = self.rfcp.req_types
        self.res_types: set[str] = self.rfcp.res_types
        self.req_dep: dict[str, dict[str, dict]] = self.rfcp.req_dep_map
        self.poss_response: dict[str, list[str]] = self.rfcp.poss_res
        
        self.generators: dict[str, list[Generator]] = {}
        self.parsers: list[Parser] = []
        self.checkers: dict[str, list[Checker]] = {}
        self.observers: dict[str, list[ResponseObserver]] = {}
        self.mutators: dict[str, list[Generator]] = {}
        self.best_generators: dict[str, Generator] = {}
        self.best_parser_info: dict = {}
        self._response_sections = None
        self._ir_evolution_rounds: dict[str, int] = {}
        self._response_component_lock = threading.RLock()
        self._response_component_pending: set[str] = set()
        self._response_component_failures: set[str] = set()
        self._response_component_queue: queue.Queue[str] = queue.Queue()
        self._response_component_worker: threading.Thread | None = None

    def _record_generation(
        self,
        component: str,
        msg_type: str,
        outcome: str,
        attempt: int,
        code: str | None = None,
        error: str = '',
        *,
        base_sha256: str | None = None,
        changed: bool | None = None,
        reason: str = '',
        response_coverage: dict[str, list[str]] | None = None,
    ) -> None:
        record = {
            'timestamp': time.time(),
            'component': component,
            'message_type': msg_type,
            'outcome': outcome,
            'attempt': attempt,
            'code_sha256': (
                hashlib.sha256(code.encode('utf-8')).hexdigest()
                if code is not None
                else None
            ),
            'base_sha256': base_sha256,
            'changed': changed,
            'reason': reason[:2000],
            'error': error[:2000],
            'response_coverage': response_coverage,
        }
        try:
            manifest_lock = getattr(self, '_generation_manifest_lock', None)
            if manifest_lock is None:
                manifest_lock = threading.Lock()
                self._generation_manifest_lock = manifest_lock
            manifest_path = getattr(
                self,
                'generation_manifest_path',
                configs.results_path / 'generation_manifest.jsonl',
            )
            with manifest_lock:
                with manifest_path.open(
                    'a', encoding='utf-8'
                ) as stream:
                    json.dump(record, stream, ensure_ascii=False)
                    stream.write('\n')
        except Exception:
            logger.exception('Producer: failed to record generation manifest')

    @staticmethod
    def _evolution_changed(code: str) -> bool:
        """Treat legacy string-returning test doubles as changed source."""
        return bool(getattr(code, 'changed', True))

    @staticmethod
    def _evolution_reason(code: str) -> str:
        reason = getattr(code, 'reason', '')
        return reason if isinstance(reason, str) else ''

    @staticmethod
    def _mutator_response_coverage(
        possible: list[str] | set[str],
        observed: list[str] | set[str],
    ) -> dict[str, list[str]]:
        """Normalize the per-request response gap supplied to a mutator."""
        possible_responses = sorted({str(response) for response in possible})
        observed_responses = sorted({str(response) for response in observed})
        return {
            'possible': possible_responses,
            'observed': observed_responses,
            'missing': sorted(
                set(possible_responses) - set(observed_responses)
            ),
        }
            
    def run(
        self
    ):
        """Load or generate initial generators, parser, checker, and mutators.
        """
        # A no-spec run is a fresh LLM-only ablation.  Never load historical
        # equipment, including an earlier LLM-only run, because it makes the
        # requested comparison depend on cache state.
        if (
            not getattr(configs, 'spec_knowledge', True)
            and not getattr(configs, 'reuse_no_spec_bundle', False)
        ):
            self.generator_gen()
            self.parser_gen()
        # load existed generator info or generate init generators
        elif(self.generator_info_path.is_file()):
            try:
                with open(self.generator_info_path, 'r', encoding='utf-8') as f:
                    generator_info = json.load(f)
                    self.generators_info_load(generator_info)
                self._filter_invalid_cached_generators()
                logger.debug("Producer: load generator")
            except Exception as e:
                logger.debug(f'Producer: generator load error {e}')
                exit(1)
        else:
            self.generator_gen()
        
        # load existed parser info or generate init parser
        if (
            (getattr(configs, 'spec_knowledge', True)
             or getattr(configs, 'reuse_no_spec_bundle', False))
            and self.parser_info_path.is_file()
        ):
            try:
                with open(self.parser_info_path, 'r', encoding='utf-8') as f:
                    parser_info = json.load(f)
                    self.parsers_info_load(parser_info)
                logger.debug("Producer: load parser info")
                if (
                    configs.spec_knowledge
                    and (
                        not self._parser_cache_matches_primary_field()
                        or not self._parser_cache_contract_valid()
                    )
                ):
                    logger.debug(
                        'Producer: parser cache does not match the primary '
                        'response field; regenerating'
                    )
                    self.parsers = []
                    self.parser_gen()
            except Exception as e:
                logger.debug(f'Producer: parser load error {e}')
        elif getattr(configs, 'spec_knowledge', True):
            self.parser_gen()

        if configs.fuzz_mode != 'replay':
            self._load_checkers()
            if getattr(configs, 'observer_enabled', True):
                self._load_observers()

        # load existed parser info or generate init mutator
        if (
            not getattr(configs, 'offline_mutator_only', False)
            and self.mutator_info_path.is_file()
        ):
            try:
                with open(self.mutator_info_path, 'r', encoding='utf-8') as f:
                    mutator_info = json.load(f)
                    self.mutators_info_load(mutator_info)
                    self._filter_invalid_cached_mutators()
                logger.debug("Mutator: load mutator info")
            except Exception as e:
                logger.debug(f'Mutator: load error {e}')

        if getattr(configs, 'spec_knowledge', True):
            self.load_best_equipment()

        if (
            not configs.spec_knowledge
            or getattr(configs, 'offline_mutator_only', False)
        ):
            self.generators = {
                msg_type: generators[:1]
                for msg_type, generators in self.generators.items()
                if generators
            }
            self.parsers = self.parsers[:1]
            self.checkers = {
                msg_type: checkers[:1]
                for msg_type, checkers in self.checkers.items()
                if checkers
            }
            self.observers = {
                msg_type: observers[:1]
                for msg_type, observers in self.observers.items()
                if observers
            }
            self.mutators = {}

    def _ensure_type_path_map(self, root: Path) -> None:
        if not hasattr(self, '_type_path_map_lock'):
            self._type_path_map_lock = threading.RLock()
        if not hasattr(self, '_type_path_map'):
            self._type_path_map = {}
        if getattr(self, '_type_path_map_loaded', False):
            return
        path = getattr(
            self,
            'type_path_map_path',
            root.parent / 'type_path_map.json',
        )
        self.type_path_map_path = path
        if path.is_file():
            try:
                payload = json.loads(path.read_text(encoding='utf-8'))
                mappings = payload.get('types', {})
                if isinstance(mappings, dict):
                    self._type_path_map = {
                        str(name): str(slug)
                        for name, slug in mappings.items()
                    }
            except (OSError, ValueError, TypeError):
                logger.warning(
                    'Producer: ignoring invalid type path map at %s',
                    path,
                )
        self._type_path_map_loaded = True

    def _record_type_path(self, root: Path, type_name: str) -> str:
        """Record the display-name to filesystem-name mapping atomically."""
        slug = type_to_slug(type_name)
        self._ensure_type_path_map(root)
        with self._type_path_map_lock:
            for known_type, known_slug in self._type_path_map.items():
                if known_slug == slug and known_type != type_name:
                    raise ValueError(
                        'component type path collision: '
                        f'{type_name!r} and {known_type!r} -> {slug!r}'
                    )
            if self._type_path_map.get(type_name) != slug:
                self._type_path_map[type_name] = slug
                self._atomic_write_json(
                    self.type_path_map_path,
                    {
                        'version': 1,
                        'encoding': 'percent-encoded UTF-8 with digest suffix',
                        'types': dict(sorted(self._type_path_map.items())),
                    },
                )
        return slug

    def _component_type_dir(
        self,
        root: Path,
        type_name: str,
        *,
        record: bool = True,
    ) -> Path:
        if record:
            self._record_type_path(root, type_name)
        return component_type_dir(root, type_name)

    def _component_source_path(
        self,
        root: Path,
        component: Generator | Checker | ResponseObserver,
    ) -> Path:
        """Resolve cached source without accepting paths outside its root."""
        typed_path = (
            self._component_type_dir(root, component.msg_type, record=False)
            / f'{component.name}.py'
        )
        if typed_path.is_file():
            return typed_path
        if component.path:
            metadata_path = Path(component.path)
            if path_within(root, metadata_path) and metadata_path.is_file():
                return metadata_path
        return typed_path

    def capture_current_equipment(
        self,
        parser: Parser | None = None,
    ) -> tuple[dict[str, Generator], Parser]:
        """Capture the equipment versions used by the current hypothesis."""
        generators = {
            msg_type: Generator(**asdict(versions[-1]))
            for msg_type, versions in self.generators.items()
            if versions
        }
        selected_parser = parser or self.parsers[-1]
        return generators, Parser(**asdict(selected_parser))

    def save_best_equipment(
        self,
        model_id: str,
        generators: dict[str, Generator],
        parser: Parser,
    ) -> None:
        """Persist the generator/parser set associated with the best model."""
        self.best_generator_path.mkdir(parents=True, exist_ok=True)
        saved_generators: dict[str, Generator] = {}

        for msg_type, generator in generators.items():
            source_path = self._component_source_path(
                self.generator_path,
                generator,
            )
            snapshot_path = (
                self.best_generator_path
                / f'{type_to_slug(msg_type)}.py'
            )
            snapshot_path.write_text(
                source_path.read_text(encoding='utf-8'),
                encoding='utf-8',
            )
            saved_generators[msg_type] = Generator(
                msg_type=generator.msg_type,
                evolved_from=generator.evolved_from,
                name=generator.name,
                path=str(snapshot_path.resolve()),
                cur_res=list(generator.cur_res),
                pre_res=list(generator.pre_res),
                fut_res=list(generator.fut_res),
                was_used=generator.was_used,
                broken=generator.broken,
            )

        parser_source_path = self.parser_path / f'{parser.name}.py'
        self.best_parser_path.write_text(
            parser_source_path.read_text(encoding='utf-8'),
            encoding='utf-8',
        )
        parser_info = {
            **asdict(parser),
            'path': str(self.best_parser_path.resolve()),
        }
        manifest = {
            'model_id': str(model_id),
            'selection_metric': 'max_response_transition_types',
            'generators': {
                msg_type: asdict(generator)
                for msg_type, generator in saved_generators.items()
            },
            'parser': parser_info,
        }
        self.best_equipment_info_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + '\n',
            encoding='utf-8',
        )
        self.best_generators = saved_generators
        self.best_parser_info = parser_info
        logger.debug(
            f'Producer: saved best equipment for model {model_id}'
        )

    def load_best_equipment(self) -> None:
        """Load a previously saved best-equipment snapshot when available."""
        self.best_generators = {}
        self.best_parser_info = {}
        if not self.best_equipment_info_path.is_file():
            return

        try:
            manifest = json.loads(
                self.best_equipment_info_path.read_text(encoding='utf-8')
            )
            for msg_type, info in manifest.get('generators', {}).items():
                normalized_info = dict(info)
                path = Path(normalized_info.get('path', ''))
                # Imported snapshots may retain the source host's absolute
                # path.  The snapshot's filename is canonical, so rebase
                # only a missing path into this local best-equipment folder.
                if not path.is_file():
                    candidate = self.best_generator_path / path.name
                    if candidate.is_file():
                        normalized_info['path'] = str(candidate.resolve())
                generator = Generator(**normalized_info)
                if Path(generator.path).is_file():
                    self.best_generators[msg_type] = generator

            parser_info = dict(manifest.get('parser', {}))
            parser_path = parser_info.get('path', '')
            if parser_path and not Path(parser_path).is_file():
                if self.best_parser_path.is_file():
                    parser_info['path'] = str(self.best_parser_path.resolve())
                    parser_path = parser_info['path']
            if parser_path and Path(parser_path).is_file():
                self.best_parser_info = parser_info
            logger.debug(
                'Producer: loaded best equipment for model '
                f'{manifest.get("model_id", "")}'
            )
        except Exception:
            self.best_generators = {}
            self.best_parser_info = {}
            logger.exception('Producer: failed to load best equipment')

    def _load_checkers(self) -> None:
        """Load or synthesize response checkers outside replay mode."""
        if self.checker_info_path.is_file():
            try:
                with open(self.checker_info_path, 'r', encoding='utf-8') as f:
                    checker_info = json.load(f)
                if isinstance(checker_info, dict):
                    self.checkers_info_load(checker_info)
                    logger.debug("Producer: load checker info")
                    if (
                        configs.spec_knowledge
                        and not self._checker_cache_matches_response_types(
                            self._initial_response_component_types()
                        )
                    ):
                        logger.debug(
                            'Producer: checker cache does not match response '
                            'types from the primary state field; regenerating'
                        )
                        self.checker_gen(
                            self._missing_checker_types(
                                self._initial_response_component_types()
                            )
                        )
                elif configs.spec_knowledge:
                    logger.debug(
                        "Producer: legacy checker cache detected; regenerating"
                    )
                    self.checker_gen(self._initial_response_component_types())
                else:
                    self.legacy_checkers_info_load(checker_info)
                    logger.debug("Producer: load legacy checker info")
            except Exception as e:
                logger.debug(f'Producer: checker load error {e}')
        elif configs.spec_knowledge:
            self.checker_gen(self._initial_response_component_types())

    def _load_observers(self) -> None:
        """Load or synthesize response observers outside replay mode."""
        info_path = self.observer_info_path
        if not info_path.is_file() and self.legacy_observer_info_path.is_file():
            info_path = self.legacy_observer_info_path

        if info_path.is_file():
            try:
                with info_path.open('r', encoding='utf-8') as f:
                    observer_info = json.load(f)
                self.observers_info_load(observer_info)
                logger.debug("Producer: load observer info")
                if (
                    configs.spec_knowledge
                    and (
                        not self._observer_cache_matches_response_types(
                            self._initial_response_component_types()
                        )
                        or not self._observer_cache_contracts_valid()
                    )
                ):
                    logger.debug(
                        'Producer: observer cache does not match response types; '
                        'regenerating'
                    )
                    self.observer_gen(
                        self._missing_observer_types(
                            self._initial_response_component_types()
                        )
                    )
            except Exception:
                logger.exception('Producer: observer load error')
                if configs.spec_knowledge:
                    self.observer_gen(
                        self._initial_response_component_types()
                    )
        elif configs.spec_knowledge:
            self.observer_gen(self._initial_response_component_types())

    def _generated_code_timeout(self) -> float:
        return max(0.1, getattr(configs, 'generated_code_timeout_s', 2.0))

    def _generated_message_limit(self) -> int:
        return max(
            1,
            getattr(configs, 'generated_message_max_bytes', 1024 * 1024),
        )

    def _observer_cache_contracts_valid(self) -> bool:
        invalid_types: list[str] = []
        for response_type in list(self.observers):
            versions = self.observers.get(response_type, [])
            if not versions:
                invalid_types.append(response_type)
                continue
            observer = versions[-1]
            path = self._component_source_path(
                self.observer_path,
                observer,
            )
            if not path.is_file():
                invalid_types.append(response_type)
                continue
            code = path.read_text(encoding='utf-8')
            validation = validate_generated_code(
                code,
                'packet_observer',
                'observer',
                timeout_s=self._generated_code_timeout(),
            )
            if not validation.ok:
                self._record_generation(
                    'observer', response_type, 'cache_invalid', 0, code,
                    validation.error,
                )
                invalid_types.append(response_type)
                continue
            self._record_generation(
                'observer', response_type, 'reused_cache', 0, code,
            )
        for response_type in invalid_types:
            self.observers.pop(response_type, None)
        return not invalid_types

    def _filter_invalid_cached_mutators(self) -> None:
        filtered: dict[str, list[Generator]] = {}
        for msg_type, versions in self.mutators.items():
            for mutator in reversed(versions):
                path = self._component_source_path(
                    self.mutator_path,
                    mutator,
                )
                if not path.is_file() and mutator.path:
                    path = Path(mutator.path)
                if not path.is_file():
                    continue
                code = path.read_text(encoding='utf-8')
                validation = validate_generated_code(
                    code,
                    'mutate',
                    'mutator',
                    timeout_s=self._generated_code_timeout(),
                    max_output_bytes=self._generated_message_limit(),
                )
                if validation.ok:
                    filtered[msg_type] = [mutator]
                    self._record_generation(
                        'mutator', msg_type, 'reused_cache', 0, code,
                    )
                    break
                self._record_generation(
                    'mutator', msg_type, 'cache_invalid', 0, code,
                    validation.error,
                )
        self.mutators = filtered

    def _filter_invalid_cached_generators(self) -> None:
        filtered: dict[str, list[Generator]] = {}
        for msg_type, versions in self.generators.items():
            for generator in versions:
                path = self._component_source_path(
                    self.generator_path,
                    generator,
                )
                if not path.is_file():
                    continue
                code = path.read_text(encoding='utf-8')
                validation = validate_generated_code(
                    code,
                    'generate',
                    'generator',
                    timeout_s=self._generated_code_timeout(),
                    max_output_bytes=self._generated_message_limit(),
                )
                if validation.ok:
                    filtered.setdefault(msg_type, []).append(generator)
                    self._record_generation(
                        'generator', msg_type, 'reused_cache', 0, code,
                    )
                    continue
                self._record_generation(
                    'generator', msg_type, 'cache_invalid', 0, code,
                    validation.error,
                )
            if msg_type not in filtered and versions:
                # Keep the latest source available for runtime repair.  It is
                # quarantined before any failing output can be sent.
                filtered[msg_type] = [versions[-1]]
        self.generators = filtered

    async def _generator_gen_one(
        self,
        msg,
        sem
    ):
        msg_ir = etree.tostring(msg, encoding="utf-8", pretty_print=True).decode("utf-8")
        msg_type = msg.get('name')
        info = ''
        with open(self.info_path, 'r', encoding='utf-8') as f:
            info = f.read()
        async with sem:
            failure_count = 0
            failed_code: str | None = None
            failure_error = ''
            retry_limit = max(1, getattr(configs, 'generation_retry_limit', 3))
            while failure_count < retry_limit:
                input_code: str | None = None
                try:
                    if failed_code is None:
                        input_code = await self.chater.llm_generator_gen(
                            pro_name=self.rfcp.pro_name,
                            field_name=self.rfcp.req_fields[0],
                            msg_type=msg_type,
                            msg_ir=msg_ir,
                            info=info,
                            type_rule=self._request_type_rule_info(msg_type),
                        )
                    else:
                        input_code = await self.chater.llm_code_repair(
                            code=failed_code,
                            error=failure_error,
                            function_name='generate',
                        )

                    validation = validate_generated_code(
                        input_code,
                        'generate',
                        'generator',
                        timeout_s=self._generated_code_timeout(),
                        max_output_bytes=self._generated_message_limit(),
                    )
                    if not validation.ok:
                        raise ValueError(validation.error)
                    self._record_generation(
                        'generator', msg_type,
                        'generated' if failure_count == 0 else 'repaired',
                        failure_count + 1, input_code,
                    )
                    return msg_type, input_code
                except LLMDeadlineExceeded:
                    raise
                except Exception as e:
                    if input_code is not None:
                        failed_code = input_code
                    elif getattr(e, 'response', None):
                        failed_code = e.response
                    failure_error = f'{type(e).__name__}: {e}'
                    failure_count += 1
                    self._record_generation(
                        'generator', msg_type, 'invalid', failure_count,
                        input_code, failure_error,
                    )
                    logger.debug(f'Producer :generate error {str(e)}')
            raise RuntimeError(
                f'generator generation failed for {msg_type} after '
                f'{retry_limit} attempts: {failure_error}'
            )

    async def _generator_gen_async(
        self
    ):
        sem = asyncio.Semaphore(configs.async_sem_fuzz)
        messages = list(self.req_ir.findall("message"))

        async def generate_one(
            message,
        ) -> tuple[str, tuple[str, str] | Exception]:
            msg_type = str(message.get('name') or '')
            try:
                return msg_type, await self._generator_gen_one(message, sem)
            except Exception as error:
                return msg_type, error

        tasks = [generate_one(message) for message in messages]

        generated: list[tuple[str, str]] = []
        failed: dict[str, str] = {}
        deadline_error: LLMDeadlineExceeded | None = None
        for task in tqdm_asyncio.as_completed(
            tasks,
            total=len(tasks),
            desc='generator',
        ):
            msg_type, result = await task
            if isinstance(result, LLMDeadlineExceeded):
                deadline_error = result
                failed[msg_type] = str(result)
            elif isinstance(result, Exception):
                failed[msg_type] = f'{type(result).__name__}: {result}'
            else:
                try:
                    self._save_initial_generator(*result)
                except Exception as error:
                    failure = f'{type(error).__name__}: {error}'
                    failed[msg_type] = failure
                    self._record_generation(
                        'generator',
                        msg_type,
                        'save_failed',
                        0,
                        result[1],
                        failure,
                    )
                    logger.exception(
                        'Producer: failed to save generator for %s',
                        msg_type,
                    )
                    continue
                generated.append(result)

        if deadline_error is not None:
            raise deadline_error
        return generated, failed

    def _save_initial_generator(
        self,
        msg_type: str,
        input_code: str,
    ) -> None:
        """Persist each validated initial generator as soon as it succeeds."""
        msg_dir = self._component_type_dir(self.generator_path, msg_type)
        msg_dir.mkdir(parents=True, exist_ok=True)
        init_gen_path = msg_dir / 'id0.py'
        init_gen_path.write_text(input_code, encoding='utf-8')
        info = {
            'msg_type': msg_type,
            'evolved_from': 'init',
            'name': 'id0',
            'path': str(init_gen_path.resolve()),
        }
        self.generators.setdefault(msg_type, [])
        self.generators[msg_type].append(Generator(**info))

    def _restrict_to_available_generators(
        self,
    ) -> None:
        """Remove unavailable initial request types from downstream inputs."""
        available = {
            msg_type for msg_type, versions in self.generators.items()
            if versions
        }
        self.req_types = set(available)
        self.req_dep = {
            msg_type: {
                dependency: relation
                for dependency, relation in dependencies.items()
                if dependency in available
            }
            for msg_type, dependencies in self.req_dep.items()
            if msg_type in available
        }
        self.poss_response = {
            msg_type: responses
            for msg_type, responses in self.poss_response.items()
            if msg_type in available
        }
        self.rfcp.req_types = set(available)
        self.rfcp.req_dep_map = self.req_dep
        self.rfcp.poss_res = self.poss_response

    def generator_gen(
        self
    ) -> None:
        """Generate and save init input generator
        """

        _, failures = asyncio.run(self._generator_gen_async())

        if not self.generators:
            failure_summary = '; '.join(
                f'{msg_type}: {error}'
                for msg_type, error in sorted(failures.items())
            )
            raise RuntimeError(
                'initial generator generation produced no usable request '
                f'types: {failure_summary or "no request messages"}'
            )

        self._restrict_to_available_generators()
        with open(self.generator_info_path, 'w', encoding='utf-8') as f:
            json.dump(self.generator_info(), f)

        if failures:
            logger.warning(
                'Producer: initial generator generation degraded; '
                f'usable={len(self.generators)} failed={len(failures)} '
                f'types={", ".join(sorted(failures))}'
            )
        else:
            logger.debug("[Producer]: finish generator generation")
        
    async def _generator_evo_one(
        self,
        msg_type: str,
        doc_info:str,
        machine: MealyMachine | None,
        sem,
        trace_hints: set[str] | None = None,
    ):
        """Generate and save evolved input generator for one message type
        
        Attribute:
            msg_type: the message type of generator to be evolved
            doc_info: the document information to be used for generator evolution
            machine: an optional complete model providing state transitions
            trace_hints: concrete partial-learning evidence used before the
                first complete model exists
        """
        generator_versions = self.generators.get(msg_type, [])
        if not generator_versions:
            logger.error(
                'Producer: skipping generator evolution for %s: '
                'no generated baseline exists',
                msg_type,
            )
            return None

        old_generator = generator_versions[-1]
        old_g_name = old_generator.name
        old_g_path = self._component_source_path(
            self.generator_path,
            old_generator,
        )
        if not old_g_path.is_file():
            logger.error(
                'Producer: skipping generator evolution for %s: '
                'baseline is missing at %s',
                msg_type,
                old_g_path,
            )
            return None
        with old_g_path.open('r', encoding='utf-8') as f:
            old_code = f.read()
            
        # extract state trace of request pair which has dependency and the code of related generators 
        code_dep: list[str] = []
        trace_list: set[str] = set(trace_hints or set())
        if msg_type in self.req_dep.keys():
            for last_req, relation in self.req_dep[msg_type].items():
                if machine is not None:
                    trace_list.add(
                        machine.get_relation(last_req, msg_type)
                    )
                dependency_generators = self.generators.get(last_req, [])
                if not dependency_generators:
                    logger.debug(
                        'Producer: dependency generator is unavailable: %s',
                        last_req,
                    )
                    continue
                dependency_generator = dependency_generators[-1]
                code_dep_path = self._component_source_path(
                    self.generator_path,
                    dependency_generator,
                )
                if not code_dep_path.is_file():
                    logger.debug(
                        'Producer: dependency generator source is missing: %s',
                        code_dep_path,
                    )
                    continue
                with code_dep_path.open('r', encoding='utf-8') as f:
                    code_dep.append(f.read())
        # for pair in self.req_dep.keys():
        #     last_request = pair.split('/')[0]
        #     current_request = pair.split('/')[1]
        #     if msg_type == last_request and self.req_dep[pair]['request_dependency'] == 'dependent':
        #         trace_list.add(machine.get_relation(last_request, current_request))
                
        async with sem:
            failure_count = 0
            failed_code: str | None = None
            failure_error = ''
            retry_limit = max(1, getattr(configs, 'generation_retry_limit', 3))
            ir_evolution_attempted = False
            while failure_count < retry_limit:
                input_code: str | None = None
                try:
                    if failed_code is None:
                        input_code = await self.chater.llm_generator_evolve(
                            code=old_code,
                            pro_name=self.rfcp.pro_name,
                            field_name=self.rfcp.req_fields[0],
                            msg_type=msg_type,
                            msg_ir=self._request_ir_info(msg_type),
                            trace='\n'.join(sorted(trace_list)),
                            info=doc_info,
                            related_code='\n'.join(code_dep)
                        )
                    else:
                        input_code = await self.chater.llm_code_repair(
                            code=failed_code,
                            error=failure_error,
                            function_name='generate',
                        )
                    
                    validation = validate_generated_code(
                        input_code,
                        'generate',
                        'generator',
                        timeout_s=self._generated_code_timeout(),
                        max_output_bytes=self._generated_message_limit(),
                    )
                    if not validation.ok:
                        raise ValueError(validation.error)
                    with analyzer.lock:
                        analyzer.finished += 1
                    if not self._evolution_changed(input_code):
                        self._record_generation(
                            'generator_evolution', msg_type, 'no_change',
                            failure_count + 1, input_code,
                            base_sha256=hashlib.sha256(
                                old_code.encode('utf-8')
                            ).hexdigest(),
                            changed=False,
                            reason=self._evolution_reason(input_code),
                        )
                        return msg_type, input_code
                    self._record_generation(
                        'generator_evolution', msg_type,
                        'generated' if failure_count == 0 else 'repaired',
                        failure_count + 1, input_code,
                    )
                    return msg_type, input_code
                except LLMDeadlineExceeded:
                    raise
                except Exception as e:
                    if input_code is not None:
                        failed_code = input_code
                    failure_error = f'{type(e).__name__}: {e}'
                    failure_count += 1
                    self._record_generation(
                        'generator_evolution', msg_type, 'invalid',
                        failure_count, input_code, failure_error,
                    )
                    if failure_count >= getattr(
                        configs,
                        'ir_evolution_failure_threshold',
                        3,
                    ) and not ir_evolution_attempted:
                        await self._maybe_evolve_request_ir(
                            msg_type,
                            (
                                f'generator_evo failed {failure_count} '
                                f'time(s): {type(e).__name__}: {e}'
                            ),
                        )
                        ir_evolution_attempted = True
                    logger.debug(f'Producer: generate error {e}')
            logger.error(
                'Producer: giving up generator evolution for %s after %d attempts',
                msg_type,
                retry_limit,
            )
            return None

    async def _generator_evo_async(
        self,
        doc_info: str,
        machine: MealyMachine | None,
        msg_types: set[str] | None = None,
        trace_hints: dict[str, set[str]] | None = None,
    ):
        sem = asyncio.Semaphore(configs.async_sem_fuzz)
        selected_types = msg_types if msg_types is not None else self.req_types
        hints = trace_hints or {}
        tasks = [
            self._generator_evo_one(
                msg_type=msg_type,
                doc_info=doc_info,
                machine=machine,
                sem=sem,
                trace_hints=hints.get(msg_type),
            )
            for msg_type in selected_types
        ]
        results = await asyncio.gather(*tasks)
        return results

    def _save_evolved_generators(self, results) -> list[str]:
        """Publish locally validated generator evolution results.

        Keep a compact outcome summary for the model-learning recovery path.
        An empty returned type list is otherwise ambiguous: every requested
        generator may have explicitly selected ``no_change``, or every
        synthesis attempt may have failed.  Only the former is a safe no-op.
        """
        evolved_types: list[str] = []
        outcome = {
            'attempted': len(results),
            'changed': 0,
            'no_change': 0,
            'failed': 0,
        }
        for result in results:
            if result is None:
                outcome['failed'] += 1
                continue
            msg_type, input_code = result
            if not self._evolution_changed(input_code):
                outcome['no_change'] += 1
                continue
            outcome['changed'] += 1
            msg_dir = self._component_type_dir(
                self.generator_path,
                msg_type,
            )
            if not msg_dir.is_dir():
                msg_dir.mkdir()

            cur_id = len(self.generators[msg_type])
            gen_path = msg_dir / f'id{cur_id}.py'
            with open(gen_path, 'w', encoding='utf-8') as f:
                f.write(input_code)

            old_name = self.generators[msg_type][-1].name
            new_name = f'id{cur_id}'
            info: dict = {
                'msg_type': msg_type,
                'evolved_from': old_name,
                'name': new_name,
                'path': str(gen_path.resolve()),
            }
            self.generators.setdefault(msg_type, [])
            self.generators[msg_type].append(Generator(**info))
            evolved_types.append(msg_type)

        with open(self.generator_info_path, 'w', encoding='utf-8') as f:
            json.dump(self.generator_info(), f)
        self._last_generator_evolution_outcome = outcome
        return evolved_types

    def generator_evo(
            self,
            machine: MealyMachine
    ) -> list[str]:
        """Evolve and save input generator
        
        Attribute:
            machine: the current MealyMachine which provides the state transition information for generator evolution
        """
        
        with analyzer.lock:
            analyzer.set_progress('evolve', 'evolve', len(self.req_types))
            
        doc_info = ''
        with open(self.info_path, 'r', encoding='utf-8') as f:
            doc_info = f.read()
        
        # produce new generator
        results = asyncio.run(self._generator_evo_async(doc_info, machine))
        evolved_types = self._save_evolved_generators(results)
        
        with analyzer.lock:
            analyzer.clean_progress()
        logger.debug("[Producer]: finish generator generation")
        return evolved_types

    @staticmethod
    def _partial_trace_hints(partial) -> dict[str, set[str]]:
        """Summarize replayed observations without inventing model states."""
        hints: dict[str, set[str]] = {}
        for trace in partial.traces:
            symbols = list(trace.symbols)
            responses = list(trace.responses)
            path = ' -> '.join(symbols)
            output = ' -> '.join(responses)
            summary = f'observed request path: {path}; responses: {output}'
            for symbol in symbols:
                hints.setdefault(symbol, set()).add(summary)
        return hints

    def generator_evo_from_partial(self, partial) -> list[str]:
        """Bootstrap generator evolution from concrete partial MQ evidence.

        This path deliberately passes no fabricated Mealy machine.  It evolves
        only request types with no response pair or a single observed response
        class; well-covered types remain on their current validated version.
        """
        response_counts: dict[str, set[str]] = {
            msg_type: set() for msg_type in self.req_types
        }
        for msg_type, response in partial.request_response_pairs:
            response_counts.setdefault(msg_type, set()).add(response)
        sparse_types = {
            msg_type
            for msg_type in self.req_types
            if len(response_counts.get(msg_type, set())) <= 1
        }
        if not sparse_types:
            # Stagnation may still reflect missing request dependencies rather
            # than per-symbol response variety.  Keep bootstrap capable of
            # making progress by evolving every validated baseline once.
            sparse_types = set(self.req_types)

        with analyzer.lock:
            analyzer.set_progress('evolve', 'evolve', len(sparse_types))

        with open(self.info_path, 'r', encoding='utf-8') as f:
            doc_info = f.read()
        results = asyncio.run(
            self._generator_evo_async(
                doc_info,
                machine=None,
                msg_types=sparse_types,
                trace_hints=self._partial_trace_hints(partial),
            )
        )
        evolved_types = self._save_evolved_generators(results)
        with analyzer.lock:
            analyzer.clean_progress()
        logger.debug(
            '[Producer]: finish partial bootstrap generator evolution'
        )
        return evolved_types
                
    async def _generator_mutate_one(
        self,
        msg_type: str,
        doc_info: str,
        req_res: dict[str, set],
        sem
    ):
        """Generate and save evolved input mutator for one message type
        
        Attribute:
            msg_type: the message type of mutator to be evolved
            doc_info: the document information to be used for mutator evolution
            req_res: the actual response for each request message, which provides the information for mutator evolution
        """
        best_generators = getattr(self, 'best_generators', {})
        old_m = best_generators.get(msg_type)
        if hasattr(self, 'generator_path'):
            source_root = getattr(
                self, 'best_generator_path', self.generator_path
            )
            if old_m is None:
                old_m = self.generators[msg_type][-1]
                source_root = self.generator_path
            old_m_path = self._component_source_path(source_root, old_m)
        else:
            # Lightweight unit-test construction predates equipment roots.
            # A fully initialized producer always takes the scoped branch.
            old_m = old_m or self.generators[msg_type][-1]
            old_m_path = Path(old_m.path)
        if not old_m_path.is_file():
            raise FileNotFoundError(
                'generator baseline is missing from its active equipment '
                f'root: {old_m_path}'
            )
        old_code = ''
        with open(old_m_path, 'r', encoding='utf-8') as f:
            old_code = f.read()

        response_coverage = self._mutator_response_coverage(
            self.poss_response.get(msg_type, []),
            req_res.get(msg_type, set()),
        )
        possible_responses = response_coverage['possible']
        observed_responses = response_coverage['observed']
        missing_responses = response_coverage['missing']
                
        async with sem:
            retry_limit = max(1, getattr(configs, 'generation_retry_limit', 3))
            failure_count = 0
            failed_code: str | None = None
            failure_error = ''
            while failure_count < retry_limit:
                mutate_code: str | None = None
                try:
                    if failed_code is None:
                        mutate_code = await self.chater.llm_mutator_evolve(
                            code=old_code,
                            pro_name=self.rfcp.pro_name,
                            field_name=self.rfcp.req_fields[0],
                            msg_type=msg_type,
                            msg_ir=self._request_ir_info(msg_type),
                            info=doc_info,
                            poss_response='\n'.join(
                                possible_responses
                            ),
                            trace=json.dumps(
                                observed_responses,
                                ensure_ascii=False,
                            ),
                            missing_response=json.dumps(
                                missing_responses,
                                ensure_ascii=False,
                            ),
                        )
                    else:
                        mutate_code = await self.chater.llm_code_repair(
                            code=failed_code,
                            error=failure_error,
                            function_name='mutate',
                        )

                    if not self._evolution_changed(mutate_code):
                        baseline_validation = validate_generated_code(
                            mutate_code,
                            'generate',
                            'generator',
                            timeout_s=self._generated_code_timeout(),
                            max_output_bytes=self._generated_message_limit(),
                        )
                        if not baseline_validation.ok:
                            raise ValueError(baseline_validation.error)
                        with analyzer.lock:
                            analyzer.finished += 1
                        self._record_generation(
                            'mutator', msg_type, 'no_change',
                            failure_count + 1, mutate_code,
                            base_sha256=hashlib.sha256(
                                old_code.encode('utf-8')
                            ).hexdigest(),
                            changed=False,
                            reason=self._evolution_reason(mutate_code),
                            response_coverage=response_coverage,
                        )
                        return None

                    # berserker_code = await self.chater.llm_mutator_berserker(
                    #     code=old_code,
                    #     pro_name=self.rfcp.pro_name,
                    #     msg_type=msg_type,
                    #     info=doc_info
                    # )
                    
                    validation = validate_generated_code(
                        mutate_code,
                        'mutate',
                        'mutator',
                        timeout_s=self._generated_code_timeout(),
                        max_output_bytes=self._generated_message_limit(),
                    )
                    if not validation.ok:
                        raise ValueError(validation.error)
                    # exec(berserker_code, name_space)
                    # obj = name_space[f'berserker_{msg_type}']
                    # obj()
                    with analyzer.lock:
                        analyzer.finished += 1
                    self._record_generation(
                        'mutator',
                        msg_type,
                        'generated' if failure_count == 0 else 'repaired',
                        failure_count + 1,
                        mutate_code,
                        response_coverage=response_coverage,
                    )
                    return msg_type, mutate_code
                except LLMDeadlineExceeded as error:
                    failure_error = f'llm_transport_timeout: {error}'
                    self._record_generation(
                        'mutator', msg_type, 'fallback', failure_count + 1,
                        mutate_code, failure_error,
                        response_coverage=response_coverage,
                    )
                    break
                except CandidateSourceValidationError as error:
                    # The delta itself was valid and produced this source;
                    # retain it so repair receives the exact missing-entry or
                    # syntax failure instead of repeating the original prompt.
                    mutate_code = error.candidate_source
                    failed_code = mutate_code
                    failure_error = f'{type(error).__name__}: {error}'
                    failure_count += 1
                    self._record_generation(
                        'mutator', msg_type, 'invalid', failure_count,
                        mutate_code, failure_error,
                        response_coverage=response_coverage,
                    )
                    logger.exception('Producer: mutator candidate failed validation')
                except Exception as error:
                    if mutate_code is not None:
                        failed_code = mutate_code
                    failure_error = f'{type(error).__name__}: {error}'
                    failure_count += 1
                    self._record_generation(
                        'mutator', msg_type, 'invalid', failure_count,
                        mutate_code, failure_error,
                        response_coverage=response_coverage,
                    )
                    logger.exception('Producer: mutator generation failed')
            logger.error(
                'Producer: falling back to the best generator for %s after %d attempts',
                msg_type,
                failure_count,
            )
            return None

    async def _generator_mutate_async(
        self,
        doc_info: str,
        req_res: dict[str, set],
        mutated_types: list[str] | None = None
    ) -> list[tuple[str, str] | None]:
        sem = asyncio.Semaphore(configs.async_sem_fuzz)
        req_types = (
            sorted(self.req_types)
            if mutated_types is None
            else mutated_types
        )
        tasks = [
            self._generator_mutate_one(msg_type=msg_type, doc_info=doc_info, req_res=req_res, sem=sem)
            for msg_type in req_types
        ]
        results = await asyncio.gather(*tasks)
        return results

    def _select_generator_mutate_types(self) -> list[str]:
        """Select the request types to mutate in one generator-mutation round."""
        req_types = sorted(self.req_types)
        if not req_types:
            return []

        configured_limit = getattr(configs, 'async_sem_fuzz', len(req_types))
        ratio = float(getattr(configs, 'mutator_round_ratio', 0.25))
        ratio_limit = math.ceil(len(req_types) * ratio)
        limit = max(1, min(configured_limit, ratio_limit, len(req_types)))
        cursor = getattr(self, '_generator_mutate_cursor', 0) % len(req_types)
        selected = [
            req_types[(cursor + offset) % len(req_types)]
            for offset in range(limit)
        ]
        self._generator_mutate_cursor = (cursor + limit) % len(req_types)
        return selected

    def generator_mutate(
        self,
        req_res,
        iteration: int | None = None,
    ) -> list[str]:
        """Generate and save input mutator
        
        Attribute:
            req_res: the actual response for each request message, which provides the information for mutator
        """
        mutated_types = self._select_generator_mutate_types()
        checkpoint_iteration = analyzer.iter if iteration is None else iteration
        analyzer.record_generator_checkpoint(
            phase='fuzzing',
            checkpoint_type='before_generator_mutate',
            phase_iteration=checkpoint_iteration,
            operation_id=f'mutate-{checkpoint_iteration}',
            mutated_types=mutated_types,
        )
        with analyzer.lock:
            analyzer.set_progress('evolve', 'mutate', len(mutated_types))
           
        doc_info = ''
        with open(self.info_path, 'r', encoding='utf-8') as f:
            doc_info = f.read()
        
        # produce new mutator
        results = asyncio.run(
            self._generator_mutate_async(
                doc_info,
                req_res,
                mutated_types=mutated_types,
            )
        )
        
        # resolve mutator
        evolved_types: list[str] = []
        for result in results:
            if result is None:
                continue
            msg_type, mutate_code = result
            msg_dir = self._component_type_dir(
                self.mutator_path,
                msg_type,
            )
            if not msg_dir.is_dir():
                msg_dir.mkdir()
            
            # save mutator
            cur_id = None
            if msg_type in self.mutators.keys():
                cur_id = len(self.mutators[msg_type])
            else:
                cur_id = 0
            mut_path = msg_dir / f'id{cur_id}.py'
            with open(mut_path, 'w', encoding='utf-8') as f:
                f.write(mutate_code)
                # f.write('\n\n')
                # f.write(berserker_code)
                
                # construct and save information for new generator
                old_name = self.generators[msg_type][0].name
                new_name = f'id{cur_id}'
                info: dict = {'msg_type': f'{msg_type}', 'evolved_from': old_name, 'name': new_name, 'path': str(mut_path.resolve())}
                
                # set mutator name as {msg_type}
                self.mutators.setdefault(msg_type, [])
                self.mutators[msg_type].append(Generator(**info))
                evolved_types.append(msg_type)
                
        # save the information of new generator to file   
        with open(self.mutator_info_path, 'w', encoding='utf-8') as f:
            json.dump(self.mutator_info(), f)
        
        with analyzer.lock:
            analyzer.clean_progress()
        logger.debug("[Producer]: finish mutator generation")
        return evolved_types

    async def _parser_gen_async(
            self
    ):
        res_info = self._primary_response_field_info()
        runtime_samples = self._parser_validation_samples()
        failed_code: str | None = None
        failure_error = ''
        retry_limit = max(1, getattr(configs, 'generation_retry_limit', 3))
        failure_count = 0
        while failure_count < retry_limit:
            pkt_parser_code: str | None = None
            try:
                if failed_code is None:
                    pkt_parser_code = await self.chater.llm_parser_gen(
                        pro_name=self.rfcp.pro_name,
                        res_info=res_info,
                    )
                else:
                    pkt_parser_code = await self.chater.llm_code_repair(
                        code=failed_code,
                        error=failure_error,
                        function_name='packet_parser',
                    )
                validation = validate_generated_code(
                    pkt_parser_code,
                    'packet_parser',
                    'parser',
                    timeout_s=self._generated_code_timeout(),
                    runtime_samples=runtime_samples,
                    require_nonempty_samples=bool(runtime_samples),
                )
                if not validation.ok:
                    raise ValueError(
                        self._parser_validation_failure(
                            validation.error,
                            runtime_samples,
                        )
                    )
                self._record_generation(
                    'parser', '__all__',
                    'generated' if failure_count == 0 else 'repaired',
                    failure_count + 1, pkt_parser_code,
                )
                return pkt_parser_code
            except LLMDeadlineExceeded:
                raise
            except Exception as e:
                if pkt_parser_code is not None:
                    failed_code = pkt_parser_code
                elif getattr(e, 'response', None):
                    failed_code = e.response
                failure_error = f'{type(e).__name__}: {e}'
                failure_count += 1
                self._record_generation(
                    'parser', '__all__', 'invalid', failure_count,
                    pkt_parser_code, failure_error,
                )
                logger.debug(f'[Parser Generation]: invalid parser {e}')
        raise RuntimeError(
            f'parser generation failed after {retry_limit} attempts: '
            f'{failure_error}'
        )
                
    def parser_gen(
            self
    ) -> None:
        """Generate and save packet parser
        """
        with tqdm(desc='Parser Gen', total=1) as pbar:
            result = asyncio.run(self._parser_gen_async())
            pbar.update(1)
        init_p_path = self.parser_path / 'id0.py'
        with open(init_p_path, 'w', encoding='utf-8') as f:
            f.write(result)
            info: dict = {
                'evolved_from': 'init',
                'name': 'id0',
                'state_field': self._primary_response_field_name()
            }
            self.parsers.append(Parser(**info))
        with open(self.parser_info_path, 'w', encoding='utf-8') as f:
            json.dump(self.parser_info(), f)
        logger.debug("[Producer]: finish parser generation")

    async def _checker_gen_one(
            self,
            response_type: str,
            msg,
            res_info: str,
            sem: asyncio.Semaphore
    ) -> tuple[str, str]:
        msg_ir = etree.tostring(
            msg,
            encoding='utf-8',
            pretty_print=True
        ).decode('utf-8')

        async with sem:
            retry_limit = max(1, getattr(configs, 'generation_retry_limit', 3))
            failure_count = 0
            while failure_count < retry_limit:
                checker_code: str | None = None
                try:
                    checker_code = await self.chater.llm_checker_gen(
                        pro_name=self.rfcp.pro_name,
                        msg_ir=msg_ir,
                        res_info=res_info,
                        response_type=response_type,
                        type_rule=self._response_type_rule_info(response_type),
                    )
                    validation = validate_generated_code(
                        checker_code,
                        'packet_checker',
                        'checker',
                        timeout_s=self._generated_code_timeout(),
                    )
                    if not validation.ok:
                        raise ValueError(validation.error)
                    self._record_generation(
                        'checker', response_type, 'generated',
                        failure_count + 1, checker_code,
                    )
                    return response_type, checker_code
                except Exception as e:
                    failure_count += 1
                    self._record_generation(
                        'checker', response_type, 'invalid', failure_count,
                        checker_code,
                        f'{type(e).__name__}: {e}',
                    )
                    logger.debug(
                        f'[Checker Generation][{response_type}]: '
                        f'invalid checker {e}'
                    )
            logger.error(
                'Producer: giving up checker generation for %s after %d attempts',
                response_type,
                retry_limit,
            )
            return None

    async def _checker_gen_async(
            self,
            response_types: list[str] | None = None,
    ) -> list[tuple[str, str] | None]:
        if not hasattr(self, 'res_ir'):
            raise RuntimeError('Response IR is unavailable for checker generation')

        messages = self.res_ir.findall('message')
        if not messages:
            raise RuntimeError('Response IR does not contain any messages')

        response_types = (
            response_types
            if response_types is not None
            else self._initial_response_component_types()
        )
        res_info = self._primary_response_field_info()
        sem = asyncio.Semaphore(configs.async_sem_fuzz)
        tasks = [
            self._checker_gen_one(
                response_type,
                self._checker_ir_for_response_type(
                    response_type,
                    messages
                ),
                res_info,
                sem
            )
            for response_type in response_types
        ]
        return await tqdm_asyncio.gather(*tasks, desc='checker')

    def checker_gen(
            self,
            response_types: list[str] | None = None,
    ) -> None:
        """Generate and persist missing response checkers."""
        response_types = list(dict.fromkeys(
            response_types
            if response_types is not None
            else self._initial_response_component_types()
        ))
        if not response_types:
            return
        results = asyncio.run(self._checker_gen_async(response_types))

        with self._response_components_lock():
            for result in results:
                if result is None:
                    continue
                msg_type, checker_code = result
                if self.checkers.get(msg_type):
                    continue
                msg_dir = self._component_type_dir(
                    self.checker_path,
                    msg_type,
                )
                msg_dir.mkdir(parents=True, exist_ok=True)
                checker_path = msg_dir / 'id0.py'
                with open(checker_path, 'w', encoding='utf-8') as f:
                    f.write(checker_code)

                checker = Checker(
                    msg_type=msg_type,
                    evolved_from='init',
                    name='id0',
                    path=str(checker_path.resolve()),
                    state_field=self._primary_response_field_name(),
                    contract_version=(
                        self.RESPONSE_COMPONENT_CONTRACT_VERSION
                    ),
                    ir_sha256=self._response_component_ir_sha256(msg_type),
                )
                self.checkers.setdefault(msg_type, []).append(checker)

            with open(self.checker_info_path, 'w', encoding='utf-8') as f:
                json.dump(self.checker_info(), f)

        logger.debug("[Producer]: finish checkers generation")

    async def _observer_gen_one(
        self,
        response_type: str,
        msg,
        res_info: str,
        sem: asyncio.Semaphore
    ) -> tuple[str, str]:
        msg_ir = etree.tostring(
            msg,
            encoding='utf-8',
            pretty_print=True,
        ).decode('utf-8')
        async with sem:
            retry_limit = max(1, getattr(configs, 'generation_retry_limit', 3))
            failure_count = 0
            failed_code: str | None = None
            failure_error = ''
            while failure_count < retry_limit:
                observer_code: str | None = None
                try:
                    if failed_code is None:
                        observer_code = await self.chater.llm_observer_gen(
                            pro_name=self.rfcp.pro_name,
                            msg_ir=msg_ir,
                            res_info=res_info,
                            response_type=response_type,
                        )
                    else:
                        observer_code = await self.chater.llm_code_repair(
                            code=failed_code,
                            error=failure_error,
                            function_name='packet_observer',
                        )
                    validation = validate_generated_code(
                        observer_code,
                        'packet_observer',
                        'observer',
                        timeout_s=self._generated_code_timeout(),
                    )
                    if not validation.ok:
                        raise ValueError(validation.error)
                    self._record_generation(
                        'observer',
                        response_type,
                        'generated' if failure_count == 0 else 'repaired',
                        failure_count + 1,
                        observer_code,
                    )
                    return response_type, observer_code
                except LLMDeadlineExceeded as error:
                    failure_error = f'llm_transport_timeout: {error}'
                    self._record_generation(
                        'observer', response_type, 'invalid', failure_count + 1,
                        observer_code, failure_error,
                    )
                    break
                except Exception as error:
                    if observer_code is not None:
                        failed_code = observer_code
                    failure_error = f'{type(error).__name__}: {error}'
                    failure_count += 1
                    self._record_generation(
                        'observer', response_type, 'invalid', failure_count,
                        observer_code, failure_error,
                    )
                    logger.exception(
                        f'Producer: invalid observer [{response_type}]'
                    )
            self._record_generation(
                'observer', response_type, 'fallback_raw_sha256',
                failure_count, RAW_SHA256_OBSERVER, failure_error,
            )
            logger.warning(
                'Producer: using raw SHA-256 observer fallback for %s',
                response_type,
            )
            return response_type, RAW_SHA256_OBSERVER

    async def _observer_gen_async(
        self,
        response_types: list[str] | None = None,
    ) -> list[tuple[str, str] | None]:
        if not hasattr(self, 'res_ir'):
            raise RuntimeError('Response IR is unavailable for observer generation')
        messages = self.res_ir.findall('message')
        if not messages:
            raise RuntimeError('Response IR does not contain any messages')
        response_types = (
            response_types
            if response_types is not None
            else self._initial_response_component_types()
        )
        res_info = self._primary_response_field_info()
        sem = asyncio.Semaphore(configs.async_sem_fuzz)
        tasks = [
            self._observer_gen_one(
                response_type,
                self._checker_ir_for_response_type(response_type, messages),
                res_info,
                sem,
            )
            for response_type in response_types
        ]
        return await tqdm_asyncio.gather(*tasks, desc='observer')

    def observer_gen(
        self,
        response_types: list[str] | None = None,
    ) -> None:
        """Generate and persist missing semantic response observers."""
        if not getattr(configs, 'observer_enabled', True):
            logger.debug('Producer: observer generation disabled')
            return
        response_types = list(dict.fromkeys(
            response_types
            if response_types is not None
            else self._initial_response_component_types()
        ))
        if not response_types:
            return
        results = asyncio.run(self._observer_gen_async(response_types))
        with self._response_components_lock():
            for result in results:
                if result is None:
                    continue
                msg_type, observer_code = result
                if self.observers.get(msg_type):
                    continue
                msg_dir = self._component_type_dir(
                    self.observer_path,
                    msg_type,
                )
                msg_dir.mkdir(parents=True, exist_ok=True)
                observer_path = msg_dir / 'id0.py'
                with observer_path.open('w', encoding='utf-8') as f:
                    f.write(observer_code)
                observer = ResponseObserver(
                    msg_type=msg_type,
                    name='id0',
                    path=str(observer_path.resolve()),
                    state_field=self._primary_response_field_name(),
                    contract_version=(
                        self.RESPONSE_COMPONENT_CONTRACT_VERSION
                    ),
                    ir_sha256=self._response_component_ir_sha256(msg_type),
                    evolved_from='init',
                )
                self.observers.setdefault(msg_type, []).append(observer)
            with self.observer_info_path.open('w', encoding='utf-8') as f:
                json.dump(self.observer_info(), f, indent=2)
        logger.debug("[Producer]: finish observers generation")

    def evolve_observer(
        self,
        response_type: str,
        samples: list[bytes]
    ) -> ResponseObserver | None:
        """Evolve a response observer so same-type historical samples converge."""
        if not getattr(configs, 'observer_enabled', True):
            logger.debug('Producer: observer evolution disabled')
            return None
        versions = self.observers.get(response_type)
        if not versions:
            logger.debug(
                f'Producer: no observer metadata to evolve [{response_type}]'
            )
            return None
        current = versions[-1]
        current_path = self._component_source_path(
            self.observer_path,
            current,
        )
        if not current_path.is_file():
            logger.debug(
                f'Producer: observer source missing for evolution {current_path}'
            )
            return None

        messages = self.res_ir.findall('message')
        msg = self._checker_ir_for_response_type(response_type, messages)
        msg_ir = etree.tostring(
            msg,
            encoding='utf-8',
            pretty_print=True,
        ).decode('utf-8')
        with current_path.open('r', encoding='utf-8') as f:
            original_code = f.read()

        unique_samples = list(dict.fromkeys(samples))
        observer_code = asyncio.run(
            self._observer_evolve_async(
                response_type,
                msg_ir,
                original_code,
                unique_samples,
            )
        )
        if observer_code is None:
            return None

        numeric_ids = [
            int(observer.name[2:])
            for observer in versions
            if observer.name.startswith('id') and observer.name[2:].isdigit()
        ]
        name = f'id{max(numeric_ids, default=-1) + 1}'
        target_dir = self._component_type_dir(
            self.observer_path,
            response_type,
        )
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / f'{name}.py'
        with target_path.open('w', encoding='utf-8') as f:
            f.write(observer_code)

        evolved = ResponseObserver(
            msg_type=response_type,
            name=name,
            path=str(target_path.resolve()),
            state_field=current.state_field,
            contract_version=current.contract_version,
            ir_sha256=current.ir_sha256,
            evolved_from=current.name,
            sample_observations=[
                hashlib.sha256(sample).hexdigest()
                for sample in unique_samples
            ],
        )
        versions.append(evolved)
        with self.observer_info_path.open('w', encoding='utf-8') as f:
            json.dump(self.observer_info(), f, indent=2)
        logger.debug(
            f'Producer: evolved observer [{response_type}] '
            f'{current.name} -> {name}'
        )
        return evolved

    def responses_semantically_equivalent(
        self,
        response_type: str,
        old_response: bytes,
        new_response: bytes
    ) -> bool:
        """Use the response IR and LLM to gate observer evolution."""
        try:
            messages = self.res_ir.findall('message')
            msg = self._checker_ir_for_response_type(
                response_type,
                messages,
            )
            msg_ir = etree.tostring(
                msg,
                encoding='utf-8',
                pretty_print=True,
            ).decode('utf-8')
            result = asyncio.run(
                self.chater.llm_observer_semantic_compare(
                    pro_name=self.rfcp.pro_name,
                    response_type=response_type,
                    msg_ir=msg_ir,
                    old_response=old_response,
                    new_response=new_response,
                )
            )
            analysis = json.loads(result)
            confidence = analysis.get('confidence', 0.0)
            equivalent = (
                analysis.get('semantic_equivalent') is True
                and isinstance(confidence, (int, float))
                and confidence >= 0.8
            )
            logger.debug(
                'Producer: observer semantic comparison '
                f'[{response_type}] equivalent={equivalent} '
                f'confidence={confidence} '
                f'reason={analysis.get("reason", "")}'
            )
            return equivalent
        except Exception:
            logger.exception(
                f'Producer: observer semantic comparison failed '
                f'[{response_type}]'
            )
            return False

    async def _observer_evolve_async(
        self,
        response_type: str,
        msg_ir: str,
        original_code: str,
        samples: list[bytes]
    ) -> str | None:
        sample_info = json.dumps([
            {
                'raw_sha256': hashlib.sha256(sample).hexdigest(),
                'length': len(sample),
                'repr': repr(sample),
            }
            for sample in samples
        ], indent=2)
        failed_code: str | None = None
        failure_error = ''
        retry_limit = max(1, getattr(configs, 'generation_retry_limit', 3))
        for failure_count in range(retry_limit):
            code: str | None = None
            try:
                if failed_code is None:
                    code = await self.chater.llm_observer_evolve(
                        pro_name=self.rfcp.pro_name,
                        response_type=response_type,
                        msg_ir=msg_ir,
                        original_code=original_code,
                        samples=sample_info,
                    )
                else:
                    code = await self.chater.llm_code_repair(
                        code=failed_code,
                        error=failure_error,
                        function_name='packet_observer',
                    )
                if not self._evolution_changed(code):
                    baseline_validation = validate_generated_code(
                        code,
                        'packet_observer',
                        'observer',
                        timeout_s=self._generated_code_timeout(),
                        observer_samples=tuple(samples),
                        require_equal_observations=True,
                    )
                    outcome = (
                        'no_change'
                        if baseline_validation.ok
                        else 'no_change_unresolved'
                    )
                    self._record_generation(
                        'observer_evolution', response_type, outcome,
                        failure_count + 1, code,
                        error='' if baseline_validation.ok else baseline_validation.error,
                        base_sha256=hashlib.sha256(
                            original_code.encode('utf-8')
                        ).hexdigest(),
                        changed=False,
                        reason=self._evolution_reason(code),
                    )
                    return None
                validation = validate_generated_code(
                    code,
                    'packet_observer',
                    'observer',
                    timeout_s=self._generated_code_timeout(),
                    observer_samples=tuple(samples),
                    require_equal_observations=True,
                )
                if not validation.ok:
                    raise ValueError(validation.error)
                self._record_generation(
                    'observer_evolution', response_type,
                    'generated' if failure_count == 0 else 'repaired',
                    failure_count + 1, code,
                )
                return code
            except LLMDeadlineExceeded as error:
                failure_error = f'llm_transport_timeout: {error}'
                self._record_generation(
                    'observer_evolution', response_type, 'invalid',
                    failure_count + 1, code, failure_error,
                )
                break
            except Exception as error:
                if code is not None:
                    failed_code = code
                failure_error = f'{type(error).__name__}: {error}'
                self._record_generation(
                    'observer_evolution', response_type, 'invalid',
                    failure_count + 1, code, failure_error,
                )
                logger.exception(
                    f'Producer: observer evolution failed [{response_type}]'
                )
        self._record_generation(
            'observer_evolution', response_type, 'keep_previous',
            retry_limit, original_code, failure_error,
        )
        return None

    @staticmethod
    def _observer_callable(namespace: dict) -> Callable | None:
        return namespace.get('packet_observer') or namespace.get('packet_hasher')

    @staticmethod
    def _valid_digest(digest) -> bool:
        return (
            isinstance(digest, str)
            and len(digest) == 64
            and digest == digest.lower()
            and all(char in '0123456789abcdef' for char in digest)
        )

    def review_nonconforming_response(
        self,
        request_type: str,
        response_type: str,
        request: bytes,
        response: bytes
    ) -> dict:
        """Use relevant response sections to distinguish bugs from checker errors."""
        if self._response_sections is None:
            self._response_sections = collect_response_sections(
                self.rfcp.tree_dict
            )
        if not self._response_sections:
            return {
                'verdict': 'uncertain',
                'confidence': 0.0,
                'summary': 'No annotated response sections are available.',
                'violations': [],
                'evidence': [],
            }

        retrieved = retrieve_response_sections(
            self._response_sections,
            request_type,
            response_type,
            request,
            response,
        )
        prompt = build_compliance_prompt(
            protocol=self.rfcp.pro_name,
            request_type=request_type,
            response_type=response_type,
            request=request,
            response=response,
            retrieved=retrieved,
        )
        model_response = asyncio.run(
            self.chater.chat_llm(
                prompt=prompt,
                usage='checker_non_compliance_review',
            )
        )
        analysis = parse_compliance_result(model_response)
        analysis['retrieved_sections'] = [
            {
                'rfc': section.rfc,
                'section': section.section,
                'content_type': section.content_type,
                'bm25_score': score,
            }
            for section, score in retrieved
        ]
        return analysis

    def evolve_checker(
        self,
        response_type: str,
        response: bytes,
        analysis: dict
    ) -> Checker | None:
        """Generate and persist a checker version that accepts a false positive."""
        checker_type = response_type
        if not self.checkers.get(checker_type):
            checker_type = '__all__'
        versions = self.checkers.get(checker_type)
        if not versions:
            logger.debug(
                f'Producer: no checker metadata to evolve [{response_type}]'
            )
            return None

        current = versions[-1]
        checker_path = self._component_source_path(
            self.checker_path,
            current,
        )
        if not checker_path.is_file():
            logger.debug(
                f'Producer: checker source missing for evolution {checker_path}'
            )
            return None

        with checker_path.open('r', encoding='utf-8') as f:
            original_code = f.read()

        checker_code = asyncio.run(
            self._checker_evolve_async(
                response_type=response_type,
                original_code=original_code,
                response=response,
                analysis=analysis,
            )
        )
        if checker_code is None:
            return None

        numeric_ids = [
            int(checker.name[2:])
            for checker in versions
            if checker.name.startswith('id') and checker.name[2:].isdigit()
        ]
        name = f'id{max(numeric_ids, default=-1) + 1}'
        target_dir = self._component_type_dir(
            self.checker_path,
            checker_type,
        )
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / f'{name}.py'
        with target_path.open('w', encoding='utf-8') as f:
            f.write(checker_code)

        response_digest = hashlib.sha256(response).hexdigest()
        evolved = Checker(
            msg_type=checker_type,
            evolved_from=current.name,
            name=name,
            path=str(target_path.resolve()),
            state_field=current.state_field,
            contract_version=current.contract_version,
            ir_sha256=current.ir_sha256,
            checked_res=list(dict.fromkeys(
                [*current.checked_res, response_digest]
            )),
        )
        versions.append(evolved)
        with self.checker_info_path.open('w', encoding='utf-8') as f:
            json.dump(self.checker_info(), f, indent=2)
        logger.debug(
            f'Producer: evolved checker [{checker_type}] '
            f'{current.name} -> {name}'
        )
        return evolved

    async def _checker_evolve_async(
        self,
        response_type: str,
        original_code: str,
        response: bytes,
        analysis: dict
    ) -> str | None:
        review_summary = json.dumps(analysis, ensure_ascii=False)
        for _ in range(3):
            try:
                checker_code = await self.chater.llm_checker_evolve(
                    pro_name=self.rfcp.pro_name,
                    response_type=response_type,
                    original_code=original_code,
                    response=response,
                    review_summary=review_summary,
                )
                if not self._evolution_changed(checker_code):
                    baseline_validation = validate_generated_code(
                        checker_code,
                        'packet_checker',
                        'checker',
                        timeout_s=self._generated_code_timeout(),
                    )
                    accepted = False
                    if baseline_validation.ok:
                        namespace = {}
                        exec(checker_code, namespace)
                        checker_func = namespace['packet_checker']
                        accepted = checker_func(response) is True
                    outcome = (
                        'no_change'
                        if baseline_validation.ok and accepted
                        else 'no_change_unresolved'
                    )
                    self._record_generation(
                        'checker_evolution', response_type, outcome, 1,
                        checker_code,
                        error=(
                            '' if outcome == 'no_change'
                            else (
                                baseline_validation.error
                                if not baseline_validation.ok
                                else 'current checker still rejects reviewed response'
                            )
                        ),
                        base_sha256=hashlib.sha256(
                            original_code.encode('utf-8')
                        ).hexdigest(),
                        changed=False,
                        reason=self._evolution_reason(checker_code),
                    )
                    return None
                compile(checker_code, '<checker_evolve>', 'exec')
                namespace = {}
                exec(checker_code, namespace)
                checker_func = namespace.get('packet_checker')
                if not callable(checker_func):
                    raise TypeError(
                        'packet_checker is missing or not callable'
                    )
                result = checker_func(response)
                if result is not True:
                    raise ValueError(
                        'evolved checker still rejects reviewed response'
                    )
                probe = checker_func(b'')
                if not isinstance(probe, bool):
                    raise TypeError('packet_checker must return bool')
                return checker_code
            except Exception:
                logger.exception(
                    f'Producer: checker evolution failed [{response_type}]'
                )
        return None

    def _response_components_lock(self) -> threading.RLock:
        lock = getattr(self, '_response_component_lock', None)
        if lock is None:
            lock = threading.RLock()
            self._response_component_lock = lock
        return lock

    @staticmethod
    def response_family(response_type: str) -> str | None:
        """Return a stable protocol response-family key when one is evident."""
        match = re.search(r'(?<!\d)([1-5])\d{2}(?!\d)', response_type)
        if match is None:
            return None
        return f'{match.group(1)}xx'

    def response_component_candidates(
        self,
        response_type: str,
    ) -> list[str]:
        """Return exact, family, then protocol-wide component keys."""
        candidates = [response_type]
        family = self.response_family(response_type)
        if family is not None and family != response_type:
            candidates.append(family)
        candidates.append('__all__')
        return list(dict.fromkeys(candidates))

    def _initial_response_component_types(self) -> list[str]:
        """Select the bounded set prepared before network fuzzing starts."""
        if not getattr(configs, 'response_component_lazy_generation', True):
            return self._response_types_from_primary_field()
        configured = getattr(
            configs,
            'response_component_prewarm_types',
            [],
        )
        known = set(self._response_types_from_primary_field())
        prewarm = [
            str(item).strip()
            for item in configured
            if str(item).strip() in known
        ]
        return list(dict.fromkeys(['__all__', *prewarm]))

    def _missing_checker_types(self, response_types: list[str]) -> list[str]:
        state_field = self._primary_response_field_name()
        missing = []
        for item in response_types:
            versions = self.checkers.get(item, [])
            if versions and self._response_component_metadata_current(
                versions[-1], item, state_field
            ):
                continue
            self.checkers.pop(item, None)
            missing.append(item)
        return missing

    def _missing_observer_types(self, response_types: list[str]) -> list[str]:
        state_field = self._primary_response_field_name()
        missing = []
        for item in response_types:
            versions = self.observers.get(item, [])
            if versions and self._response_component_metadata_current(
                versions[-1], item, state_field
            ):
                continue
            self.observers.pop(item, None)
            missing.append(item)
        return missing

    def _response_component_ir_sha256(self, response_type: str) -> str:
        messages = self.res_ir.findall('message')
        selected = self._checker_ir_for_response_type(response_type, messages)
        digest = hashlib.sha256()
        digest.update(etree.tostring(selected, encoding='utf-8'))
        digest.update(b'\0')
        digest.update(
            self._primary_response_field_info().encode('utf-8')
        )
        digest.update(b'\0')
        digest.update(
            self._response_type_rule_info(response_type).encode('utf-8')
        )
        return digest.hexdigest()

    def _response_component_metadata_current(
        self,
        component: Checker | ResponseObserver,
        response_type: str,
        state_field: str | None = None,
    ) -> bool:
        return (
            component.state_field == (
                state_field or self._primary_response_field_name()
            )
            and component.contract_version == (
                self.RESPONSE_COMPONENT_CONTRACT_VERSION
            )
            and component.ir_sha256 == self._response_component_ir_sha256(
                response_type
            )
        )

    def request_response_components(self, response_type: str) -> None:
        """Queue missing exact/family components without blocking fuzzing."""
        if response_type.upper() in {
            'UNKNOWN', 'UNKOWN', 'TIMEOUT', 'CRASH', 'CLOSED', 'RCLOSED',
            'POLLERR',
        }:
            return
        if (
            not getattr(configs, 'spec_knowledge', True)
            or not getattr(configs, 'response_component_lazy_generation', True)
        ):
            return
        keys = self.response_component_candidates(response_type)[:-1]
        with self._response_components_lock():
            if not hasattr(self, '_response_component_pending'):
                self._response_component_pending = set()
            if not hasattr(self, '_response_component_failures'):
                self._response_component_failures = set()
            if not hasattr(self, '_response_component_queue'):
                self._response_component_queue = queue.Queue()
            for key in keys:
                checker_missing = bool(self._missing_checker_types([key]))
                observer_missing = (
                    bool(self._missing_observer_types([key]))
                    if getattr(configs, 'observer_enabled', True)
                    else False
                )
                if (
                    not checker_missing
                    and not observer_missing
                ) or key in self._response_component_pending or key in (
                    self._response_component_failures
                ):
                    continue
                self._response_component_pending.add(key)
                self._response_component_queue.put(key)
            worker = getattr(self, '_response_component_worker', None)
            if self._response_component_pending and (
                worker is None or not worker.is_alive()
            ):
                self._response_component_worker = threading.Thread(
                    target=self._response_component_worker_main,
                    name='voltron-response-components',
                    daemon=True,
                )
                self._response_component_worker.start()

    def _response_component_worker_main(self) -> None:
        """Generate queued components serially to keep cache writes coherent."""
        while True:
            failed = False
            try:
                response_type = self._response_component_queue.get_nowait()
            except queue.Empty:
                return
            try:
                if not self.checkers.get(response_type):
                    self.checker_gen([response_type])
                if (
                    getattr(configs, 'observer_enabled', True)
                    and not self.observers.get(response_type)
                ):
                    self.observer_gen([response_type])
                if (
                    not self.checkers.get(response_type)
                    or (
                        getattr(configs, 'observer_enabled', True)
                        and not self.observers.get(response_type)
                    )
                ):
                    failed = True
                    self._record_generation(
                        'response_components', response_type,
                        'quarantined', 0,
                        error='required response component generation unavailable',
                    )
            except Exception:
                failed = True
                logger.exception(
                    'Producer: on-demand response component generation failed '
                    '[%s]',
                    response_type,
                )
            finally:
                with self._response_components_lock():
                    if failed:
                        self._response_component_failures.add(response_type)
                    self._response_component_pending.discard(response_type)
                self._response_component_queue.task_done()

    def wait_for_response_components(self, timeout: float | None = None) -> bool:
        """Testing/shutdown hook; normal fuzzing never waits for generation."""
        worker = getattr(self, '_response_component_worker', None)
        if worker is None:
            return True
        worker.join(timeout)
        return not worker.is_alive()

    def _response_types_from_primary_field(
        self
    ) -> list[str]:
        rules = getattr(self.rfcp, 'res_type_rules', {})
        if isinstance(rules, dict):
            types = [
                str(item['type_name']).strip()
                for item in rules.get('types', [])
                if (
                    isinstance(item, dict)
                    and isinstance(item.get('type_name'), str)
                    and item['type_name'].strip()
                )
            ]
            if types:
                return list(dict.fromkeys(types))

        field_info = json.loads(self._primary_response_field_info())
        if not field_info:
            raise RuntimeError(
                'Response field information is empty; checker generation '
                'requires at least one state-field descriptor'
            )
        field = field_info[0]
        values = field.get('value')
        if not isinstance(values, list) or not values:
            raise RuntimeError(
                'The first response-state field must define a non-empty '
                'value list for checker generation'
            )
        return list(dict.fromkeys(str(value) for value in values))

    def _request_ir_info(
        self,
        msg_type: str
    ) -> str:
        if not hasattr(self, 'req_ir'):
            return ''

        for message in self.req_ir.findall('message'):
            if str(message.get('name', '')) == msg_type:
                return etree.tostring(
                    message,
                    encoding='utf-8',
                    pretty_print=True,
                ).decode('utf-8')

        return etree.tostring(
            self.req_ir,
            encoding='utf-8',
            pretty_print=True,
        ).decode('utf-8')

    def _ir_evolution_allowed(
        self
    ) -> bool:
        return (
            getattr(configs, 'ir_evolution_enabled', True)
            and getattr(configs, 'spec_knowledge', True)
            and analyzer.active_phase == 'model_learning'
        )

    def _ir_evolution_round_available(
        self,
        direction: str,
        msg_type: str
    ) -> bool:
        key = f'{direction}:{msg_type}'
        max_rounds = getattr(configs, 'ir_evolution_max_rounds_per_type', 1)
        return self._ir_evolution_rounds.get(key, 0) < max_rounds

    def _record_ir_evolution_round(
        self,
        direction: str,
        msg_type: str
    ) -> None:
        key = f'{direction}:{msg_type}'
        self._ir_evolution_rounds[key] = (
            self._ir_evolution_rounds.get(key, 0) + 1
        )

    async def _maybe_evolve_request_ir(
        self,
        msg_type: str,
        feedback: str
    ) -> bool:
        if (
            not self._ir_evolution_allowed()
            or not self._ir_evolution_round_available('request', msg_type)
        ):
            return False

        current_ir = self._request_ir_info(msg_type)
        if not current_ir:
            return False

        evolved_ir = await self.chater.llm_ir_evolve(
            pro_name=self.rfcp.pro_name,
            direction='request',
            msg_type=msg_type,
            current_ir=current_ir,
            type_rule=self._request_type_rule_info(msg_type),
            section_context=self.rfcp._message_ir_context(msg_type, 'req'),
            feedback=feedback,
        )
        if not evolved_ir:
            return False

        self._replace_request_ir(msg_type, evolved_ir)
        self._record_ir_evolution(
            direction='request',
            msg_type=msg_type,
            old_ir=current_ir,
            new_ir=evolved_ir,
            feedback=feedback,
        )
        self._record_ir_evolution_round('request', msg_type)
        logger.info(f'Producer: evolved request IR [{msg_type}]')
        return True

    async def _maybe_evolve_response_ir(
        self,
        response: bytes,
        feedback: str
    ) -> bool:
        msg_type = 'response'
        if (
            not self._ir_evolution_allowed()
            or not self._ir_evolution_round_available('response', msg_type)
            or not hasattr(self, 'res_ir')
        ):
            return False

        current_ir = etree.tostring(
            self.res_ir,
            encoding='utf-8',
            pretty_print=True,
        ).decode('utf-8')
        evolved_ir = await self.chater.llm_ir_evolve(
            pro_name=self.rfcp.pro_name,
            direction='response',
            msg_type=msg_type,
            current_ir=current_ir,
            type_rule=self._response_type_rules_info(),
            section_context=self.rfcp._message_ir_context(
                f'response message of {self.rfcp.pro_name} protocol',
                'res',
            ),
            feedback=(
                f'{feedback}\n'
                f'Response bytes repr: {response!r}\n'
                f'Response bytes hex: {response.hex(" ")}'
            ),
        )
        if not evolved_ir:
            return False

        self._replace_response_ir(evolved_ir)
        self._record_ir_evolution(
            direction='response',
            msg_type=msg_type,
            old_ir=current_ir,
            new_ir=evolved_ir,
            feedback=feedback,
        )
        self._record_ir_evolution_round('response', msg_type)
        logger.info('Producer: evolved response IR')
        return True

    def _parse_evolved_ir(
        self,
        evolved_ir: str
    ):
        root = etree.fromstring(evolved_ir.encode('utf-8'))
        if root.tag == 'ir':
            return root

        wrapper = etree.Element('ir')
        wrapper.append(root)
        return wrapper

    def _replace_request_ir(
        self,
        msg_type: str,
        evolved_ir: str
    ) -> None:
        evolved_root = self._parse_evolved_ir(evolved_ir)
        replacement = None
        for message in evolved_root.findall('message'):
            if str(message.get('name', '')) == msg_type:
                replacement = message
                break

        if replacement is None:
            messages = evolved_root.findall('message')
            if len(messages) == 1:
                replacement = messages[0]

        if replacement is None:
            raise ValueError(f'evolved request IR lacks message {msg_type}')

        for index, message in enumerate(self.req_ir.findall('message')):
            if str(message.get('name', '')) == msg_type:
                parent_index = self.req_ir.index(message)
                self.req_ir[parent_index] = replacement
                break
        else:
            self.req_ir.append(replacement)

        self._write_ir_file('req', self.req_ir)
        self.rfcp.req_ir = etree.ElementTree(self.req_ir)

    def _replace_response_ir(
        self,
        evolved_ir: str
    ) -> None:
        self.res_ir = self._parse_evolved_ir(evolved_ir)
        self.rfcp.res_ir = etree.ElementTree(self.res_ir)
        self._write_ir_file('res', self.res_ir)

    def _write_ir_file(
        self,
        direction: str,
        root
    ) -> None:
        path = self.rfcp.ir_path / f'{direction}_ir.xml'
        etree.ElementTree(root).write(
            path,
            encoding='UTF-8',
            xml_declaration=True,
            pretty_print=True,
            standalone='yes',
        )

    def _record_ir_evolution(
        self,
        direction: str,
        msg_type: str,
        old_ir: str,
        new_ir: str,
        feedback: str
    ) -> None:
        log_path = self.rfcp.ir_path / 'ir_evolution_log.json'
        try:
            if log_path.is_file():
                with open(log_path, 'r', encoding='utf-8') as f:
                    records = json.load(f)
            else:
                records = []

            records.append({
                'phase': analyzer.active_phase,
                'direction': direction,
                'message_type': msg_type,
                'feedback': feedback,
                'old_hash': hashlib.sha256(
                    old_ir.encode('utf-8')
                ).hexdigest(),
                'new_hash': hashlib.sha256(
                    new_ir.encode('utf-8')
                ).hexdigest(),
            })
            with open(log_path, 'w', encoding='utf-8') as f:
                json.dump(records, f, indent=2)
        except Exception:
            logger.exception('Producer: failed to write IR evolution log')

    def _checker_ir_for_response_type(
        self,
        response_type: str,
        messages: list
    ):
        """Select dedicated IR when available, otherwise retain generic IR."""
        for message in messages:
            if str(message.get('name', '')) == response_type:
                return message

        state_field = self._primary_response_field_name()
        normalized_state_field = self._normalize_field_name(state_field)
        for message in messages:
            for field in message.findall('field'):
                if (
                    self._normalize_field_name(field.get('name', ''))
                    != normalized_state_field
                ):
                    continue
                if str(field.get('value', '')).strip() == response_type:
                    return message

        if len(messages) == 1:
            return messages[0]
        return self.res_ir

    @staticmethod
    def _normalize_field_name(
        field_name: str
    ) -> str:
        return ''.join(char.lower() for char in field_name if char.isalnum())

    def _checker_cache_matches_response_types(
        self,
        expected_types: list[str] | None = None,
    ) -> bool:
        expected = set(
            expected_types
            if expected_types is not None
            else self._initial_response_component_types()
        )
        if not expected.issubset(self.checkers):
            return False
        state_field = self._primary_response_field_name()
        return all(
            checkers
            and self._response_component_metadata_current(
                checkers[-1], msg_type, state_field
            )
            for msg_type, checkers in self.checkers.items()
            if msg_type in expected
        )

    def _observer_cache_matches_response_types(
        self,
        expected_types: list[str] | None = None,
    ) -> bool:
        expected = set(
            expected_types
            if expected_types is not None
            else self._initial_response_component_types()
        )
        if not expected.issubset(self.observers):
            return False
        state_field = self._primary_response_field_name()
        return all(
            observers
            and self._response_component_metadata_current(
                observers[-1], msg_type, state_field
            )
            for msg_type, observers in self.observers.items()
            if msg_type in expected
        )
        
    async def _parser_evo_one(
        self,
        message
    ):
        res_info = self._primary_response_field_info()
        await self._maybe_evolve_response_ir(
            message,
            (
                'parser_evo was triggered by a response that the current '
                'parser could not classify during model learning.'
            ),
        )
        old_code = ''
        old_p_name = f'{self.parsers[-1].name}.py'
        old_p_path = self.parser_path / old_p_name
        with open(old_p_path, 'r', encoding='utf-8') as f:
            old_code = f.read()
                
        failed_code: str | None = None
        failure_error = ''
        retry_limit = max(1, getattr(configs, 'generation_retry_limit', 3))
        failure_count = 0
        while failure_count < retry_limit:
            pkt_parser_code: str | None = None
            try:
                if failed_code is None:
                    pkt_parser_code = await self.chater.llm_parser_evolve(
                        old_code=old_code,
                        pro_name=self.rfcp.pro_name,
                        res_info=res_info,
                        message=message,
                    )
                else:
                    pkt_parser_code = await self.chater.llm_code_repair(
                        code=failed_code,
                        error=failure_error,
                        function_name='packet_parser',
                    )
                if not self._evolution_changed(pkt_parser_code):
                    baseline_validation = validate_generated_code(
                        pkt_parser_code,
                        'packet_parser',
                        'parser',
                        timeout_s=self._generated_code_timeout(),
                        runtime_samples=(message,),
                        require_nonempty_samples=True,
                    )
                    outcome = (
                        'no_change'
                        if baseline_validation.ok
                        else 'no_change_unresolved'
                    )
                    self._record_generation(
                        'parser_evolution', '__all__', outcome,
                        failure_count + 1, pkt_parser_code,
                        error='' if baseline_validation.ok else self._parser_validation_failure(
                            baseline_validation.error,
                            (message,),
                        ),
                        base_sha256=hashlib.sha256(
                            old_code.encode('utf-8')
                        ).hexdigest(),
                        changed=False,
                        reason=self._evolution_reason(pkt_parser_code),
                    )
                    return None

                # test generated code
                with analyzer.lock:
                    analyzer.finished += 1
                validation = validate_generated_code(
                    pkt_parser_code,
                    'packet_parser',
                    'parser',
                    timeout_s=self._generated_code_timeout(),
                    runtime_samples=(message,),
                    require_nonempty_samples=True,
                )
                if not validation.ok:
                    raise ValueError(
                        self._parser_validation_failure(
                            validation.error,
                            (message,),
                        )
                    )
                self._record_generation(
                    'parser_evolution', '__all__',
                    'generated' if failure_count == 0 else 'repaired',
                    failure_count + 1, pkt_parser_code,
                )
                return pkt_parser_code
            except LLMDeadlineExceeded:
                raise
            except Exception as e:
                if pkt_parser_code is not None:
                    failed_code = pkt_parser_code
                failure_error = f'{type(e).__name__}: {e}'
                failure_count += 1
                self._record_generation(
                    'parser_evolution', '__all__', 'invalid',
                    failure_count, pkt_parser_code, failure_error,
                )
                logger.debug(f'Producer: generate error {e}')
        raise RuntimeError(
            f'parser evolution failed after {retry_limit} attempts: '
            f'{failure_error}'
        )

    def _primary_response_field_info(
        self
    ) -> str:
        """Serialize response-state field descriptors used by parser/checkers."""
        if not self.rfcp.res_json:
            raise RuntimeError(
                'Response field information is empty; parser generation '
                'requires at least one state-field descriptor'
            )
        return json.dumps(self.rfcp.res_json)

    def _primary_response_field_name(
        self
    ) -> str:
        rules = getattr(self.rfcp, 'res_type_rules', {})
        if isinstance(rules, dict):
            primary_fields = rules.get('primary_fields')
            if isinstance(primary_fields, list) and primary_fields:
                fields = [
                    str(field)
                    for field in primary_fields
                    if str(field).strip()
                ]
                if fields:
                    return '+'.join(fields)

        field_info = json.loads(self._primary_response_field_info())
        if not field_info:
            return ''
        field = field_info[0]
        return str(field.get('field_name') or field.get('name') or '')

    def _request_type_rule_info(
        self,
        request_type: str
    ) -> str:
        rules = getattr(self.rfcp, 'req_type_rules', {})
        if not isinstance(rules, dict):
            return '{}'
        for item in rules.get('types', []):
            if (
                isinstance(item, dict)
                and str(item.get('type_name', '')).strip() == request_type
            ):
                return json.dumps(item)
        return '{}'

    def _response_type_rule_info(
        self,
        response_type: str
    ) -> str:
        rules = getattr(self.rfcp, 'res_type_rules', {})
        if not isinstance(rules, dict):
            return '{}'
        for item in rules.get('types', []):
            if (
                isinstance(item, dict)
                and str(item.get('type_name', '')).strip() == response_type
            ):
                return json.dumps(item)
        return '{}'

    def _response_type_rules_info(
        self
    ) -> str:
        rules = getattr(self.rfcp, 'res_type_rules', {})
        if isinstance(rules, dict):
            return json.dumps(rules)
        return '{}'

    @staticmethod
    def _parser_validation_samples() -> tuple[bytes, ...]:
        samples = getattr(configs, 'parser_validation_samples', ())
        if not isinstance(samples, (list, tuple)):
            return ()
        return tuple(
            sample
            for sample in samples
            if isinstance(sample, bytes) and sample
        )

    def _parser_validation_failure(
        self,
        error: str,
        samples: tuple[bytes, ...],
    ) -> str:
        if not samples:
            return error
        field = self._primary_response_field_name()
        summaries = ', '.join(
            f'len={len(sample)} hex={sample[:96].hex()}'
            for sample in samples[:8]
        )
        return (
            f'{error}\nExpected non-empty bytes classification for real '
            f'protocol samples using response field {field!r}. '
            f'Failing validation samples: {summaries}'
        )

    def _parser_cache_matches_primary_field(
        self
    ) -> bool:
        if not self.parsers:
            return False
        return self.parsers[-1].state_field == (
            self._primary_response_field_name()
        )

    def _parser_cache_contract_valid(self) -> bool:
        if not self.parsers:
            return False
        parser = self.parsers[-1]
        path = self.parser_path / f'{parser.name}.py'
        if not path.is_file():
            return False
        code = path.read_text(encoding='utf-8')
        validation = validate_generated_code(
            code,
            'packet_parser',
            'parser',
            timeout_s=self._generated_code_timeout(),
        )
        self._record_generation(
            'parser', '__all__',
            'reused_cache' if validation.ok else 'cache_invalid',
            0, code, validation.error,
        )
        return validation.ok

    @staticmethod
    def _atomic_write_text(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(
            f'.{path.name}.{threading.get_ident()}.{time.time_ns()}.tmp'
        )
        temporary.write_text(content, encoding='utf-8')
        temporary.replace(path)

    def _atomic_write_json(self, path: Path, content: object) -> None:
        self._atomic_write_text(
            path,
            json.dumps(content, ensure_ascii=False),
        )

    def _publish_runtime_component(
        self,
        component: str,
        component_type: str,
        code: str,
    ) -> object:
        """Atomically publish a contract-validated replacement version."""
        lock = getattr(self, '_runtime_component_lock', None)
        if lock is None:
            lock = threading.RLock()
            self._runtime_component_lock = lock
        with lock:
            state_field = self._primary_response_field_name()
            if component == 'parser':
                old_name = self.parsers[-1].name if self.parsers else 'init'
                name = f'id{len(self.parsers)}'
                path = self.parser_path / f'{name}.py'
                self._atomic_write_text(path, code)
                metadata = Parser(
                    evolved_from=old_name,
                    name=name,
                    state_field=state_field,
                )
                self.parsers.append(metadata)
                self._atomic_write_json(
                    self.parser_info_path,
                    self.parser_info(),
                )
                return metadata

            if component in {'generator', 'mutator'}:
                collection = (
                    self.generators
                    if component == 'generator'
                    else self.mutators
                )
                root = (
                    self.generator_path
                    if component == 'generator'
                    else self.mutator_path
                )
                versions = collection.setdefault(component_type, [])
                old_name = versions[-1].name if versions else 'init'
                name = f'id{len(versions)}'
                path = (
                    self._component_type_dir(root, component_type)
                    / f'{name}.py'
                )
                self._atomic_write_text(path, code)
                metadata = Generator(
                    msg_type=component_type,
                    evolved_from=old_name,
                    name=name,
                    path=str(path.resolve()),
                )
                versions.append(metadata)
                info_path = (
                    self.generator_info_path
                    if component == 'generator'
                    else self.mutator_info_path
                )
                info = (
                    self.generator_info()
                    if component == 'generator'
                    else self.mutator_info()
                )
                self._atomic_write_json(info_path, info)
                return metadata

            if component == 'checker':
                versions = self.checkers.setdefault(component_type, [])
                old_name = versions[-1].name if versions else 'init'
                name = f'id{len(versions)}'
                path = (
                    self._component_type_dir(
                        self.checker_path,
                        component_type,
                    )
                    / f'{name}.py'
                )
                self._atomic_write_text(path, code)
                metadata = Checker(
                    msg_type=component_type,
                    evolved_from=old_name,
                    name=name,
                    path=str(path.resolve()),
                    state_field=state_field,
                    contract_version=self.RESPONSE_COMPONENT_CONTRACT_VERSION,
                    ir_sha256=self._response_component_ir_sha256(
                        component_type
                    ),
                )
                versions.append(metadata)
                self._atomic_write_json(
                    self.checker_info_path,
                    self.checker_info(),
                )
                return metadata

            if component == 'observer':
                versions = self.observers.setdefault(component_type, [])
                old_name = versions[-1].name if versions else 'init'
                name = f'id{len(versions)}'
                path = (
                    self._component_type_dir(
                        self.observer_path,
                        component_type,
                    )
                    / f'{name}.py'
                )
                self._atomic_write_text(path, code)
                metadata = ResponseObserver(
                    msg_type=component_type,
                    evolved_from=old_name,
                    name=name,
                    path=str(path.resolve()),
                    state_field=state_field,
                    contract_version=self.RESPONSE_COMPONENT_CONTRACT_VERSION,
                    ir_sha256=self._response_component_ir_sha256(
                        component_type
                    ),
                )
                versions.append(metadata)
                self._atomic_write_json(
                    self.observer_info_path,
                    self.observer_info(),
                )
                return metadata

        raise ValueError(f'unsupported runtime component: {component}')

    async def _repair_runtime_component_async(
        self,
        component: str,
        component_type: str,
        source_code: str,
        error: str,
        runtime_input: bytes | None,
    ) -> tuple[object, str] | None:
        function_name = {
            'parser': 'packet_parser',
            'generator': 'generate',
            'mutator': 'mutate',
            'checker': 'packet_checker',
            'observer': 'packet_observer',
        }[component]
        failed_code = source_code
        runtime_samples = (
            (runtime_input,) if runtime_input is not None else ()
        )
        failure_error = (
            self._parser_validation_failure(error, runtime_samples)
            if component == 'parser'
            else error
        )
        retry_limit = max(1, getattr(configs, 'generation_retry_limit', 3))
        for attempt in range(1, retry_limit + 1):
            candidate: str | None = None
            try:
                candidate = await self.chater.llm_code_repair(
                    code=failed_code,
                    error=failure_error,
                    function_name=function_name,
                )
                validation = validate_generated_code(
                    candidate,
                    function_name,
                    component,
                    timeout_s=self._generated_code_timeout(),
                    max_output_bytes=self._generated_message_limit(),
                    observer_samples=runtime_samples,
                    runtime_samples=runtime_samples,
                    require_nonempty_samples=(component == 'parser'),
                )
                if not validation.ok:
                    validation_error = validation.error
                    if component == 'parser':
                        validation_error = self._parser_validation_failure(
                            validation_error,
                            runtime_samples,
                        )
                    raise ValueError(validation_error)
                metadata = self._publish_runtime_component(
                    component,
                    component_type,
                    candidate,
                )
                self._record_generation(
                    f'{component}_runtime_repair', component_type,
                    'published', attempt, candidate,
                )
                self._last_runtime_repair_attempts = attempt
                return metadata, candidate
            except LLMDeadlineExceeded:
                raise
            except Exception as repair_error:
                if candidate is not None:
                    failed_code = candidate
                failure_error = (
                    f'{type(repair_error).__name__}: {repair_error}'
                )
                self._record_generation(
                    f'{component}_runtime_repair', component_type,
                    'invalid', attempt, candidate, failure_error,
                )
        self._last_runtime_repair_attempts = retry_limit
        return None

    def repair_runtime_component(
        self,
        component: str,
        component_type: str,
        source_code: str,
        error: str,
        runtime_input: bytes | None = None,
    ) -> tuple[object, str] | None:
        """Repair, validate, and publish code after a runtime contract failure."""
        return asyncio.run(self._repair_runtime_component_async(
            component,
            component_type,
            source_code,
            error,
            runtime_input,
        ))

    def parser_evo(
        self,
        message
    ) -> bool:
        """Generate and save parser
        """
        # produce new parser
        parser_code = asyncio.run(self._parser_evo_one(message))
        if parser_code is None:
            logger.debug('Producer: parser evolution kept the current parser')
            return False
        
        par_dir = self.parser_path
        if not par_dir.is_dir():
            par_dir.mkdir()
        
        # save parser
        cur_id = len(self.parsers)
        par_path = par_dir / f'id{cur_id}.py'
        with open(par_path, 'w', encoding='utf-8') as f:
            f.write(parser_code)
            # construct and save information for new parser
            
            old_name = self.parsers[-1].name
            new_name = f'id{cur_id}'
            info: dict = {
                'evolved_from': old_name,
                'name': new_name,
                'state_field': self._primary_response_field_name()
            }
            self.parsers.append(Parser(**info))
                
        # save the information of new parser to file   
        with open(self.parser_info_path, 'w', encoding='utf-8') as f:
            json.dump(self.parser_info(), f)
        
        logger.debug("[Producer]: finish parser evolve")
        return True

    def generator_info(
        self
    ) -> dict:
        """The information of generators
        Contains a dict to map msg_type and corresponded generator
        """
        info: dict[str, list[dict]]= {}
        for msg_type in self.generators.keys():
            for g in self.generators[msg_type]:
                info.setdefault(msg_type, [])
                info[msg_type].append(asdict(g))
        return info
    
    def mutator_info(
        self
    ) -> dict:
        """The information of mutators
        Contains a dict to map msg_type and corresponded mutator
        """
        info: dict[str, list[dict]]= {}
        for msg_type, ms in self.mutators.items():
            for m in ms:
                info.setdefault(msg_type, [])
                info[msg_type].append(asdict(m))
        return info
    
    def parser_info(
        self
    ) -> list:
        """The information of parsers
        """
        info: list[dict] = []
        for p in self.parsers:
            info.append(asdict(p))
        return info

    def checker_info(
        self
    ) -> dict:
        """Map each response type to its generated checker metadata."""
        return {
            msg_type: [asdict(checker) for checker in checkers]
            for msg_type, checkers in self.checkers.items()
        }

    def observer_info(self) -> dict:
        return {
            msg_type: [asdict(observer) for observer in observers]
            for msg_type, observers in self.observers.items()
        }
    
    def generators_info_load(
        self,
        info: dict
    ):
        try:
            for msg_type in info:
                for g in info[msg_type]:
                    normalized = dict(g)
                    # Imported bundles retain their source runtime's absolute
                    # paths.  The active equipment directory is authoritative:
                    # prefer its typed component path whenever it exists.
                    local_path = (
                        self._component_type_dir(
                            self.generator_path,
                            msg_type,
                            record=False,
                        )
                        / f"{normalized['name']}.py"
                    )
                    if local_path.is_file():
                        normalized['path'] = str(local_path.resolve())
                    self.generators.setdefault(msg_type, [])
                    self.generators[msg_type].append(Generator(**normalized))
        except Exception as e:
            logger.debug(f'Producer: load error {e}')
    
    def mutators_info_load(
        self,
        info: dict
    ):
        try:
            for msg_type in info:
                for g in info[msg_type]:
                    self.mutators.setdefault(msg_type, [])
                    self.mutators[msg_type].append(Generator(**g))
        except Exception as e:
            logger.debug(f'Producer: load error {e}')
        
                
    def parsers_info_load(
        self,
        info: list
    ):
        for p in info:
            self.parsers.append(Parser(**p))

    def checkers_info_load(
        self,
        info: dict
    ):
        for msg_type, checkers in info.items():
            for checker in checkers:
                checker.setdefault('msg_type', msg_type)
                checker.setdefault('state_field', '')
                self.checkers.setdefault(msg_type, [])
                self.checkers[msg_type].append(Checker(**checker))

    def observers_info_load(self, info: dict) -> None:
        self.observers = {}
        for msg_type, observers in info.items():
            for observer in observers:
                observer.setdefault('msg_type', msg_type)
                observer.setdefault('state_field', '')
                observer.setdefault('evolved_from', 'init')
                observer.setdefault(
                    'sample_observations',
                    observer.pop('sample_hashes', []),
                )
                self.observers.setdefault(msg_type, []).append(
                    ResponseObserver(**observer)
                )

    def legacy_checkers_info_load(
        self,
        info: list
    ):
        """Load the former single-checker cache as a global fallback."""
        for checker in info:
            name = checker.get('name', 'id0')
            path = self.checker_path / f'{name}.py'
            legacy = Checker(
                msg_type='__all__',
                evolved_from=checker.get('evolved_from', 'init'),
                name=name,
                path=str(path.resolve()),
                state_field='',
                checked_res=checker.get('checked_res', [])
            )
            self.checkers.setdefault('__all__', []).append(legacy)
