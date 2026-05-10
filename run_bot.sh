#!/bin/bash
# Phase A5: anchor to script directory (works regardless of caller's CWD)
cd "$(dirname "$(realpath "$0")")"
if [ -f ou_mrs.log ] && [ -s ou_mrs.log ]; then
    mv ou_mrs.log "logs/ou_mrs_$(date +%Y%m%d_%H%M%S).log"
fi
exec ./venv/bin/python ./ou_mrs.py
