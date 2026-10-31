#!/bin/sh
set -eu
exec python "$(dirname "$0")/build_ipk.py"
