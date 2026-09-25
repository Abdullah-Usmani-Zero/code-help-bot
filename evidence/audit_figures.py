"""Recompute the README's audit figures from pilot_answer_audit.xlsx.

Usage: python evidence/audit_figures.py path/to/pilot_answer_audit.xlsx   (needs openpyxl)
"""

import statistics
import sys
from collections import defaultdict

import openpyxl

TOKENS = "Whole-File Prompt Tokens Sent (tiktoken cl100k_base)"
FABRICATED = "Fabricated Detail An Engineer Had To Correct"
GROUNDED = "Answer Grounded In The Source File (Yes/No)"
CITED = "Cited Where In The File (Yes/No)"
MINUTES = "Correction Time (minutes)"
FILE = "Source File Sent To The Model"

sheet = openpyxl.load_workbook(sys.argv[1], read_only=True).worksheets[0]
header, *body = list(sheet.iter_rows(values_only=True))
rows = [dict(zip(header, r)) for r in body]
fab = [r for r in rows if r[FABRICATED] != "None"]
tokens = [r[TOKENS] for r in rows]

print(f"questions audited:            {len(rows)} ({rows[0]['Date Asked']} to {rows[-1]['Date Asked']})")
print(f"grounded in the source file:  {sum(r[GROUNDED] == 'Yes' for r in rows)}")
print(f"with a fabricated detail:     {len(fab)} ({len(fab) / len(rows):.0%})")
print(f"cited where in the file:      {sum(r[CITED] == 'Yes' for r in rows)}")
print(f"fabricated AND cited:         {sum(r[CITED] == 'Yes' for r in fab)}")
print(f"engineer correction time:     {sum(r[MINUTES] for r in rows)} min ({sum(r[MINUTES] for r in fab) / len(fab):.1f} min per fabrication)")
print(f"prompt tokens sent (audit):   total {sum(tokens)}, mean {statistics.mean(tokens):.0f}, median {statistics.median(tokens)}")
print()
by_file = defaultdict(list)
for r in rows:
    by_file[r[FILE]].append(r)
print(f"{'file':32} {'questions':>9} {'fabricated':>10} {'cited':>5} {'minutes':>7} {'audit tokens':>12}")
for name, rs in sorted(by_file.items()):
    print(f"{name:32} {len(rs):>9} {sum(r[FABRICATED] != 'None' for r in rs):>10} "
          f"{sum(r[CITED] == 'Yes' for r in rs):>5} {sum(r[MINUTES] for r in rs):>7} {rs[0][TOKENS]:>12}")
