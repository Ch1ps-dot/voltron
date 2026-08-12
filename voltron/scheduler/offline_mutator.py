"""Deterministic, local byte-level mutations for fuzzing sequences."""

from __future__ import annotations

from collections import Counter
import random
from dataclasses import dataclass, field


OPERATORS = ("bit_flip", "byte_flip", "arithmetic", "insert", "delete", "duplicate", "block_replace", "boundary", "length_extreme")

# AFLNet inherits AFL's byte-level stages for a selected message.  Splicing is
# deliberately excluded: this mutator is local to one packet and must not
# change the sequence scheduler's prefix/dependency semantics.
AFLNET_SINGLE_PACKET_OPERATORS = (
    "aflnet_bitflip_1", "aflnet_bitflip_2", "aflnet_bitflip_4",
    "aflnet_byteflip_1", "aflnet_byteflip_2", "aflnet_byteflip_4",
    "aflnet_arith_8", "aflnet_arith_16", "aflnet_arith_32",
    "aflnet_interest_8", "aflnet_interest_16", "aflnet_interest_32",
    "aflnet_dict_overwrite", "aflnet_dict_insert", "aflnet_havoc",
)

_INTERESTING_8 = (0, 1, 16, 32, 64, 100, 127, 128, 255)
_INTERESTING_16 = (0, 1, 16, 32, 64, 100, 127, 128, 255, 256, 512,
                   1000, 1024, 32767, 32768, 65535)
_INTERESTING_32 = (0, 1, 16, 32, 64, 100, 127, 128, 255, 256, 512,
                   1000, 1024, 65535, 65536, 100663045, 2147483647,
                   2147483648, 4294967295)


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
                 max_delta_bytes=4, seed=0, mutate_imported_seeds=True,
                 protected_types=(), max_message_length=65536,
                 extreme_message_length=4096, aflnet_single_packet=True,
                 aflnet_dictionary=(), aflnet_havoc_stack=4):
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
        self.aflnet_single_packet = bool(aflnet_single_packet)
        self.aflnet_dictionary = tuple(
            token if isinstance(token, bytes) else str(token).encode("utf-8")
            for token in aflnet_dictionary
            if token
        )
        self.aflnet_havoc_stack = max(2, int(aflnet_havoc_stack))
        self.operators = OPERATORS + (
            AFLNET_SINGLE_PACKET_OPERATORS if self.aflnet_single_packet else ()
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
                operator = self.rand.choice(self.operators)
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
        elif operator.startswith("aflnet_"):
            return self._apply_aflnet(operator, bytes(out))
        return bytes(out)

    def _apply_aflnet(self, operator, data):
        """Apply one AFL/AFLNet single-message stage without sequence splicing."""
        if operator.startswith("aflnet_bitflip_"):
            width = int(operator.rsplit("_", 1)[1])
            total_bits = len(data) * 8
            if total_bits < width:
                return None
            bit = self.rand.randrange(total_bits - width + 1)
            value = int.from_bytes(data, "little") ^ (((1 << width) - 1) << bit)
            return value.to_bytes(len(data), "little")
        if operator.startswith("aflnet_byteflip_"):
            width = int(operator.rsplit("_", 1)[1])
            if len(data) < width:
                return None
            out = bytearray(data)
            pos = self.rand.randrange(len(out) - width + 1)
            for index in range(pos, pos + width):
                out[index] ^= 0xFF
            return bytes(out)
        if operator.startswith("aflnet_arith_"):
            return self._aflnet_arithmetic(data, int(operator.rsplit("_", 1)[1]) // 8)
        if operator.startswith("aflnet_interest_"):
            return self._aflnet_interesting(data, int(operator.rsplit("_", 1)[1]) // 8)
        if operator == "aflnet_dict_overwrite":
            return self._aflnet_dictionary_mutation(data, insert=False)
        if operator == "aflnet_dict_insert":
            return self._aflnet_dictionary_mutation(data, insert=True)
        if operator == "aflnet_havoc":
            return self._aflnet_havoc(data)
        return None

    def _aflnet_arithmetic(self, data, width):
        if len(data) < width:
            return None
        out = bytearray(data)
        pos = self.rand.randrange(len(out) - width + 1)
        byteorder = self.rand.choice(("little", "big")) if width > 1 else "little"
        value = int.from_bytes(out[pos:pos + width], byteorder)
        delta = self.rand.choice((-35, -16, -1, 1, 16, 35))
        out[pos:pos + width] = ((value + delta) % (1 << (width * 8))).to_bytes(
            width, byteorder,
        )
        return bytes(out)

    def _aflnet_interesting(self, data, width):
        if len(data) < width:
            return None
        values = {1: _INTERESTING_8, 2: _INTERESTING_16, 4: _INTERESTING_32}[width]
        out = bytearray(data)
        pos = self.rand.randrange(len(out) - width + 1)
        byteorder = self.rand.choice(("little", "big")) if width > 1 else "little"
        out[pos:pos + width] = self.rand.choice(values).to_bytes(width, byteorder)
        return bytes(out)

    def _aflnet_dictionary_mutation(self, data, *, insert):
        if not self.aflnet_dictionary:
            return None
        token = self.rand.choice(self.aflnet_dictionary)
        if insert:
            pos = self.rand.randrange(len(data) + 1)
            return data[:pos] + token + data[pos:]
        if len(token) > len(data):
            return None
        pos = self.rand.randrange(len(data) - len(token) + 1)
        return data[:pos] + token + data[pos + len(token):]

    def _aflnet_havoc(self, data):
        """AFL-style stacked local edits, bounded by normal acceptance checks."""
        stages = tuple(op for op in self.operators
                       if op not in {"length_extreme", "aflnet_havoc"})
        result = data
        for _ in range(self.rand.randint(2, self.aflnet_havoc_stack)):
            candidate = self._apply(self.rand.choice(stages), result)
            if candidate and len(candidate) <= self.max_message_length:
                result = candidate
        return result
