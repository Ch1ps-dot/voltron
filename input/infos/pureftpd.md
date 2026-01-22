- Server information: The FTP server will run in local mode. The password of the user **ubuntu** on the local server is **ubuntu**.
- Server information: The FTP server will run in local mode. The password of the user **fuzzing** on the local server is **fuzzing**.
-  Commandline: src/pure-ftpd -A -S 127.0.0.1,2121
    Listens exclusively on the local loopback address (127.0.0.1) and port 2121 (no external network access).
    Rejects all anonymous FTP connections, requiring valid user authentication for any FTP access.
    Runs from the src/ directory (likely a development/test build of Pure-FTPd).