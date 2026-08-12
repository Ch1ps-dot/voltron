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
