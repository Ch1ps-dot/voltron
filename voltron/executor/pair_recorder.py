import base64
import hashlib
import json
import os
import threading
from pathlib import Path

from voltron.executor.conversation import Conversation
from voltron.utils.logger import logger_fuzz as logger


ABNORMAL_RESPONSES = {'TIMEOUT', 'CRASH', 'CLOSED', 'POLLERR'}


class RequestResponsePairRecorder:
    """Persist first-seen request/response relations from every runtime phase."""

    def __init__(self, results_path: Path) -> None:
        self.target_folder = results_path / 'request_response_pairs'
        self._seen_relations: set[tuple[str, str]] = set()
        self._next_id = 0
        self._lock = threading.Lock()

    def observe(
        self,
        conversation: Conversation,
        phase: str = '',
        component_evidence: dict[tuple[str, str, str], dict] | None = None,
    ) -> int:
        """Record eligible relations and return the number of new pair files."""
        saved = 0
        limit = min(
            len(conversation.req_seq),
            len(conversation.res_seq),
            len(conversation.content),
        )
        for index in range(limit):
            request_type = conversation.req_seq[index]
            response_type = conversation.res_seq[index]
            request, response = conversation.content[index]
            if (
                request_type == '-'
                or response_type == '-'
                or response_type in ABNORMAL_RESPONSES
                or not request
                or not response
            ):
                continue
            if self._save_pair(
                request_type=request_type,
                response_type=response_type,
                request=request,
                response=response,
                phase=phase,
                component_evidence=(
                    component_evidence or {}
                ).get((
                    request_type,
                    response_type,
                    hashlib.sha256(response).hexdigest(),
                )),
            ):
                saved += 1
        return saved

    def _save_pair(
        self,
        request_type: str,
        response_type: str,
        request: bytes,
        response: bytes,
        phase: str,
        component_evidence: dict | None = None,
    ) -> bool:
        relation = (request_type, response_type)
        with self._lock:
            if relation in self._seen_relations:
                return False

            self.target_folder.mkdir(parents=True, exist_ok=True)
            while True:
                file_path = self.target_folder / f'pair_{self._next_id:06d}.json'
                self._next_id += 1
                if not file_path.exists():
                    break

            digest = hashlib.sha256()
            digest.update(request_type.encode('utf-8', errors='replace'))
            digest.update(b'\0')
            digest.update(response_type.encode('utf-8', errors='replace'))
            digest.update(b'\0')
            digest.update(request)
            digest.update(b'\0')
            digest.update(response)
            data = {
                'request_type': request_type,
                'response_type': response_type,
                'request_length': len(request),
                'response_length': len(response),
                'request': {
                    'encoding': 'base64',
                    'data': base64.b64encode(request).decode('ascii'),
                },
                'response': {
                    'encoding': 'base64',
                    'data': base64.b64encode(response).decode('ascii'),
                },
                'phase': phase or 'unknown',
                'conversation_digest': digest.hexdigest(),
                'runtime_components': component_evidence or {
                    'checker': {
                        'status': 'unchecked',
                        'scope': 'none',
                        'component_type': None,
                        'error': 'checker was not enabled for this exchange',
                    },
                    'observer': {
                        'semantic_fingerprint': hashlib.sha256(
                            response
                        ).hexdigest(),
                        'raw_fingerprint': hashlib.sha256(response).hexdigest(),
                        'scope': 'raw',
                        'component_type': None,
                        'provisional': True,
                        'error': 'observer evidence was not recorded',
                    },
                },
            }
            temporary_path = file_path.with_name(
                f'.{file_path.name}.{os.getpid()}.{threading.get_ident()}.tmp'
            )
            try:
                with temporary_path.open('x', encoding='utf-8') as stream:
                    json.dump(data, stream, indent=2)
                    stream.write('\n')
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary_path, file_path)
            except Exception:
                temporary_path.unlink(missing_ok=True)
                logger.exception(
                    'PairRecorder: failed to save relation %s/%s',
                    request_type,
                    response_type,
                )
                return False

            self._seen_relations.add(relation)
            logger.debug(
                'PairRecorder: saved relation %s/%s from %s to %s',
                request_type,
                response_type,
                phase or 'unknown',
                file_path.name,
            )
            return True
