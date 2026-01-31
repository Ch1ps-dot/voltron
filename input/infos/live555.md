**URL Settings**

"mpeg4ESVideoTest" stream, from the file "test.m4e"
Play this stream using the URL "rtsp://127.0.0.1:8554/mpeg4ESVideoTest"

"h264ESVideoTest" stream, from the file "test.264"
Play this stream using the URL "rtsp://127.0.0.1:8554/h264ESVideoTest"

"h265ESVideoTest" stream, from the file "test.265"
Play this stream using the URL "rtsp://127.0.0.1:8554/h265ESVideoTest"

"mpeg1or2AudioVideoTest" stream, from the file "test.mpg"
Play this stream using the URL "rtsp://127.0.0.1:8554/mpeg1or2AudioVideoTest"

"mpeg1or2ESVideoTest" stream, from the file "testv.mpg"
Play this stream using the URL "rtsp://127.0.0.1:8554/mpeg1or2ESVideoTest"

"mp3AudioTest" stream, from the file "test.mp3"
Play this stream using the URL "rtsp://127.0.0.1:8554/mp3AudioTest"

"wavAudioTest" stream, from the file "test.wav"
Play this stream using the URL "rtsp://127.0.0.1:8554/wavAudioTest"

"amrAudioTest" stream, from the file "test.amr"
Play this stream using the URL "rtsp://127.0.0.1:8554/amrAudioTest"

"vobTest" stream, from the file "test.vob"
Play this stream using the URL "rtsp://127.0.0.1:8554/vobTest"

"mpeg2TransportStreamTest" stream, from the file "test.ts"
Play this stream using the URL "rtsp://127.0.0.1:8554/mpeg2TransportStreamTest"

"aacAudioTest" stream, from the file "test.aac"
Play this stream using the URL "rtsp://127.0.0.1:8554/aacAudioTest"

"dvVideoTest" stream, from the file "test.dv"
Play this stream using the URL "rtsp://127.0.0.1:8554/dvVideoTest"

"ac3AudioTest" stream, from the file "test.ac3"
Play this stream using the URL "rtsp://127.0.0.1:8554/ac3AudioTest"

"matroskaFileTest" stream, from the file "test.mkv"
Play this stream using the URL "rtsp://127.0.0.1:8554/matroskaFileTest"

"webmFileTest" stream, from the file "test.webm"
Play this stream using the URL "rtsp://127.0.0.1:8554/webmFileTest"

"oggFileTest" stream, from the file "test.ogg"
Play this stream using the URL "rtsp://127.0.0.1:8554/oggFileTest"

"opusFileTest" stream, from the file "test.opus"
Play this stream using the URL "rtsp://127.0.0.1:8554/opusFileTest"

"mpeg2TransportStreamFromUDPSourceTest" stream, from a UDP Transport Stream input source 
        (IP multicast address 239.255.42.42, port 1234)
Play this stream using the URL "rtsp://127.0.0.1:8554/mpeg2TransportStreamFromUDPSourceTest"
**Previous Message Example** 

- **Example 1**
DESCRIBE rtsp://127.0.0.1:8554/webmFileTest RTSP/1.0
CSeq: 2
User-Agent: ./testRTSPClient (LIVE555 Streaming Media v2018.08.28)
Accept: application/sdp

SETUP rtsp://127.0.0.1:8554/webmFileTest/track1 RTSP/1.0
CSeq: 3
User-Agent: ./testRTSPClient (LIVE555 Streaming Media v2018.08.28)
Transport: RTP/AVP;unicast;client_port=50494-50495

SETUP rtsp://127.0.0.1:8554/webmFileTest/track2 RTSP/1.0
CSeq: 4
User-Agent: ./testRTSPClient (LIVE555 Streaming Media v2018.08.28)
Transport: RTP/AVP;unicast;client_port=60854-60855
Session: 000022B8

PLAY rtsp://127.0.0.1:8554/webmFileTest/ RTSP/1.0
CSeq: 5
User-Agent: ./testRTSPClient (LIVE555 Streaming Media v2018.08.28)
Session: 000022B8
Range: npt=0.000-

TEARDOWN rtsp://127.0.0.1:8554/webmFileTest/ RTSP/1.0
CSeq: 6
User-Agent: ./testRTSPClient (LIVE555 Streaming Media v2018.08.28)
Session: 000022B8

- **Example 2**
DESCRIBE rtsp://127.0.0.1:8554/wavAudioTest RTSP/1.0
CSeq: 2
User-Agent: ./testRTSPClient (LIVE555 Streaming Media v2018.08.28)
Accept: application/sdp

SETUP rtsp://127.0.0.1:8554/wavAudioTest/track1 RTSP/1.0
CSeq: 3
User-Agent: ./testRTSPClient (LIVE555 Streaming Media v2018.08.28)
Transport: RTP/AVP;unicast;client_port=37952-37953

PLAY rtsp://127.0.0.1:8554/wavAudioTest/ RTSP/1.0
CSeq: 4
User-Agent: ./testRTSPClient (LIVE555 Streaming Media v2018.08.28)
Session: 000022B8
Range: npt=0.000-

TEARDOWN rtsp://127.0.0.1:8554/wavAudioTest/ RTSP/1.0
CSeq: 5
User-Agent: ./testRTSPClient (LIVE555 Streaming Media v2018.08.28)
Session: 000022B8

- **Example 3**
DESCRIBE rtsp://127.0.0.1:8554/mpeg1or2AudioVideoTest RTSP/1.0
CSeq: 2
User-Agent: ./testRTSPClient (LIVE555 Streaming Media v2018.08.28)
Accept: application/sdp

SETUP rtsp://127.0.0.1:8554/mpeg1or2AudioVideoTest/track1 RTSP/1.0
CSeq: 3
User-Agent: ./testRTSPClient (LIVE555 Streaming Media v2018.08.28)
Transport: RTP/AVP;unicast;client_port=50778-50779

SETUP rtsp://127.0.0.1:8554/mpeg1or2AudioVideoTest/track2 RTSP/1.0
CSeq: 4
User-Agent: ./testRTSPClient (LIVE555 Streaming Media v2018.08.28)
Transport: RTP/AVP;unicast;client_port=45546-45547
Session: 000022B8

PLAY rtsp://127.0.0.1:8554/mpeg1or2AudioVideoTest/ RTSP/1.0
CSeq: 5
User-Agent: ./testRTSPClient (LIVE555 Streaming Media v2018.08.28)
Session: 000022B8
Range: npt=0.000-

TEARDOWN rtsp://127.0.0.1:8554/mpeg1or2AudioVideoTest/ RTSP/1.0
CSeq: 6
User-Agent: ./testRTSPClient (LIVE555 Streaming Media v2018.08.28)
Session: 000022B8

- **Example 4**

DESCRIBE rtsp://127.0.0.1:8554/mp3AudioTest RTSP/1.0
CSeq: 2
User-Agent: ./testRTSPClient (LIVE555 Streaming Media v2018.08.28)
Accept: application/sdp

SETUP rtsp://127.0.0.1:8554/mp3AudioTest/track1 RTSP/1.0
CSeq: 3
User-Agent: ./testRTSPClient (LIVE555 Streaming Media v2018.08.28)
Transport: RTP/AVP;unicast;client_port=43712-43713

PLAY rtsp://127.0.0.1:8554/mp3AudioTest/ RTSP/1.0
CSeq: 4
User-Agent: ./testRTSPClient (LIVE555 Streaming Media v2018.08.28)
Session: 000022B8
Range: npt=0.000-

TEARDOWN rtsp://127.0.0.1:8554/mp3AudioTest/ RTSP/1.0
CSeq: 5
User-Agent: ./testRTSPClient (LIVE555 Streaming Media v2018.08.28)
Session: 000022B8

- **Example 5**

DESCRIBE rtsp://127.0.0.1:8554/matroskaFileTest RTSP/1.0
CSeq: 2
User-Agent: ./testRTSPClient (LIVE555 Streaming Media v2018.08.28)
Accept: application/sdp

SETUP rtsp://127.0.0.1:8554/matroskaFileTest/track1 RTSP/1.0
CSeq: 3
User-Agent: ./testRTSPClient (LIVE555 Streaming Media v2018.08.28)
Transport: RTP/AVP;unicast;client_port=37216-37217

SETUP rtsp://127.0.0.1:8554/matroskaFileTest/track2 RTSP/1.0
CSeq: 4
User-Agent: ./testRTSPClient (LIVE555 Streaming Media v2018.08.28)
Transport: RTP/AVP;unicast;client_port=49022-49023
Session: 000022B8

PLAY rtsp://127.0.0.1:8554/matroskaFileTest/ RTSP/1.0
CSeq: 5
User-Agent: ./testRTSPClient (LIVE555 Streaming Media v2018.08.28)
Session: 000022B8
Range: npt=0.000-

TEARDOWN rtsp://127.0.0.1:8554/matroskaFileTest/ RTSP/1.0
CSeq: 6
User-Agent: ./testRTSPClient (LIVE555 Streaming Media v2018.08.28)
Session: 000022B8

- **Example 6**

DESCRIBE rtsp://127.0.0.1:8554/ac3AudioTest RTSP/1.0
CSeq: 2
User-Agent: ./testRTSPClient (LIVE555 Streaming Media v2018.08.28)
Accept: application/sdp

SETUP rtsp://127.0.0.1:8554/ac3AudioTest/track1 RTSP/1.0
CSeq: 3
User-Agent: ./testRTSPClient (LIVE555 Streaming Media v2018.08.28)
Transport: RTP/AVP;unicast;client_port=33900-33901

PLAY rtsp://127.0.0.1:8554/ac3AudioTest/ RTSP/1.0
CSeq: 4
User-Agent: ./testRTSPClient (LIVE555 Streaming Media v2018.08.28)
Session: 000022B8
Range: npt=0.000-