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
    return parser.parse_args()


def load_target_config(target_name: str) -> dict[str, Any]:
    config_path = configs.base_path / "config" / "configs.yaml"
    with config_path.open("r", encoding="utf-8") as f:
        config_data = yaml.safe_load(f)

    target = config_data.get(target_name)
    if not isinstance(target, dict):
        raise ValueError(f"unknown SUT in {config_path}: {target_name}")

    llm_config = config_data.get("llm_doc")
    if not isinstance(llm_config, dict):
        raise ValueError(f"missing llm_doc configuration in {config_path}")

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
    configs.base_url_doc = str(llm_config.get("base_url", ""))
    configs.api_key_doc = str(llm_config.get("api_key", ""))
    configs.model_doc = str(llm_config.get("model", ""))

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
    ir_path = configs.base_path / "component" / "ir" / protocol
    for rfc_name in dict.fromkeys(rfc_names):
        tree_path = ir_path / f"{rfc_name}.pkl"
        try:
            if not tree_path.is_file():
                raise FileNotFoundError("cache file does not exist")
            with tree_path.open("rb") as f:
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
            reason = f"{tree_path}: {type(error).__name__}: {error}"
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
            "regenerate component/ir caches."
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


def display_bytes(data: bytes, limit: int = 4096) -> dict[str, Any]:
    sample = data[:limit]
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


async def run(args: argparse.Namespace) -> int:
    target = load_target_config(args.sut)
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
    with tqdm(
        total=len(pair_files),
        desc="Compliance analysis",
        unit="pair",
        dynamic_ncols=True,
    ) as progress:
        for pair_path in pair_files:
            progress.set_postfix(
                current=pair_path.name,
                completed=completed,
                failed=failures,
                refresh=True,
            )
            try:
                pair = load_pair(pair_path)
                result = await analyze_pair(
                    chater,
                    target,
                    pair,
                    sections,
                    args.top_k,
                    args.max_section_chars,
                )
                output_path = output_dir / f"{pair_path.stem}.analysis.json"
                with output_path.open("w", encoding="utf-8") as f:
                    json.dump(result, f, indent=2, ensure_ascii=False)
                    f.write("\n")

                analysis = result["analysis"]
                verdict = analysis["verdict"]
                tqdm.write(
                    f"{pair_path.name}: {verdict} "
                    f"({analysis.get('confidence', 0.0)}) - "
                    f"{analysis.get('summary', '')}"
                )
            except Exception as e:
                failures += 1
                verdict = "failed"
                tqdm.write(f"{pair_path.name}: analysis failed: {e}")
            finally:
                completed += 1
                progress.update(1)
                progress.set_postfix(
                    verdict=verdict,
                    completed=completed,
                    failed=failures,
                    refresh=True,
                )

    print(f"Analysis results: {output_dir}")
    return 1 if failures else 0


def main() -> None:
    raise SystemExit(asyncio.run(run(parse_args())))


if __name__ == "__main__":
    main()
