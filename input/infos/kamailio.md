**SIP User information**
Act as user 30 on 127.0.0.1:5061 to send request messages, enabling communication with user 33 on 127.0.0.1:5068.

**Configuration File of Kamailio Server**

kamailio server configs:
```
The server is listening to 127.0.0.1:5060

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