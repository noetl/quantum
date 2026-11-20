# Current Problems / Open Questions

**Last refreshed:** 2026-11-20 (UTC). Canonical numbers: [`STATE.md`](https://github.com/noetl/quantum/blob/main/STATE.md) and [Status](Status).

## 1. Our optimizer is a tidy pass, worth about 1×

- The NoETL rewrite pass (`playbooks/vqcc_optimize.yaml`) makes provably exact local rewrites of the reference circuits. It scores ≈ 1.0013: invsqrt 1.0039× (Kaggle), dqi and dfthcsos 1.0×.
- The reference circuits are already well compiled, so local rewriting finds almost nothing. As a polish on top of strong circuits, it is worth at most about +0.01–0.1%.
- **Withdrawn:** the earlier claim that a GF(2^12) multiplier redesign is "the real remaining headroom". It held only relative to the reference decoder. Public circuits have already replaced the whole decoder design.

## 2. Real gains are per-task algorithm redesigns

| Task | What the public field changed | Public best ratio |
| --- | --- | --- |
| invsqrt | new fixed-point arithmetic, 260 → 44 qubits | ≈ 27.9× |
| dqi | a different decoder family, 5.7M → 366k Toffolis and 1,893 → 890 qubits (Q is squared in the cost) | ≈ 70.8× |
| dfthcsos | refitted factorization and new lookup loaders | ≈ 11.4× |

These are other teams' measurements, re-run locally by the portfolio pipeline. Original work at this level is weeks to months per task, with uncertain results. Beating the 31.74 leader needs about 1.42× better combined than the public best.

## 3. The wrapper path: ranking only

- `playbooks/vqcc_portfolio.yaml` (PR #34) imports hash-pinned public circuits by other authors, verifies every candidate at several salts, keeps the cheapest that passes everywhere, optionally polishes it, and packages the zip. That reaches the public plateau (≈ 28.24, shared by about 100 teams).
- **It counts for leaderboard ranking only. It is not an original result and is not prize-eligible.**
- **Open:** whether to submit it. That is the owner's decision.

## 4. Private-board risk

- The private board re-runs the verifiers with a hidden salt. One task failing there scores the whole submission 0. Multi-salt verification is the guard; it is evidence, not a proof.

## 5. Spec clarifications still open

- FR-006 (dqi `R(ε)`), FR-007 (dfthcsos `λ_eff`) and FR-008 (leaderboard aggregate) stay `[NEEDS CLARIFICATION]`. See [Tutorial 9: Open questions](Tutorial-09-Open-Questions).
