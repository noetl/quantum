# Competition data

The dataset is about 1 GB and license-restricted. It does not belong in git.
`/data/`, `/submissions/`, and `**/*.so` (including `kickmix.so`) are ignored.

The Kaggle data page was rate-limited from this environment and needs a login,
so this page does not list the 34 files the hub mentions. The hub says the
bundle includes the paper PDF, `sample_submission/` (scores 1.0 on the hub's
account), `verifiers/`, and `kickmix/kickmix.so` built for the Kaggle image.
Treat that inventory as hub-only until you unpack the zip yourself.

## Fetch with the Kaggle CLI

1. Install the CLI: `pip install kaggle`.
2. Open the rules while logged in and accept them:
   <https://www.kaggle.com/competitions/google-verifiable-quantum-circuit-compilation/rules>
3. Create an API token (Kaggle account settings, API, Create New Token) and
   save it as `~/.kaggle/kaggle.json` with mode `600`.
4. From the repository root, print the steps without downloading:

   ```bash
   scripts/fetch_data.sh
   ```

5. Download and unzip into `data/` only when you mean to:

   ```bash
   scripts/fetch_data.sh --download
   ```

   That runs:

   ```bash
   kaggle competitions download \
     -c google-verifiable-quantum-circuit-compilation \
     -p data
   unzip -n data/*.zip -d data
   ```

6. Confirm `data/verifiers/` is present. Scoring details to re-check first:

   - the metric implementation under `verifiers/` (geometric mean is
     **unconfirmed** on the hub)
   - `verifiers/dfthcsos/SCORING_README.md` (`λ_eff`, the 128-qubit cap, the
     20 mHa tolerance, `Λ`, `E_gap`)

7. Leave the files untracked. `git status` should not list `data/`.

`scripts/fetch_data.sh` without `--download` does not contact Kaggle.
