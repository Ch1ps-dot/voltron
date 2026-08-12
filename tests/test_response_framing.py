from voltron.executor.executor import Executor
from voltron.executor.response_framing import split_response_frames


def test_ftp_multiline_reply_is_one_frame():
    data = b'214-First line\r\nMore help\r\n214 End\r\n'
    frames = split_response_frames('ftp', data)
    assert [frame.data for frame in frames] == [data]


def test_ftp_staged_replies_are_distinct_frames():
    data = b'150 opening data\r\n226 done\r\n'
    frames = split_response_frames('ftp', data)
    assert [frame.data for frame in frames] == [
        b'150 opening data\r\n', b'226 done\r\n',
    ]


def test_http_content_length_keeps_two_responses_separate():
    first = b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nOK'
    second = b'HTTP/1.1 204 No Content\r\n\r\n'
    frames = split_response_frames('http', first + second)
    assert [frame.data for frame in frames] == [first, second]


def test_incomplete_frame_is_retained_without_byte_loss():
    data = b'HTTP/1.1 200 OK\r\nContent-Length: 9\r\n\r\nshort'
    frames = split_response_frames('http', data)
    assert len(frames) == 1
    assert frames[0].data == data


def test_model_response_symbol_preserves_single_and_encodes_multi_frames():
    assert Executor._model_response_symbol(
        [{'response_type': '226', 'parse_status': 'parsed'}], '226',
    ) == '226'
    assert Executor._model_response_symbol(
        [
            {'response_type': '150', 'parse_status': 'parsed'},
            {'response_type': '125', 'parse_status': 'parsed'},
            {'response_type': '226', 'parse_status': 'parsed'},
        ],
        '226',
    ) == '["150","125","226"]'


def test_model_response_symbol_ignores_unparsed_frames():
    assert Executor._model_response_symbol(
        [
            {'response_type': '150', 'parse_status': 'parsed'},
            {'response_type': 'PARSE_FAILURE', 'parse_status': 'parse_failure'},
            {'response_type': '226', 'parse_status': 'parsed'},
        ],
        '226',
    ) == '["150","226"]'
