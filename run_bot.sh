#!/bin/bash
cd /home/ubuntu/bots/ou-mrs
if [ -f ou_mrs.log ] && [ -s ou_mrs.log ]; then
    mv ou_mrs.log "logs/ou_mrs_$(date +%Y%m%d_%H%M%S).log"
fi
exec /home/ubuntu/bots/ou-mrs/venv/bin/python /home/ubuntu/bots/ou-mrs/ou_mrs.py
