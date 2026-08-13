import socket

from voltron.executor.executor import Executor
from voltron.executor.response_framing import split_response_frames
from voltron.configs import configs


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
    assert frames[0].framing_status == 'framing_incomplete'
    assert frames[0].framing_error == 'declared_content_length_exceeds_receive_batch'


def test_sip_staged_responses_are_distinct_frames():
    first = b'SIP/2.0 100 Trying\r\nContent-Length: 0\r\n\r\n'
    second = b'SIP/2.0 415 Unsupported Media Type\r\nContent-Length: 0\r\n\r\n'
    frames = split_response_frames('sip', first + second)
    assert [frame.data for frame in frames] == [first, second]
    assert all(frame.framing_status == 'framed' for frame in frames)


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


def test_response_batch_parses_every_sip_frame_and_uses_final_output():
    executor = Executor.__new__(Executor)
    executor._recv_batch_id = 0
    executor.parser_func = lambda frame: frame.split(b' ', 2)[1]
    old_protocol = getattr(configs, 'pro_name', '')
    configs.pro_name = 'sip'
    try:
        data = (
            b'SIP/2.0 100 Trying\r\nContent-Length: 0\r\n\r\n'
            b'SIP/2.0 415 Unsupported Media Type\r\nContent-Length: 0\r\n\r\n'
        )
        frames = executor._parse_response_frames(
            data,
            'INVITE',
            False,
            datagrams=[{
                'index': 0,
                'offset_start': 0,
                'offset_end': len(data),
                'timestamp': 0.0,
            }],
        )
    finally:
        configs.pro_name = old_protocol

    assert [frame['response_type'] for frame in frames] == ['100', '415']
    assert [frame['parse_status'] for frame in frames] == ['parsed', 'parsed']
    assert Executor._response_batch_result(frames) == '415'
    assert all(frame['datagrams'][0]['index'] == 0 for frame in frames)


def test_incomplete_sip_frame_is_not_sent_to_the_packet_parser():
    executor = Executor.__new__(Executor)
    executor._recv_batch_id = 0
    executor.parser_func = lambda _: (_ for _ in ()).throw(AssertionError())
    old_protocol = getattr(configs, 'pro_name', '')
    configs.pro_name = 'sip'
    try:
        frames = executor._parse_response_frames(
            b'SIP/2.0 200 OK\r\nContent-Length: 9\r\n\r\nshort',
            'INVITE',
            False,
        )
    finally:
        configs.pro_name = old_protocol

    assert frames[0]['parse_status'] == 'framing_incomplete'
    assert frames[0]['framing_error'] == 'declared_content_length_exceeds_receive_batch'


def test_udp_receive_tracks_datagrams_and_uses_final_sip_response():
    receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    receiver.bind(('127.0.0.1', 0))
    old_protocol = getattr(configs, 'pro_name', '')
    configs.pro_name = 'sip'
    try:
        sender.sendto(
            b'SIP/2.0 100 Trying\r\nContent-Length: 0\r\n\r\n',
            receiver.getsockname(),
        )
        sender.sendto(
            b'SIP/2.0 415 Unsupported Media Type\r\nContent-Length: 0\r\n\r\n',
            receiver.getsockname(),
        )
        executor = Executor.__new__(Executor)
        executor._recv_batch_id = 0
        executor.trans_layer = 'udp'
        executor.max_timeout_ms = 100
        executor.parser_func = lambda frame: frame.split(b' ', 2)[1]
        executor._should_stop = lambda: False

        response_type, _ = executor.net_recv(receiver, msg_type='INVITE')
    finally:
        configs.pro_name = old_protocol
        receiver.close()
        sender.close()

    assert response_type == '415'
    assert [
        frame['response_type'] for frame in executor._last_response_frames
    ] == ['100', '415']
    assert [
        frame['datagrams'][0]['index']
        for frame in executor._last_response_frames
    ] == [0, 1]
