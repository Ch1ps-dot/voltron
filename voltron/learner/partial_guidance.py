"""Partial-learning evidence retained for safe fuzzing guidance.

An incomplete observation table is not a Mealy machine: it can contain rows
whose successors are unknown or whose future behavior has not been
distinguished.  This module therefore stores concrete, replayable traces
instead of inventing state identifiers or transition destinations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Iterable

from voltron.executor.conversation import Conversation


ABNORMAL_RESPONSES = {'TIMEOUT', 'CRASH', 'CLOSED', 'POLLERR'}


@dataclass(frozen=True)
class PartialTrace:
    """One successful concrete request prefix observed by a membership query."""

    messages: tuple[tuple[str, bytes], ...]
    responses: tuple[str, ...]

    @property
    def symbols(self) -> tuple[str, ...]:
        return tuple(symbol for symbol, _message in self.messages)


@dataclass
class PartialStateGraph:
    """Replayable evidence for prefix/frontier guidance, never a full model."""

    fingerprint: dict[str, object]
    traces: list[PartialTrace] = field(default_factory=list)
    request_response_pairs: set[tuple[str, str]] = field(default_factory=set)
    response_symbols: set[str] = field(default_factory=set)
    executed_symbols: set[str] = field(default_factory=set)
    conflicts: list[dict[str, object]] = field(default_factory=list)
    table_snapshot: tuple[set, set, dict] | None = None
    reason: str = 'threshold_drained_partial'

    def seed_sequences(self) -> list[list[tuple[str, bytes]]]:
        """Return concrete sequences usable by the existing Berserker seed path."""
        unique: dict[tuple[tuple[str, bytes], ...], PartialTrace] = {}
        for trace in self.traces:
            if trace.messages:
                unique.setdefault(trace.messages, trace)
        return [list(trace.messages) for trace in unique.values()]

    def frontier_for(self, trace: PartialTrace, alphabet: Iterable[str]) -> set[str]:
        """Inputs not yet observed after this exact prefix.

        The graph deliberately does not infer a destination state.  A caller
        may use this only as an exploration preference.
        """
        prefix = trace.symbols
        seen = {
            symbol
            for candidate in self.traces
            if candidate.symbols[:-1] == prefix and candidate.symbols
            for symbol in candidate.symbols[-1:]
        }
        return set(alphabet) - seen


class PartialTraceRecorder:
    """Collect successful MQ conversations and track request/response novelty."""

    def __init__(self) -> None:
        self.graph = PartialStateGraph(fingerprint={})

    def observe(self, conversation: Conversation) -> bool:
        """Record a complete normal conversation and return whether pairs grew."""
        messages: list[tuple[str, bytes]] = []
        responses: list[str] = []
        pairs_before = len(self.graph.request_response_pairs)

        for index, response in enumerate(conversation.res_seq):
            if index >= len(conversation.req_seq):
                return False
            symbol = conversation.req_seq[index]
            if symbol == '-':
                # Initial greetings are connection events, not model inputs.
                continue
            if (
                response in ABNORMAL_RESPONSES
                or response in {'', '-', 'UNKNOWN'}
                or index >= len(conversation.content)
            ):
                return False
            request, raw_response = conversation.content[index]
            if not request or not raw_response:
                return False
            messages.append((symbol, request))
            responses.append(response)
            self.graph.executed_symbols.add(symbol)
            self.graph.response_symbols.add(response)
            self.graph.request_response_pairs.add((symbol, response))

        if not messages:
            return False
        self.graph.traces.append(
            PartialTrace(tuple(messages), tuple(responses))
        )
        return len(self.graph.request_response_pairs) > pairs_before

    def snapshot(
        self,
        fingerprint: dict[str, object],
        table_snapshot: tuple[set, set, dict],
        reason: str,
    ) -> PartialStateGraph:
        self.graph.fingerprint = dict(fingerprint)
        self.graph.table_snapshot = table_snapshot
        self.graph.reason = reason
        return self.graph


class ModelLearningThreshold:
    """Input/output-scaled no-growth threshold for model-learning MQs."""

    def __init__(self, alphabet: Iterable[str]) -> None:
        self.alphabet = {symbol for symbol in alphabet if symbol != '-'}
        self.no_growth_mq = 0
        self.reached = False
        self.threshold = 0
        self.round_size = 0
        self.rounds = 0

    def observe(self, recorder: PartialTraceRecorder, pair_grew: bool) -> bool:
        """Update after one successful MQ and return whether the gate is reached."""
        if self.reached:
            return True
        # Do not let a homogeneous bootstrap response stop learning before all
        # input symbols have been exercised once.
        if not self.alphabet.issubset(recorder.graph.executed_symbols):
            return False

        input_count = max(1, len(self.alphabet))
        output_count = max(1, len(recorder.graph.response_symbols))
        pair_space = input_count * output_count
        self.round_size = max(input_count, math.ceil(math.sqrt(pair_space)))
        self.rounds = min(6, max(2, math.ceil(math.log2(pair_space + 1))))
        self.threshold = self.round_size * self.rounds

        if pair_grew:
            self.no_growth_mq = 0
        else:
            self.no_growth_mq += 1
        self.reached = self.no_growth_mq >= self.threshold
        return self.reached
