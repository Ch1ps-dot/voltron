#!/bin/bash
/home/ubuntu/experiments/atftp/atftpd \
  --daemon \
  --no-fork \
  --port 6969 \
  --bind-address 127.0.0.1 \
  --logfile - \
  --verbose=5 \
  /tmp/tftp-root