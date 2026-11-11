"""Parse tour: watch the AST grow as expressions gain structure.

Run:  python examples/parse_tour.py
"""

from __future__ import annotations

from aibi_dax.parser import parse

EXPRESSIONS = [
    ("a bare column", "[Amount]"),
    ("addition", "[Amount] + [Tax]"),
    ("precedence", "1 + 2 * 3"),
    ("a function call", "SUM('Sales'[Amount])"),
    ("an iterator with CALCULATE", "SUMX('Sales', CALCULATE([Amount]))"),
    ("SWITCH with a default", 'SWITCH([Size], "L", 1, "XL", 2, 0)'),
    ("a VAR block", "VAR k = [Amount] * 2 RETURN IF(k > 100, k, 0)"),
]

for label, expr in EXPRESSIONS:
    print(f"── {label}: {expr}")
    print(f"   {parse(expr)}\n")
