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
    return {
        "length": len(data),
        "truncated": len(sample) < len(data),
        "text": sample.decode("utf-8", errors="backslashreplace"),
        "hex": sample.hex(" "),
        "base64": base64.b64encode(sample).decode("ascii"),
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
    context = []
    for number, (section, score) in enumerate(retrieved, start=1):
        context.append(
            f"[SPEC {number}]\n"
            f"RFC: {section.rfc}\n"
            f"Section: {section.section}\n"
            f"Annotation: {section.content_type}\n"
            f"BM25 score: {score:.4f}\n"
            f"Content:\n{section.content[:max_section_chars]}"
        )

    exchange = {
        "request_type": request_type,
        "response_type": response_type,
        "request": _display_bytes(request),
        "response": _display_bytes(response),
    }
    return (
        "Determine whether this response violates the protocol specification. "
        "The local checker rejected it, but that rejection may be a checker "
        "false positive.\n\n"
        f"Protocol: {protocol}\n"
        f"Captured exchange:\n{json.dumps(exchange, indent=2)}\n\n"
        f"Retrieved response-structure sections:\n{'\n\n'.join(context)}\n\n"
        "Use non_compliant only when the retrieved specification contains a "
        "normative wire-format, semantic, or sequencing constraint that the "
        "response violates. Use compliant when the response is permitted and "
        "the local checker is too strict. Use uncertain when the supplied "
        "sections are insufficient. Return only one JSON object matching:\n"
        f"{json.dumps(ANALYSIS_SCHEMA, indent=2)}"
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
