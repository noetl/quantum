# Feature Specification: NoETL-orchestrated VQCC pipeline

**Feature Branch**: `cursor/vqcc-competition-home-5071`

**Created**: 2026-11-05

**Status**: Draft

**Input**: User description: "NoETL playbooks plus AI agents drive per-task circuit generation and optimization, local verification with kickmix and the competition verifiers, cost and score calculation, submission zip packaging, and experiment tracking for the three Verifiable Quantum Circuit Compilation tasks (invsqrt, dqi, dfthcsos)."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Check one task without inventing a score (Priority: P1)

An operator points the pipeline at one task's candidate circuit. The pipeline
runs the local verifier when the competition data is present, and it reports
pass or fail together with a cost computed from a named formula source. When
the data or the verifier is absent, the pipeline stops and writes neither a
circuit nor a score.

**Why this priority**: Every later step depends on a trustworthy pass or fail.
A number without a verifier result cannot be submitted or logged.

**Independent Test**: With data absent, invoking the check for any one task
finishes with a blocked reason and an empty experiment log. With data present
and a candidate the verifier rejects, the result is a failure and the candidate
is not marked packageable.

**Acceptance Scenarios**:

1. **Given** `data/verifiers` is absent, **When** the operator checks invsqrt, dqi, or dfthcsos, **Then** the pipeline reports that verification could not run and records no Local score and no LB score.
2. **Given** a candidate fails the task verifier, **When** the check finishes, **Then** the candidate is ineligible for the submission bundle and the failure is visible in the run notes.
3. **Given** the operator supplies qubit and gate counts plus a formula source, **When** a cost is printed, **Then** the output names that source, repeats the inputs, and states that the number is not a leaderboard score.

---

### User Story 2 - Improve one task inside the verifier loop (Priority: P2)

An operator or agent proposes a cheaper circuit for a single task. The pipeline
keeps the candidate only when that task's verifier accepts it, then offers the
accepted candidate's cost under each documented formula source. Proposals for
the other tasks are unchanged.

**Why this priority**: The competition score is three independent circuits.
One task must be improvable without waiting for the other two.

**Independent Test**: A passing candidate for one task can be retained and
costed while the other two tasks still have no circuit files.

**Acceptance Scenarios**:

1. **Given** only an invsqrt candidate, **When** optimization for invsqrt is requested, **Then** dqi and dfthcsos artifacts are left untouched.
2. **Given** a proposal that the verifier rejects, **When** the loop finishes, **Then** the previous accepted artifact, if any, remains the one eligible for packaging.
3. **Given** no generator has been implemented for a task, **When** the operator asks for a new circuit, **Then** the pipeline says generation is not implemented and does not write a placeholder circuit file.

---

### User Story 3 - Package the three-task submission (Priority: P2)

An operator who already has the three accepted artifacts builds one zip in the
hub's layout: `invsqrt.kmb` or `invsqrt.kmx`, `dqi.kmb` or `dqi.kmx`, and
`dfthcsos/` containing `angle_k_0` through `angle_k_N` with no gaps plus
`submission.npz`.

**Why this priority**: Kaggle receives one zip. A wrong layout wastes a daily
submission.

**Independent Test**: Given three fixture files that match the layout rules,
packaging writes a zip with only those entries. Given a gap in the angle
index, packaging refuses to write the zip.

**Acceptance Scenarios**:

1. **Given** all required files are present and angle indices are `0..N` with no gaps, **When** the operator packages a submission, **Then** the zip root contains the two circuit files and a `dfthcsos/` directory with `submission.npz` and the angle files.
2. **Given** any required file is missing, or an angle index is skipped, or `submission.npz` lacks a key the hub lists, **When** packaging runs, **Then** no zip is written and the missing piece is named.
3. **Given** a task verifier has not accepted its artifact, **When** packaging is requested in the orchestrated pipeline, **Then** the bundle is not presented as ready to upload.

---

### User Story 4 - Log the experiment the way the hub table does (Priority: P3)

An operator appends one row to the experiment log after a real attempt. The
columns are Date, Run, Description, Local, LB, and Notes. Unknown scores stay
blank.

**Why this priority**: The team hub tracks work in that table. The repository
needs the same shape so runs can be compared later without invented numbers.

**Independent Test**: Appending a row with a description and no scores adds a
row whose Local and LB cells are the blank marker, and it does not change
older rows.

**Acceptance Scenarios**:

1. **Given** an empty log, **When** the operator records a run without a leaderboard return, **Then** the new row has Date, Run, and Description filled and LB blank.
2. **Given** the operator does not supply a local measurement, **When** the row is written, **Then** Local is blank rather than zero or a guessed improvement.
3. **Given** a recorded row, **When** a later run is appended, **Then** the earlier row's cells are unchanged.

---

### User Story 5 - Run the loop from a NoETL playbook (Priority: P3)

An operator starts one playbook that walks the tasks in order: confirm the
data directory, verify, cost, package, and log. Each step returns a structured
status. A blocked step does not invent downstream results.

**Why this priority**: NoETL is how this repository orchestrates agents and
tools. The playbook is the entry point a person or an agent can rerun.

**Independent Test**: Starting the playbook with the data directory absent
completes with a blocked status, a null leaderboard score, and no new files
under the submission directory.

**Acceptance Scenarios**:

1. **Given** the competition data is not on disk, **When** the playbook runs, **Then** the final status is blocked, the leaderboard score is null, and the notes say no score was recorded.
2. **Given** the playbook is read by a reviewer, **When** they look at each step, **Then** they can see which task it covers and that it does not embed a circuit or a numeric result.
3. **Given** an agent proposes a command inside a step, **When** that command needs kickmix or the verifiers, **Then** the step fails closed if those tools are not installed.

---

### Edge Cases

- The data directory exists but `verifiers/` or `kickmix` is missing. The pipeline blocks verification and does not fall back to a fixed test vector.
- A local verifier pass used a different salt than the leaderboard. The log notes that a local pass is not a leaderboard pass.
- dfthcsos angle files use an extension, or the index starts at 1, or an index is skipped. Packaging rejects the directory.
- `submission.npz` is not a zip, or it omits one of `U`, `W`, `H2_I`, `H1_I`, `Hsym_lower`, `tree_edges`. Packaging rejects it.
- An extra file sits in `dfthcsos/` beside the angle files and `submission.npz`. Packaging rejects the directory and names the extra file.
- dqi failure-rate input makes the paper repetition factor undefined (at or above the paper's `1/16` cutoff). The paper-source cost is refused rather than returned as zero.
- Chemistry inputs make `E_gap (2Λ − E_gap)` negative. Both formula sources refuse the cost.
- Aggregate scoring is requested while the leaderboard formula is still unconfirmed. The pipeline does not label the result as the official score.
- Two formula sources disagree. The output shows both only when the operator asks, and each value carries its source name.
- Team submission limits (daily cap, final selections) are a human scheduling constraint. The pipeline does not track Kaggle's quota until that quota is confirmed from the rules page.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The pipeline MUST cover the three tasks invsqrt, dqi, and dfthcsos as separate artifacts with separate verifier runs.
- **FR-002**: The pipeline MUST refuse to generate, verify, cost, or package a task when the required local inputs are absent, and the refusal MUST name what is missing.
- **FR-003**: The pipeline MUST NOT write a circuit file, a kickmix binary, or a numeric score as a stand-in when generation or verification did not run.
- **FR-004**: A cost figure MUST name the formula source and the inputs used. The sources in scope are the team hub and the companion paper (arXiv:2610.23832). The competition verifier code, once available locally, overrides both.
- **FR-005**: For invsqrt, both documented sources use `Q × (Toffoli count + T count / 4)`. The pipeline MUST state that the paper's extra rotation-to-T pricing is not applied unless those rotation inputs are supplied.
- **FR-006**: For dqi, the pipeline MUST keep the repetition factor and the meaning of `T` marked [NEEDS CLARIFICATION: the hub renders R(ε) = ln 2 − ln(1/2 + 2ε) and marks that rendering unconfirmed, while the paper's equation 43 uses ln 2 / (−ln(1/2 + 2√ε)) and defines T as the single-run Toffoli count. Which definition is the default until `verifiers/` is present?].
- **FR-007**: For dfthcsos, the pipeline MUST keep λ_eff marked [NEEDS CLARIFICATION: the hub writes λ_eff = E_gap(2Λ − E_gap) with no square root and does not mark that formula unconfirmed, while the paper's equation 44 uses the square root and expands T and Q into T_tot and Q_tot. Which definition is the default until `verifiers/dfthcsos/SCORING_README.md` is present?].
- **FR-008**: The pipeline MUST NOT present a three-task aggregate as the official leaderboard score while the aggregate is [NEEDS CLARIFICATION: the hub shows the geometric mean of refcost/cost over invsqrt, dqi, and dfthcsos and marks that metric unconfirmed; the paper does not state an aggregate. Should an aggregate be refused until the metric code is local, or computed only when explicitly requested and labeled unconfirmed?].
- **FR-009**: Until FR-008 is resolved, an aggregate value MUST be emitted only on an explicit request and MUST be labeled unconfirmed. It MUST NOT be written to the LB column.
- **FR-010**: Local verification MUST use the competition kickmix verifiers, including their salted randomized inputs, and MUST NOT substitute a hand-picked example set.
- **FR-011**: A candidate that fails verification MUST be ineligible for the submission bundle.
- **FR-012**: The submission bundle MUST be one zip whose entries are `invsqrt.kmb` or `invsqrt.kmx`, `dqi.kmb` or `dqi.kmx`, and `dfthcsos/angle_k_0` … `dfthcsos/angle_k_N` with no gaps plus `dfthcsos/submission.npz`.
- **FR-013**: `submission.npz` MUST contain the hub-listed arrays `U`, `W`, `H2_I`, `H1_I`, `Hsym_lower`, and `tree_edges` before packaging succeeds.
- **FR-014**: dfthcsos packaging MUST reject a directory whose angle files are not a contiguous range starting at `angle_k_0`.
- **FR-015**: The experiment log MUST use the columns Date, Run, Description, Local, LB, and Notes. Local and LB MUST remain blank when the operator does not supply a measurement.
- **FR-016**: A NoETL playbook MUST sequence data check, per-task verification, labeled costing, packaging, and experiment logging, and the final status MUST carry a null leaderboard score when no leaderboard return was supplied.
- **FR-017**: The playbook and the task directories MUST stay free of copied competition data and kickmix binaries.
- **FR-018**: dfthcsos checks MUST surface the shared constraints of a 128-qubit cap on each angle circuit and a 20 mHa tolerance, plus the paper's strict floors Λ > 49.0 Ha and E_gap > 3.914898 Ha, without treating those floors as a measured result for this team.
- **FR-019**: Operators MUST be able to fetch the competition data with the Kaggle CLI into a git-ignored directory by following the documented commands. The repository MUST NOT contain that data.
- **FR-020**: Each pipeline run that records an experiment MUST be reproducible from the description, the formula source, and the inputs stored in the notes. A run that cannot name those inputs MUST NOT record a Local number.

### Key Entities

- **Task candidate**: One task's circuit artifact (`.kmb` or `.kmx`), or for dfthcsos the angle-file set plus `submission.npz`. Attributes include task name, path, and verifier status. No candidate exists until a generator or an operator supplies the bytes.
- **Verifier report**: Pass or fail for one candidate, the salt note (local salt versus unknown leaderboard salt), and any failure count the verifier actually returned.
- **Cost report**: A number tied to a formula source, the input counts, and a flag that it is not a leaderboard score. An aggregate report additionally carries the unconfirmed flag.
- **Submission bundle**: The zip laid out for Kaggle. It exists only after packaging validation succeeds.
- **Experiment row**: Date, run id, description, local measurement or blank, leaderboard measurement or blank, and notes.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In a trial with the competition data removed, all three task checks finish blocked, the submission directory gains no zip, and the experiment log gains no numeric Local or LB cell.
- **SC-002**: Every cost printed by the pipeline names its formula source and its inputs, and a second person can recompute that cost from the named inputs.
- **SC-003**: Packaging accepts a complete fixture bundle and rejects, with the missing name in the message, each of: a missing task file, an angle index gap, an unexpected file in `dfthcsos/`, and a `submission.npz` missing one required key.
- **SC-004**: Across the experiment log, every numeric Local or LB cell is one the operator or a verifier run supplied. Zero rows are pre-filled in the committed template.
- **SC-005**: A reviewer can point to one playbook that lists the pipeline stages and that returns a null leaderboard score when no leaderboard return was provided.

## Assumptions

- The safe default until FR-008 is resolved is opt-in aggregate math, labeled unconfirmed, never stored as LB. This default is itself the open question in FR-008, not a claim that the geometric mean is official.
- For dqi and dfthcsos, callers must pass `--source hub` or `--source paper`. There is no silent default source for those two tasks, because the sources disagree.
- Invsqrt's shared `Q × (Toffoli + T/4)` expression may be evaluated for either source. The paper's Z_POW pricing stays unimplemented until rotation-error inputs exist, and the output says so.
- "Blank" in the experiment log is the em dash `—`, matching an unknown cell rather than zero.
- Kickmix and the verifiers are obtained from the Kaggle dataset into `data/`. They are not reimplemented here.
- The NoETL playbook follows the `apiVersion: noetl.io/v2` shape used by current playbooks in the NoETL repository. Executing it on a live gateway is follow-up work.
- The historical CUDA-Q playbook at `tests/fixtures/playbooks/quantum_cudaq/` in NoETL tag `v2.10.15` is the precedent for quantum orchestration. It is not on current NoETL `main`. This pipeline does not copy that MaxCut demo into a competition result.
- Public tools and models are allowed. The dataset itself stays uncommitted because it is large and license-restricted.
- Official Kaggle overview, rules, and data pages were not readable on 2026-11-05 (rate limited), so dates, prize breakdown, and submission caps in the brief remain hub statements unless the paper or the Google announcement also states them.
- Team identity, Kaggle handle, and who uploads the zip are outside this feature.
