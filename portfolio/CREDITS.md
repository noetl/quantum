# Credits: external circuits in the NoETL portfolio

**Ranking only.** The portfolio pipeline (`playbooks/vqcc_portfolio.yaml`)
ships other authors' public circuits. All credit for those circuits goes to
their authors. A submission built from them counts for leaderboard ranking
only: it is **not** an original NoETL result and is **not** eligible for
prizes, which require the entrant's own original work. What NoETL adds is
the reproducible run: hash-pinned import, official verification at several
salts, selection, optional polish, packaging and provenance.

Every file is pinned by sha256 in `portfolio/candidates.json`. The run
refuses any file whose hash does not match.

| Task | Circuit | Authors (credit chain) | License |
| --- | --- | --- | --- |
| invsqrt | `acc7b9c8` | **maoxin123**, notebook "QCC 28.23 \| 4,022-Toffoli chemistry loaders" (2026-11-19 13:04 UTC run); 44-qubit generator line of **Syed Asad Ali** and **Ali Haydar Özdağ** | Apache-2.0 |
| dqi | `f6b555a6` | **manwithacat (James Barlow)**, "VQCC Hedge Wizardry Notebook" HW-31 (2026-11-19 20:25 UTC); edit of **goodpjw2008**'s `f56b04c7`, itself an edit of **Koushik Rudra**'s `4471b493`; decoder line of Syed Asad Ali, Ertuğrul Özer, Balram Srinivasan, GrantPrater, 暗黑AGI, SomeJoint (Agniv Banerjee) and others | Apache-2.0 |
| dfthcsos | `e6233e86` | weights `6ef06081` (first seen in **Manvender Singh**'s run, shipped by **Leo Tang**) on **maoxin123**'s 4,022-Toffoli loaders; lineage per maoxin123: Ertuğrul Özer (CC0 table line), prvsiyan, Syed Asad Ali, Lera (marculera), Ahmed Berat Özer, Atakan Aldemir, James Barlow (manwithacat), Busya PRIME, Heliosli | Apache-2.0 / CC0 |

The files were taken from **alex chilton**'s Apache-2.0 notebook
"28.24 LB | Which Circuits Survive Private Salt?" (version 22,
`submission.zip`), which assembles them and names each author. That notebook
is the source of the bytes, not their author.

The competition reference circuits are Google Quantum AI's sample
submission, used here as the fallback candidate for each task.
