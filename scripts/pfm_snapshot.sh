#!/bin/bash
cd "$(dirname "$(realpath "$0")")/.."  # Phase A5: scripts/ -> repo root
LOG=$(ls -t logs/ou_mrs_*.log 2>/dev/null | head -1)
[ -f "$LOG" ] || exit 0
DICT=$(grep -E "\[pfm\] (init|EOD|status)" "$LOG" | tail -1 | grep -oP '\{.*\}$')
[ -z "$DICT" ] && exit 0
mkdir -p state
venv/bin/python3 -c "
import re, json, datetime, ast
s = '''$DICT'''
s = re.sub(r'np\.float64\(([^)]+)\)', r'\1', s)
s = s.replace('np.True_', 'True').replace('np.False_', 'False')
data = ast.literal_eval(s)
data['snapshot_at'] = datetime.datetime.now().isoformat()
data['source'] = 'pfm_snapshot.sh'
open('state/pfm.json', 'w').write(json.dumps(data, indent=2))
"
