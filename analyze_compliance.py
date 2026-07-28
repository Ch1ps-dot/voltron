#!/usr/bin/env python3

import argparse
import asyncio
import base64
import json
import pickle
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from fastbm25 import fastbm25
from tqdm import tqdm

from voltron.configs import configs
from voltron.llm.chatter import AsyncChater
from voltron.rfcparser.setciontree import SectionTree


ANALYSIS_SCHEMA = {
    "verdict": "compliant | non_compliant | uncertain",
    "confidence": "number from 0.0 to 1.0",
    "summary": "short conclusion",
    "violations": [
        {
            "rfc": "specification name",
            "section": "section heading",
            "requirement": "normative requirement",
            "observation": "how the captured exchange violates it",
        }
    ],
    "evidence": [
        {
            "rfc": "specification name",
            "section": "section heading",
            "relevance": "why this section supports the conclusion",
        }
    ],
}


@dataclass(frozen=True)
class PairRecord:
    source: Path
    request_type: str
    response_type: str
    request: bytes
    response: bytes


@dataclass(frozen=True)
class SectionRecord:
    rfc: str
    section: str
    content_type: str
    content: str


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be greater than zero")
    return parsed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Analyze saved request-response pairs for protocol "
            "non-compliance using cached RFC SectionTrees and the configured LLM."
        )
    )
    parser.add_argument(
        "-s",
        "--sut",
        required=True,
        help="SUT name from config/configs.yaml",
    )
    parser.add_argument(
        "-i",
        "--input",
        required=True,
        type=Path,
        help=(
            "A pair JSON file, request_response_pairs directory, "
            "or fuzz result directory"
        ),
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output directory (default: compliance_analysis beside the input)",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=8,
        help="Number of RFC sections supplied to the LLM (default: 8)",
    )
    parser.add_argument(
        "--max-section-chars",
        type=int,
        default=6000,
        help="Maximum characters retained from each RFC section (default: 6000)",
    )
    parser.add_argument(
        "-j",
        "--concurrency",
        type=positive_int,
        default=None,
        help=(
            "Maximum concurrent pair analyses "
            "(default: llm_compliance.async_sem)"
        ),
    )
    return parser.parse_args()


def load_target_config(target_name: str) -> dict[str, Any]:
    config_path = configs.base_path / "config" / "configs.yaml"
    with config_path.open("r", encoding="utf-8") as f:
        config_data = yaml.safe_load(f)

    target = config_data.get(target_name)
    if not isinstance(target, dict):
        raise ValueError(f"unknown SUT in {config_path}: {target_name}")

    llm_config = config_data.get("llm_compliance")
    if not isinstance(llm_config, dict):
        raise ValueError(
            f"missing llm_compliance configuration in {config_path}"
        )

    rfc_names = target.get("rfc_name")
    if not isinstance(rfc_names, list) or not rfc_names:
        raise ValueError(f"SUT {target_name} has no RFC list")

    protocol = target.get("protocol")
    if not isinstance(protocol, str) or not protocol:
        raise ValueError(f"SUT {target_name} has no protocol")

    configs.target_name = target_name
    configs.pro_name = protocol
    configs.rfc_name = rfc_names
    configs.pmp_path = configs.base_path / "skills"
    configs.base_url_compliance = str(llm_config.get("base_url", ""))
    configs.api_key_compliance = str(llm_config.get("api_key", ""))
    configs.model_compliance = str(llm_config.get("model", ""))
    configs.async_sem_compliance = llm_config.get("async_sem", 1)

    return {
        "target_name": target_name,
        "protocol": protocol,
        "rfc_names": [str(name) for name in rfc_names],
        "llm": llm_config,
    }


def discover_pair_files(input_path: Path) -> list[Path]:
    input_path = input_path.resolve()
    if input_path.is_file():
        return [input_path]
    if not input_path.is_dir():
        raise FileNotFoundError(f"input does not exist: {input_path}")

    pair_dir = input_path
    nested_pair_dir = input_path / "request_response_pairs"
    if nested_pair_dir.is_dir():
        pair_dir = nested_pair_dir

    pair_files = sorted(pair_dir.glob("pair_*.json"))
    if not pair_files:
        raise FileNotFoundError(f"no pair_*.json files found under {pair_dir}")
    return pair_files


def decode_base64_field(data: dict[str, Any], field_name: str) -> bytes:
    field = data.get(field_name)
    if not isinstance(field, dict):
        raise ValueError(f"missing object field: {field_name}")
    if field.get("encoding") != "base64":
        raise ValueError(f"{field_name} encoding must be base64")
    encoded = field.get("data")
    if not isinstance(encoded, str):
        raise ValueError(f"{field_name}.data must be a string")
    try:
        return base64.b64decode(encoded, validate=True)
    except ValueError as e:
        raise ValueError(f"invalid base64 in {field_name}") from e


def load_pair(path: Path) -> PairRecord:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"pair file must contain a JSON object: {path}")

    request_type = data.get("request_type")
    response_type = data.get("response_type")
    if not isinstance(request_type, str) or not request_type:
        raise ValueError(f"invalid request_type in {path}")
    if not isinstance(response_type, str) or not response_type:
        raise ValueError(f"invalid response_type in {path}")

    request = decode_base64_field(data, "request")
    response = decode_base64_field(data, "response")
    expected_request_length = data.get("request_length")
    expected_response_length = data.get("response_length")
    if expected_request_length is not None and expected_request_length != len(request):
        raise ValueError(f"request_length mismatch in {path}")
    if expected_response_length is not None and expected_response_length != len(response):
        raise ValueError(f"response_length mismatch in {path}")

    return PairRecord(
        source=path,
        request_type=request_type,
        response_type=response_type,
        request=request,
        response=response,
    )


def load_sections(protocol: str, rfc_names: list[str]) -> list[SectionRecord]:
    sections: list[SectionRecord] = []
    failures: list[str] = []
    tree_path = configs.base_path / "component" / "tree" / protocol
    for rfc_name in dict.fromkeys(rfc_names):
        cache_path = tree_path / f"{rfc_name}.pkl"
        try:
            if not cache_path.is_file():
                raise FileNotFoundError("cache file does not exist")
            with cache_path.open("rb") as f:
                tree = pickle.load(f)
            if not isinstance(tree, SectionTree):
                raise TypeError(
                    f"expected SectionTree, got {type(tree).__name__}"
                )

            loaded_count = 0
            for node in tree.leafs:
                if node.content_type not in {"request", "response", "all"}:
                    continue
                content = tree.fetch_node_content(node).strip()
                if content:
                    sections.append(
                        SectionRecord(
                            rfc=rfc_name,
                            section=node.name.strip(),
                            content_type=node.content_type,
                            content=content,
                        )
                    )
                    loaded_count += 1
            if loaded_count == 0:
                raise ValueError(
                    "cache contains no annotated protocol sections"
                )
        except Exception as error:
            reason = f"{cache_path}: {type(error).__name__}: {error}"
            failures.append(reason)
            print(
                "Warning: skipping unusable SectionTree cache: "
                f"{reason}",
                file=sys.stderr,
            )

    if not sections:
        details = "\n".join(f"- {failure}" for failure in failures)
        raise RuntimeError(
            f"no usable cached RFC SectionTrees found for protocol "
            f"{protocol}.\n{details}\n"
            "Run the normal specification-aware workflow again to "
            "regenerate component/tree caches."
        )
    if failures:
        print(
            f"Loaded {len(sections)} protocol sections while skipping "
            f"{len(failures)} unusable RFC cache(s).",
            file=sys.stderr,
        )
    return sections


def bytes_for_query(data: bytes, limit: int = 512) -> str:
    sample = data[:limit]
    text = sample.decode("utf-8", errors="backslashreplace")
    hex_text = sample.hex(" ")
    return f"{text} {hex_text}"


def retrieve_sections(
    pair: PairRecord,
    sections: list[SectionRecord],
    top_k: int,
) -> list[tuple[SectionRecord, float]]:
    if top_k <= 0:
        raise ValueError("top_k must be greater than zero")

    corpus = [section.content.split() for section in sections]
    index = fastbm25(corpus)
    query = (
        f"{pair.request_type} {pair.response_type} "
        f"{bytes_for_query(pair.request)} {bytes_for_query(pair.response)}"
    ).split()
    results = index.top_k_sentence(query, min(top_k, len(sections)))
    return [
        (sections[result[1]], float(result[2]))
        for result in results
    ]


def display_bytes(data: bytes, limit: int | None = 4096) -> dict[str, Any]:
    sample = data if limit is None else data[:limit]
    return {
        "length": len(data),
        "truncated": len(sample) < len(data),
        "text": sample.decode("utf-8", errors="backslashreplace"),
        "hex": sample.hex(" "),
        "base64": base64.b64encode(sample).decode("ascii"),
    }


def build_prompt(
    target: dict[str, Any],
    pair: PairRecord,
    retrieved: list[tuple[SectionRecord, float]],
    max_section_chars: int,
) -> str:
    if max_section_chars <= 0:
        raise ValueError("max_section_chars must be greater than zero")

    context_parts = []
    for number, (section, score) in enumerate(retrieved, start=1):
        content = section.content[:max_section_chars]
        context_parts.append(
            f"[SPEC {number}]\n"
            f"RFC: {section.rfc}\n"
            f"Section: {section.section}\n"
            f"Annotation: {section.content_type}\n"
            f"BM25 score: {score:.4f}\n"
            f"Content:\n{content}"
        )

    exchange = {
        "request_type": pair.request_type,
        "response_type": pair.response_type,
        "request": display_bytes(pair.request),
        "response": display_bytes(pair.response),
    }
    return (
        "You are analyzing a captured network protocol request-response pair "
        "for a possible standards non-compliance bug.\n\n"
        f"Target: {target['target_name']}\n"
        f"Protocol: {target['protocol']}\n"
        f"Configured specifications: {target['rfc_names']}\n\n"
        "Captured exchange:\n"
        f"{json.dumps(exchange, indent=2, ensure_ascii=False)}\n\n"
        "Retrieved specification context:\n"
        f"{'\n\n'.join(context_parts)}\n\n"
        "Determine whether the response violates a normative protocol "
        "requirement for this request. Distinguish an actual wire-format, "
        "semantic, sequencing, or required-response violation from behavior "
        "that is implementation-defined, optional, or unsupported by the "
        "retrieved evidence. If the exchange lacks state/history needed for "
        "a reliable conclusion, use verdict 'uncertain'. Do not claim a "
        "violation without identifying supporting RFC text and the conflicting "
        "observed bytes.\n\n"
        "Return only one JSON object matching this shape:\n"
        f"{json.dumps(ANALYSIS_SCHEMA, indent=2)}"
    )


def parse_model_result(response: str | None) -> dict[str, Any]:
    if not response:
        return {
            "verdict": "uncertain",
            "confidence": 0.0,
            "summary": "The model returned no analysis.",
            "violations": [],
            "evidence": [],
        }

    cleaned = re.sub(
        r"^\s*```(?:json)?\s*|\s*```\s*$",
        "",
        response.strip(),
        flags=re.IGNORECASE,
    )
    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        if start == -1:
            result = None
        else:
            try:
                result, _ = json.JSONDecoder().raw_decode(cleaned[start:])
            except json.JSONDecodeError:
                result = None

    if not isinstance(result, dict):
        return {
            "verdict": "uncertain",
            "confidence": 0.0,
            "summary": "The model response was not valid JSON.",
            "violations": [],
            "evidence": [],
            "raw_model_response": response,
        }

    if result.get("verdict") not in {
        "compliant",
        "non_compliant",
        "uncertain",
    }:
        result["verdict"] = "uncertain"
    result.setdefault("confidence", 0.0)
    result.setdefault("summary", "")
    result.setdefault("violations", [])
    result.setdefault("evidence", [])
    return result


def build_vulnerability_report_prompt(
    target: dict[str, Any],
    pair: PairRecord,
    result: dict[str, Any],
) -> str:
    exchange = {
        "request_type": pair.request_type,
        "response_type": pair.response_type,
        "request": display_bytes(pair.request, limit=8192),
        "response": display_bytes(pair.response, limit=8192),
    }
    report_context = {
        "target": target["target_name"],
        "protocol": target["protocol"],
        "source_pair": str(pair.source),
        "analysis": result["analysis"],
        "retrieved_sections": result["retrieved_sections"],
        "captured_exchange": exchange,
    }
    return (
        "You are a security engineer writing a vulnerability report for a "
        "protocol standards non-compliance bug.\n\n"
        "Use the provided compliance analysis, retrieved RFC evidence, and "
        "captured request/response messages. Do not invent unsupported root "
        "causes. If impact is uncertain, say so explicitly.\n\n"
        "Write a concise Markdown report with these sections:\n"
        "1. Summary\n"
        "2. Affected Target and Protocol\n"
        "3. Non-Compliance Evidence\n"
        "4. Triggering Request and Observed Response\n"
        "5. Reproduction Notes\n"
        "6. Security Impact Hypothesis\n"
        "7. Confidence and Open Questions\n\n"
        f"Evidence JSON:\n{json.dumps(report_context, indent=2, ensure_ascii=False)}"
    )


def render_vulnerability_report_markdown(
    pair: PairRecord,
    result: dict[str, Any],
    model_report: str | None,
) -> str:
    request = display_bytes(pair.request, limit=None)
    response = display_bytes(pair.response, limit=None)
    analysis = result["analysis"]
    model_text = model_report or "The model returned no vulnerability report."
    return (
        f"# Vulnerability Report: {pair.source.stem}\n\n"
        "## Captured Exchange\n\n"
        f"- Source pair: `{pair.source}`\n"
        f"- Request type: `{pair.request_type}`\n"
        f"- Response type: `{pair.response_type}`\n"
        f"- Verdict: `{analysis.get('verdict', '')}`\n"
        f"- Confidence: `{analysis.get('confidence', '')}`\n"
        f"- Summary: {analysis.get('summary', '')}\n\n"
        "## Request Message\n\n"
        f"- Length: {request['length']}\n"
        f"- Encoding: base64\n\n"
        "````text\n"
        f"{request['text']}\n"
        "````\n\n"
        "```hex\n"
        f"{request['hex']}\n"
        "```\n\n"
        "```base64\n"
        f"{request['base64']}\n"
        "```\n\n"
        "## Response Message\n\n"
        f"- Length: {response['length']}\n"
        f"- Encoding: base64\n\n"
        "````text\n"
        f"{response['text']}\n"
        "````\n\n"
        "```hex\n"
        f"{response['hex']}\n"
        "```\n\n"
        "```base64\n"
        f"{response['base64']}\n"
        "```\n\n"
        "## Model-Generated Analysis\n\n"
        f"{model_text.strip()}\n"
    )


async def generate_vulnerability_report(
    chater: AsyncChater,
    target: dict[str, Any],
    pair: PairRecord,
    result: dict[str, Any],
    output_dir: Path,
) -> dict[str, str]:
    report_dir = output_dir / "vulnerability_reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    prompt = build_vulnerability_report_prompt(target, pair, result)
    model_report = await chater.chat_llm(
        prompt=prompt,
        usage="non_compliance_report",
    )

    report_record = {
        "source_pair": str(pair.source),
        "target": target["target_name"],
        "protocol": target["protocol"],
        "request_type": pair.request_type,
        "response_type": pair.response_type,
        "analysis": result["analysis"],
        "retrieved_sections": result["retrieved_sections"],
        "request": display_bytes(pair.request, limit=None),
        "response": display_bytes(pair.response, limit=None),
        "llm_report": model_report or "",
    }
    json_path = report_dir / f"{pair.source.stem}.report.json"
    markdown_path = report_dir / f"{pair.source.stem}.report.md"
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(report_record, f, indent=2, ensure_ascii=False)
        f.write("\n")
    with markdown_path.open("w", encoding="utf-8") as f:
        f.write(
            render_vulnerability_report_markdown(
                pair,
                result,
                model_report,
            )
        )
        f.write("\n")
    return {
        "json": str(json_path),
        "markdown": str(markdown_path),
    }


async def analyze_pair(
    chater: AsyncChater,
    target: dict[str, Any],
    pair: PairRecord,
    sections: list[SectionRecord],
    top_k: int,
    max_section_chars: int,
) -> dict[str, Any]:
    retrieved = retrieve_sections(pair, sections, top_k)
    prompt = build_prompt(target, pair, retrieved, max_section_chars)
    model_response = await chater.chat_llm(
        prompt=prompt,
        usage="non_compliance_analysis",
    )
    analysis = parse_model_result(model_response)
    return {
        "source_pair": str(pair.source),
        "target": target["target_name"],
        "protocol": target["protocol"],
        "request_type": pair.request_type,
        "response_type": pair.response_type,
        "analysis": analysis,
        "retrieved_sections": [
            {
                "rfc": section.rfc,
                "section": section.section,
                "content_type": section.content_type,
                "bm25_score": score,
            }
            for section, score in retrieved
        ],
    }


def default_output_dir(input_path: Path) -> Path:
    input_path = input_path.resolve()
    if input_path.is_file():
        return input_path.parent / "compliance_analysis"
    return input_path / "compliance_analysis"


async def analyze_pair_file(
    semaphore: asyncio.Semaphore,
    chater: AsyncChater,
    target: dict[str, Any],
    pair_path: Path,
    sections: list[SectionRecord],
    output_dir: Path,
    top_k: int,
    max_section_chars: int,
) -> tuple[Path, dict[str, Any] | None, Exception | None]:
    """Analyze and persist one pair within the configured concurrency limit."""
    try:
        async with semaphore:
            pair = load_pair(pair_path)
            result = await analyze_pair(
                chater,
                target,
                pair,
                sections,
                top_k,
                max_section_chars,
            )
            verdict = result["analysis"]["verdict"]
            result_dir = output_dir / verdict
            result_dir.mkdir(parents=True, exist_ok=True)
            if verdict == "non_compliant":
                try:
                    result["vulnerability_report"] = (
                        await generate_vulnerability_report(
                            chater,
                            target,
                            pair,
                            result,
                            output_dir,
                        )
                    )
                except Exception as report_error:
                    print(
                        "Warning: vulnerability report generation failed "
                        f"for {pair_path}: {report_error}",
                        file=sys.stderr,
                    )
            output_path = result_dir / f"{pair_path.stem}.analysis.json"
            with output_path.open("w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
                f.write("\n")
        return pair_path, result, None
    except Exception as error:
        failure_dir = output_dir / "failed"
        failure_dir.mkdir(parents=True, exist_ok=True)
        failure_path = failure_dir / f"{pair_path.stem}.analysis.json"
        failure_record = {
            "source_pair": str(pair_path),
            "error_type": type(error).__name__,
            "error": str(error),
        }
        try:
            with failure_path.open("w", encoding="utf-8") as f:
                json.dump(failure_record, f, indent=2, ensure_ascii=False)
                f.write("\n")
        except OSError:
            pass
        return pair_path, None, error


async def run(args: argparse.Namespace) -> int:
    target = load_target_config(args.sut)
    concurrency = getattr(args, "concurrency", None)
    if concurrency is None:
        concurrency = target["llm"].get("async_sem", 1)
    if (
        not isinstance(concurrency, int)
        or isinstance(concurrency, bool)
        or concurrency <= 0
    ):
        raise ValueError(
            "concurrency must be a positive integer; check --concurrency "
            "or llm_compliance.async_sem"
        )

    pair_files = discover_pair_files(args.input)
    sections = load_sections(target["protocol"], target["rfc_names"])
    output_dir = (args.output or default_output_dir(args.input)).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    llm = target["llm"]
    chater = AsyncChater(
        str(llm.get("base_url", "")),
        str(llm.get("api_key", "")),
        str(llm.get("model", "")),
    )

    failures = 0
    completed = 0
    semaphore = asyncio.Semaphore(concurrency)
    tasks = [
        asyncio.create_task(analyze_pair_file(
            semaphore=semaphore,
            chater=chater,
            target=target,
            pair_path=pair_path,
            sections=sections,
            output_dir=output_dir,
            top_k=args.top_k,
            max_section_chars=args.max_section_chars,
        ))
        for pair_path in pair_files
    ]
    with tqdm(
        total=len(pair_files),
        desc="Compliance analysis",
        unit="pair",
        dynamic_ncols=True,
    ) as progress:
        for task in asyncio.as_completed(tasks):
            pair_path, result, error = await task
            if error is None and result is not None:
                analysis = result["analysis"]
                verdict = analysis["verdict"]
                tqdm.write(
                    f"{pair_path.name}: {verdict} "
                    f"({analysis.get('confidence', 0.0)}) - "
                    f"{analysis.get('summary', '')}"
                )
            else:
                failures += 1
                verdict = "failed"
                tqdm.write(
                    f"{pair_path.name}: analysis failed: {error}"
                )

            completed += 1
            progress.update(1)
            progress.set_postfix(
                verdict=verdict,
                completed=completed,
                failed=failures,
                concurrency=concurrency,
                refresh=True,
            )

    print(f"Analysis results: {output_dir}")
    return 1 if failures else 0


def main() -> None:
    raise SystemExit(asyncio.run(run(parse_args())))


if __name__ == "__main__":
    main()
