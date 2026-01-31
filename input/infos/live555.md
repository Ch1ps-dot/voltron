
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