#!/bin/bash
export KAMAILIO_MODULES="src/modules"
export KAMAILIO_RUNTIME_DIR="runtime_dir"
WORKDIR="/home/ubuntu/experiments"

./src/kamailio -f ${WORKDIR}/kamailio-basic.cfg -L $KAMAILIO_MODULES -Y $KAMAILIO_RUNTIME_DIR -n 1 -D -E