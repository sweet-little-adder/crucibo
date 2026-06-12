# Process

How we extend crucibo without scope creep.

**Coming back after a break?** Read **[HANDOFF.md](HANDOFF.md)** first—commands, Polygon deferral, next coding targets.

## Branches / commits

- **Small commits** tied to roadmap checkboxes where possible.
- Commit messages describe *why* (invariants, bug class), not only *what*.

## Secrets

- **Never** commit API keys, vendor tokens, or paths to proprietary data.
- Use `.env` (gitignored) or macOS Keychain wrappers later; document variable **names** in `DATA.md` only.

## Experiments

- Put ad-hoc work under `experiments/YYYY-MM-DD_short-name/`.
- Each experiment gets a one-paragraph `README.md` listing data slice + command used.

## When to write a decision

If the choice costs >2 hours to reverse or affects public interfaces, add a row to `DECISIONS.md`.

## Definition of done (for any PR to yourself)

1. Repro command documented in commit or experiment README.
2. No new lookahead vectors (peer review with future-you).
3. Tests or invariant checks updated if sim semantics changed.
