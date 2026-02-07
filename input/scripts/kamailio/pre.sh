#!/bin/bash
export KAMAILIO_MODULES="src/modules"
export KAMAILIO_RUNTIME_DIR="runtime_dir"
WORKDIR="/home/ubuntu/experiments"

./src/kamailio -f /home/ubuntu/experiments/kamailio-basic.cfg -L src/modules -Y runtime_dir -n 1 -D -E