"""Demo: lint the README's example expressions end to end.

Run from the repo root: python examples/quick_lint.py
"""

from aibi_dax.complexity import weight
from aibi_dax.lint import lint_expression

SAMPLES = [
    "SUM('Sales'[Amount])",
    "SUMX('Sales', CALCULATE([Amount]))",
    "IF(a, 1, IF(b, 2, IF(c, 3, [D]/[E])))",
    "[x] = BLANK()",
    'SWITCH(TRUE(), [k]="a", 1, [k]="b", 2)',
    'SWITCH(TRUE(), [k]="a", 1, [k]="b", 2, 0)',
    "SUMX('Sales', 'Sales'[Amount])",
    "SUMX('Sales', 'Sales'[Amount] * [Qty])",
    'CONCATENATEX(Sales, "a&b", [x])',
]


def main() -> None:
    for expr in SAMPLES:
        findings = lint_expression(expr)
        print(f"weight {weight(expr):4}  {expr}")
        for finding in findings:
            print(f"   - {finding}")
        if not findings:
            print("   clean")


if __name__ == "__main__":
    main()
