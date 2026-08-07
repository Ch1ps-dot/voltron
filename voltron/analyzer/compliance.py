import base64
import json
import re
from dataclasses import dataclass
from typing import Any

from fastbm25 import fastbm25


ANALYSIS_SCHEMA = {
    "verdict": "compliant | non_compliant | uncertain",
    "confidence": "number from 0.0 to 1.0",
    "summary": "short conclusion",
    "violations": [
        {
            "rfc": "specification name",
            "section": "section heading",
            "requirement": "normative requirement",
            "observation": "how the response violates it",
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
class SectionRecord:
    rfc: str
    section: str
    content_type: str
    content: str


def collect_response_sections(tree_dict: dict) -> list[SectionRecord]:
    sections = []
    for rfc_name, tree in tree_dict.items():
        for node in tree.leafs:
            if node.content_type not in {"response", "all"}:
                continue
            content = tree.fetch_node_content(node).strip()
            if content:
                sections.append(
                    SectionRecord(
                        rfc=str(rfc_name),
                        section=node.name.strip(),
                        content_type=node.content_type,
                        content=content,
                    )
                )
    return sections


def _bytes_for_query(data: bytes, limit: int = 512) -> str:
    sample = data[:limit]
    return (
        f"{sample.decode('utf-8', errors='backslashreplace')} "
        f"{sample.hex(' ')}"
    )


def retrieve_response_sections(
    sections: list[SectionRecord],
    request_type: str,
    response_type: str,
    request: bytes,
    response: bytes,
    top_k: int = 8,
) -> list[tuple[SectionRecord, float]]:
    if not sections or top_k <= 0:
        return []
    index = fastbm25([section.content.split() for section in sections])
    query = (
        f"{request_type} {response_type} "
        f"{_bytes_for_query(request)} {_bytes_for_query(response)}"
    ).split()
    results = index.top_k_sentence(query, min(top_k, len(sections)))
    return [
        (sections[result[1]], float(result[2]))
        for result in results
    ]


def _display_bytes(data: bytes, limit: int = 4096) -> dict[str, Any]:
    sample = data[:limit]
    try:
        content = sample.decode("utf-8")
    except UnicodeDecodeError:
        encoding = "base64"
        content = base64.b64encode(sample).decode("ascii")
    else:
        encoding = "utf-8"
    return {
        "length": len(data),
        "truncated": len(sample) < len(data),
        "encoding": encoding,
        "data": content,
    }


def build_compliance_prompt(
    protocol: str,
    request_type: str,
    response_type: str,
    request: bytes,
    response: bytes,
    retrieved: list[tuple[SectionRecord, float]],
    max_section_chars: int = 6000,
) -> str:
    context = [
        {
            "rfc": section.rfc,
            "section": section.section,
            "content": section.content[:max_section_chars],
        }
        for section, _score in retrieved
    ]

    exchange = {
        "request_type": request_type,
        "response_type": response_type,
        "request": _display_bytes(request),
        "response": _display_bytes(response),
    }
    return (
        "TASK\nJudge whether a checker-rejected response violates the protocol "
        "or is a checker false positive.\n\n"
        "INPUT\n"
        f"PROTOCOL: {protocol}\n"
        f"EXCHANGE_JSON: {json.dumps(exchange, separators=(',', ':'))}\n"
        f"SPEC_CONTEXT_JSON: {json.dumps(context, separators=(',', ':'))}\n\n"
        "RULES\nUse non_compliant only for a normative wire-format, semantic, "
        "or sequencing rule contradicted by the response. Use compliant when "
        "permitted and the checker is too strict; uncertain when evidence is "
        "insufficient. Do not invent requirements.\n\n"
        "OUTPUT\nJSON only matching: "
        f"{json.dumps(ANALYSIS_SCHEMA, separators=(',', ':'))}"
    )


def parse_compliance_result(response: str | None) -> dict[str, Any]:
    fallback = {
        "verdict": "uncertain",
        "confidence": 0.0,
        "summary": "The model did not return a valid compliance judgment.",
        "violations": [],
        "evidence": [],
    }
    if not response:
        return fallback

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
            return {**fallback, "raw_model_response": response}
        try:
            result, _ = json.JSONDecoder().raw_decode(cleaned[start:])
        except json.JSONDecodeError:
            return {**fallback, "raw_model_response": response}

    if not isinstance(result, dict):
        return {**fallback, "raw_model_response": response}
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
