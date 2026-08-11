"""Deterministic, local byte-level mutations for fuzzing sequences."""

from __future__ import annotations

from collections import Counter
import random
from dataclasses import dataclass, field


OPERATORS = ("bit_flip", "byte_flip", "arithmetic", "insert", "delete", "duplicate", "block_replace", "boundary", "length_extreme")


@dataclass
class OfflineMutationStats:
    attempts: int = 0
    applied: int = 0
    bytes_added: int = 0
    bytes_removed: int = 0
    operators: Counter[str] = field(default_factory=Counter)


class OfflineMutator:
    """Apply bounded local mutations to the non-prefix part of a sequence."""

    def __init__(self, *, enabled=True, probability=0.3,
                 max_mutated_packets_per_sequence=3, max_mutations_per_packet=4,
                 max_delta_bytes=4, seed=0, mutate_imported_seeds=False,
                 protected_types=(), max_message_length=65536,
                 extreme_message_length=4096):
        self.enabled = bool(enabled)
        self.probability = max(0.0, min(1.0, float(probability)))
        self.max_mutated_packets_per_sequence = max(
            0, int(max_mutated_packets_per_sequence),
        )
        self.max_mutations_per_packet = max(0, int(max_mutations_per_packet))
        self.max_delta_bytes = max(0, int(max_delta_bytes))
        self.mutate_imported_seeds = bool(mutate_imported_seeds)
        self.protected_types = frozenset(str(x) for x in protected_types)
        self.max_message_length = max(1, int(max_message_length))
        self.extreme_message_length = min(
            self.max_message_length, max(1, int(extreme_message_length)),
        )
        self.rand = random.Random(int(seed))
        self.stats = OfflineMutationStats()

    def mutate_sequence(self, sequence, *, prefix_length=0, imported=False):
        sequence = list(sequence)
        if (not self.enabled or not sequence
                or self.max_mutated_packets_per_sequence <= 0
                or self.max_mutations_per_packet <= 0
                or (imported and not self.mutate_imported_seeds)
                or self.rand.random() >= self.probability):
            return sequence, []
        self.stats.attempts += 1
        candidates = [i for i in range(max(0, int(prefix_length)), len(sequence))
                      if sequence[i][0] not in self.protected_types]
        if not candidates:
            return sequence, []
        changed = []
        packet_count = self.rand.randint(
            1, min(self.max_mutated_packets_per_sequence, len(candidates)),
        )
        for index in self.rand.sample(candidates, packet_count):
            msg_type, original = sequence[index]
            mutated = bytes(original)
            mutation_count = self.rand.randint(1, self.max_mutations_per_packet)
            for _ in range(mutation_count):
                operator = self.rand.choice(OPERATORS)
                candidate = self._apply(operator, mutated)
                if (candidate is None or not candidate
                        or len(candidate) > self.max_message_length):
                    continue
                delta = len(candidate) - len(original)
                if operator != 'length_extreme' and abs(delta) > self.max_delta_bytes:
                    continue
                before = len(mutated)
                mutated = candidate
                self.stats.applied += 1
                self.stats.operators[operator] += 1
                self.stats.bytes_added += max(0, len(mutated) - before)
                self.stats.bytes_removed += max(0, before - len(mutated))
                changed.append((index, operator, delta))
            if mutated != original:
                sequence[index] = (msg_type, mutated)
        return sequence, changed

    def _apply(self, operator, data):
        if not data:
            return None
        out = bytearray(data)
        pos = self.rand.randrange(len(out))
        if operator == "bit_flip":
            out[pos] ^= 1 << self.rand.randrange(8)
        elif operator == "byte_flip":
            out[pos] ^= 0xFF
        elif operator == "arithmetic":
            out[pos] = (out[pos] + self.rand.choice((-1, 1, -16, 16))) & 0xFF
        elif operator == "insert":
            out[pos:pos] = bytes([self.rand.randrange(256)])
        elif operator == "delete":
            del out[pos]
        elif operator == "duplicate":
            out[pos:pos] = out[pos:pos + 1]
        elif operator == "block_replace":
            size = min(len(out) - pos, self.rand.randint(1, 4))
            out[pos:pos + size] = bytes(self.rand.randrange(256) for _ in range(size))
        elif operator == "boundary":
            out[pos] = self.rand.choice((0, 1, 0x7F, 0x80, 0xFE, 0xFF))
        elif operator == "length_extreme":
            if self.rand.choice((True, False)):
                return bytes(out[:1])
            padding = bytes(
                self.rand.randrange(256)
                for _ in range(max(0, self.extreme_message_length - len(out)))
            )
            return bytes(out) + padding
        return bytes(out)
