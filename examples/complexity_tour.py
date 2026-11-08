"""Demo: the complexity ladder from trivial to pathological.

Run from the repo root: python examples/complexity_tour.py
"""

from aibi_dax.complexity import report, weight
from aibi_dax.lint import lint_expression

LADDER = [
    "SUM('Sales'[Amount])",
    "CALCULATE([Amount], 'Sales'[Qty] > 0)",
    "IF(HASONEVALUE('S'[k]), VALUES('S'[k]), \"many\")",
    "SUMX(FILTER(ALL('S'), [q] > 0), IF([d] > 0, [x]/[d], 0))",
    "IF(a, 1, IF(b, 2, IF(c, 3, IFERROR([x]/0, 0))))",
]


def main() -> None:
    for expr in LADDER:
        m = report(expr)
        print(
            f"weight {weight(expr):4}  "
            f"deps {m['depth']}  fns {m['functions']:2}  iter {m['iterators']}  "
            f"| {expr[:52]}",
        )
        for finding in lint_expression(expr):
            print(f"      {finding}")


if __name__ == "__main__":
    main()
