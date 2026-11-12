# Security Policy

## Scope

`aibi-dax` is a static analyzer: it reads DAX expression text you feed it
and reports findings. It does not execute DAX, connect to data sources,
or handle credentials.

## Supported versions

| Version | Supported |
| ------- | --------- |
| 0.2.x   | yes       |
| < 0.2   | no        |

## What counts as a security issue here

- ReDoS or a hang triggered by adversarial expression input to the
  lexer's regexes or the rule engine.
- A crash / unhandled exception reachable from untrusted input
  (`dxa lint`, `dxa parse`, `dxa lint-model`) — the fuzz suite
  (`tests/test_fuzz.py`) pins "no exception escapes besides ParseError",
  so a new crash from seeded soup is a reportable regression.
- Anything that would execute code from a model JSON file passed to
  `dxa lint-model` (the loader must stay data-only).

## What does not

- DAX quality findings themselves (wrong rule, missed pattern) — those
  are regular bugs, filed publicly.
- The docs site build.

## Reporting

Open a public issue in this repository unless you believe it is actively
exploitable in a real deployment; in that case contact the maintainer
privately first (GitHub profile contact). Reports on a static analyzer
of public DAX are rarely embargo-worthy.
