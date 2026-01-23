**Collected Request Message Example**

```
REGISTER sip:127.0.0.1 SIP/2.0
Via: SIP/2.0/UDP 127.0.0.1:5061;branch=z9hG4bK-670-1-0
From: <sip:30@127.0.0.1>;tag=1
To: <sip:30@127.0.0.1>
Call-ID: 1-670@127.0.0.1
CSeq: 1 REGISTER
Contact: sip:30@127.0.0.1:5061
Max-Forwards: 100
Expires: 120
User-Agent: SIPp/Win32
Content-Length: 0
```

```
INVITE sip:33@127.0.0.1:5060 SIP/2.0
Via: SIP/2.0/UDP 127.0.0.1:5061;branch=z9hG4bK-670-1-2
From: sipp <sip:30@127.0.0.1>;tag=1
To: <sip:33@127.0.0.1:5060>
Call-ID: 1-670@127.0.0.1
CSeq: 2 INVITE
Contact: sip:30@127.0.0.1:5061
Max-Forwards: 100
Content-Type: application/sdp
Content-Length:   129

v=0
o=user1 53655765 2353687637 IN IP4 127.0.0.1
s=-
c=IN IP4 127.0.0.1
t=0 0
m=audio 6000 RTP/AVP 8
a=rtpmap:8 PCMA/8000
ACK sip:33@127.0.0.1:5068;ob SIP/2.0
Via: SIP/2.0/UDP 127.0.0.1:5061;branch=z9hG4bK-670-1-7
From: <sip:30@127.0.0.1>;tag=1
To: <sip:33@127.0.0.1>;tag=02cV-oIOVhYnZS3wEzeDPLO.u9i61mwV
Route: <sip:127.0.0.1;lr>
Call-ID: 1-670@127.0.0.1
CSeq: 2 ACK
Contact: sip:30@127.0.0.1:5061
Max-Forwards: 100
Content-Length: 0
```

```
BYE sip:33@127.0.0.1:5068;ob SIP/2.0
Via: SIP/2.0/UDP 127.0.0.1:5061;branch=z9hG4bK-670-1-9
From: <sip:30@127.0.0.1>;tag=1
To: <sip:33@127.0.0.1>;tag=02cV-oIOVhYnZS3wEzeDPLO.u9i61mwV
Route: <sip:127.0.0.1;lr>
Call-ID: 1-670@127.0.0.1
CSeq: 3 BYE
Contact: sip:sipp@127.0.0.1:5061
Max-Forwards: 100
Content-Length: 0
```

**Configuration File of Kamailio Server**
```

fork=no
children=0

/* uncomment the next line to disable TCP (default on) */
disable_tcp=yes

/* uncomment the next line to disable the auto discovery of local aliases
 * based on reverse DNS on IPs (default on) */
auto_aliases=no

/* add local domain aliases */
#alias="sip.mydomain.com"

/* uncomment and configure the following line if you want Kamailio to
 * bind on a specific interface/port/proto (default bind on all available) */
listen=udp:127.0.0.1:5060

/* port to listen to
 * - can be specified more than once if needed to listen on many ports */
port=5060

#!ifdef WITH_TLS
enable_tls=yes
#!endif

/* life time of TCP connection when there is no traffic
 * - a bit higher than registration expires to cope with UA behind NAT */
tcp_connection_lifetime=3605
```