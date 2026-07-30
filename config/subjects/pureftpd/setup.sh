#!/bin/bash

# Do not clear /home/ubuntu: benchmark containers run from a copied source
# tree there, and deleting it loses results before they can be archived.
set -euo pipefail

pkill pure-ftpd > /dev/null 2>&1 || true
