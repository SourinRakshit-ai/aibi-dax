"""Rule-engine benchmark: per-rule timing over a synthetic corpus.

Run:  python examples/bench_rules.py
"""

from __future__ import annotations

import time

from aibi_dax.antipattern import ALL_RULES
from aibi_dax.lint import lint_expression, lint_model

CORPUS = [
    "[Amount]",
    "SUM('Sales'[Amount])",
    "[Amount] / [Scale]",
    "[Amount] / 2",
    'DIVIDE([A], [B], "n/a")',
    "[x] = BLANK()",
    "ISBLANK([x])",
    "IF(a, 1, IF(b, 2, IF(c, 3, [D]/[E])))",
    'SWITCH(TRUE(), [k]="a", 1, [k]="b", 2)',
    'SWITCH(TRUE(), [k]="a", 1, [k]="b", 2, 0)',
    'CONCATENATEX(Sales, "Q" & [Month], "-")',
    'CONCATENATEX(Sales, "a&b", [x])',
    "SUMX('Sales', CALCULATE([Amount]))",
    "SUMX('Sales', AVERAGEX('Sales', [x]))",
    "VAR k = [Amount] * 2 RETURN IF(k > 100, k, 0)",
    "VAR s = SUMX('S', [x]) RETURN s",
    "CALCULATE([Amount], ALL('Sales'))",
    "CALCULATE([Amount], 'Sales'[Qty] > 0)",
    "IFERROR([A] / [B], 0)",
    "IF(HASONEVALUE([k]), VALUES([k]), 0)",
    "sum('Sales'[amount])",
    "EARLIER([k])",
    # logic and constant collapses
    "NOT(NOT([x]))",
    "[x] || NOT([x])",
    "IF(TRUE(), 1, 2)",
    "IF(1 = 1, 2, 3)",
    "SWITCH(TRUE(), TRUE(), 1, 2)",
    "OR(TRUE(), [x])",
    # numeric and identity shapes
    "[x] * 1",
    "[x] * -1",
    "DIVIDE([x], 0)",
    "DIVIDE([x], 1)",
    "ROUND(ROUND([x], 2), 2)",
    "ABS(ABS([x]))",
    "ABS([x]) < 0",
    # COALESCE / IF / BLANK families
    "COALESCE([x], BLANK())",
    "COALESCE(BLANK(), [x])",
    "COALESCE([x], BLANK(), [y])",
    "COALESCE([x], [x])",
    "IF(ISBLANK([x]), 0, [x])",
    "IF(ISBLANK([x]), x, BLANK())",
    "ISBLANK(BLANK())",
    "MAX([x], BLANK())",
    "COUNTROWS('T') = 0",
    "COUNTROWS('T') >= 1",
    "COUNTROWS(FILTER('T', FALSE()))",
    "DISTINCTCOUNT(VALUES([x]))",
    # VAR, switch and iterator shapes
    "VAR a = [x] RETURN a",
    "VAR a = 1 RETURN 2",
    "IF([x] = 1, 2, IF([x] = 2, 3, 4))",
    "SWITCH([x], 1, 2, 1, 3, 4)",
    "SUMX('T', [a] + 0)",
    "SUMX('T', [a] * 1)",
    "MAX([x], [x])",
    "CONCATENATE([a], [b])",
    "[x] IN {}",
]

MODEL = {
    "tables": [
        {"name": f"T{i}", "measures": [{"name": f"M{j}", "expression": e} for j, e in enumerate(CORPUS)]}
        for i in range(4)
    ]
}


def bench_per_rule(rounds: int = 50) -> None:
    print(f"per-rule mean over {rounds} rounds x {len(CORPUS)} expressions")
    for rule in ALL_RULES:
        start = time.perf_counter()
        for _ in range(rounds):
            for expr in CORPUS:
                rule(expr)
        mean = (time.perf_counter() - start) / (rounds * len(CORPUS)) * 1e6
        print(f"  {rule.__name__:24}{mean:8.1f} us/expr")


def bench_pipeline(rounds: int = 20) -> None:
    start = time.perf_counter()
    for _ in range(rounds):
        for expr in CORPUS:
            lint_expression(expr)
    lint_mean = (time.perf_counter() - start) / (rounds * len(CORPUS)) * 1e6

    start = time.perf_counter()
    for _ in range(rounds):
        lint_model(MODEL)
    model_mean = (time.perf_counter() - start) / rounds * 1e3

    print(f"lint_expression {lint_mean:8.1f} us/expr   lint_model {model_mean:6.1f} ms/model")


if __name__ == "__main__":
    bench_per_rule()
    bench_pipeline()
