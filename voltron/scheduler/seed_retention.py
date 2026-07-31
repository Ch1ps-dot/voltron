from dataclasses import dataclass

from voltron.executor.conversation import Conversation


ABNORMAL_RESPONSES = {'TIMEOUT', 'CRASH', 'CLOSED', 'POLLERR'}


@dataclass(frozen=True)
class SeedNovelty:
    """Novel behavior found while examining one replayable conversation."""

    interesting: bool
    new_request_response_pairs: list[tuple[str, str, bytes, bytes]]
    new_responses: list[tuple[int, str]]
    request_response_relations: list[tuple[str, str]]


class SeedRetentionPolicy:
    """Stateful, phase-local version of Voltron's interesting-seed rule.

    A conversation is useful when it adds a response transition/type, extends
    the longest observed sequence, introduces a response type within the
    sequence, or exposes a request/response-type relation.
    """

    def __init__(self) -> None:
        self.unique_responses: set[str] = set()
        self.max_unique_response_count = 0
        self.max_sequence_length = 0
        self.seen_request_response_pairs: set[tuple[str, str]] = set()

    @staticmethod
    def is_interesting(
        transition_increment: int,
        response_type_increment: int,
        sequence_length_increment: int,
        unique_response_increment: int,
        request_response_increment: int,
    ) -> bool:
        return (
            transition_increment > 0
            or response_type_increment > 0
            or sequence_length_increment > 0
            or unique_response_increment > 0
            or request_response_increment > 0
        )

    def observe(
        self,
        conversation: Conversation,
        transition_increment: int,
        response_type_increment: int,
    ) -> SeedNovelty:
        """Update phase-local novelty state and return the retention decision."""
        new_pairs: list[tuple[str, str, bytes, bytes]] = []
        new_responses: list[tuple[int, str]] = []
        relations: list[tuple[str, str]] = []

        for index, response_type in enumerate(conversation.res_seq):
            if index >= len(conversation.req_seq):
                continue

            request_type = conversation.req_seq[index]
            if request_type == '-' or response_type == '-':
                continue
            if response_type in ABNORMAL_RESPONSES:
                break

            relations.append((request_type, response_type))
            content = (
                conversation.content[index]
                if index < len(conversation.content)
                else None
            )
            if content is not None:
                request, response = content
                relation = (request_type, response_type)
                if (
                    request
                    and response
                    and relation not in self.seen_request_response_pairs
                ):
                    self.seen_request_response_pairs.add(relation)
                    new_pairs.append((request_type, response_type, request, response))

            if response_type not in self.unique_responses:
                self.unique_responses.add(response_type)
                new_responses.append((index, response_type))

        sequence_length = len(conversation.res_seq)
        unique_response_count = len(set(conversation.res_seq))
        unique_response_increment = (
            unique_response_count - self.max_unique_response_count
        )
        sequence_length_increment = sequence_length - self.max_sequence_length
        self.max_sequence_length = max(
            sequence_length,
            self.max_sequence_length,
        )
        self.max_unique_response_count = max(
            unique_response_count,
            self.max_unique_response_count,
        )

        return SeedNovelty(
            interesting=self.is_interesting(
                transition_increment,
                response_type_increment,
                sequence_length_increment,
                unique_response_increment,
                len(new_pairs),
            ),
            new_request_response_pairs=new_pairs,
            new_responses=new_responses,
            request_response_relations=relations,
        )
