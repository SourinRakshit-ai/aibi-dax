"""Demo: lint the README's example expressions end to end.

Run from the repo root: python examples/quick_lint.py
"""

from aibi_dax.complexity import weight
from aibi_dax.lint import lint_expression

SAMPLES = [
    "SUM('Sales'[Amount])",
    "SUMX('Sales', CALCULATE([Amount]))",
    "IF(a, 1, IF(b, 2, IF(c, 3, [D]/0)))",
    "[x] = BLANK()",
]


def main() -> None:
    for expr in SAMPLES:
        print(f"weight {weight(expr):4}  {expr}")
        for finding in lint_expression(expr):
            print(f"   - {finding}")
        if not lint_expression(expr):
            print("   clean")


if __name__ == "__main__":
    main()
