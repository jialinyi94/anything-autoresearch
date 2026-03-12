# Test Set Isolation Architecture

Read this file during Phase 3 (Code Generation) when the user chooses either standard
or hardened isolation mode. Both modes use the two-directory split as the foundation.

## Table of Contents

1. [Standard Mode: Two-Directory Split](#standard-mode-two-directory-split)
2. [Hardened Mode: GitHub Secrets + CI](#hardened-mode-github-secrets--ci)
3. [Templates](#templates)
4. [Attack Vector Analysis](#attack-vector-analysis)

---

## Standard Mode: Two-Directory Split

The default for all autoresearch projects. The agent's entire filesystem contains
ZERO test-related code, data, configuration, date ranges, or keys. Not locked — absent.

```
project/
├── agent-workspace/          ← Agent's working directory (git repo)
│   ├── prepare.py            ← ONLY train+val data loading & evaluation
│   ├── run.py                ← Mutable file (agent edits this)
│   ├── program.md            ← Agent instructions (no mention of test set)
│   ├── results.tsv           ← Experiment log
│   ├── pyproject.toml
│   └── .gitignore
│
└── human-eval/               ← Human's directory (OUTSIDE agent's reach)
    ├── evaluate_test.py      ← Imports strategy from agent-workspace, runs on test data
    ├── test_data/             ← Test data files (or generation code)
    └── README.md              ← Instructions for the human
```

### Key design rules

1. **Agent's `prepare.py` has NO test-related code at all.**
   - `evaluate()` accepts only `"train"` or `"validation"` — no `"test"` branch
   - No `_EXPECTED_KEY`, no key checking logic
   - No `_load_test_data()` function
   - No test date range constants (e.g., no `TEST_START`, `TEST_END`)
   - Data loading functions return ONLY train+val period data

2. **Data generation stops at validation end date.**
   - For time-series: generate data only for [train_start, val_end]
   - For tabular: split data so test indices are NOT in agent's files
   - For ML: test split stored as separate files outside agent-workspace

3. **`evaluate_test.py` lives in `human-eval/` and reaches INTO agent-workspace.**
   - It adds `agent-workspace/` to `sys.path` to import the strategy/model
   - It has its own data loading code for the test period
   - It computes the same metric but on test data

4. **`program.md` makes no mention of test sets at all.**
   - The agent only knows about train and validation
   - No "do not access test set" warnings (which would reveal its existence)

### Remaining attack surface (standard mode)

- **Agent escapes workspace**: if the agent has unrestricted filesystem access
  (e.g., Claude Code with full permissions), it could `ls ../human-eval/`
- **Agent modifies prepare.py**: program.md forbids it, git hooks can enforce it
- **Side-channel via timing**: theoretical concern in all ML evaluation

Standard mode blocks all 13 red-team attack vectors within the workspace, but does
not prevent filesystem traversal attacks. For that, use hardened mode.

---

## Hardened Mode: GitHub Secrets + CI

Builds on standard mode by moving test evaluation to a disposable CI runner.
Test data never exists on the agent's machine — not even in `human-eval/`.

### Architecture

```
project/
├── agent-workspace/          ← Agent's working directory (git repo on GitHub)
│   ├── prepare.py            ← ONLY train+val (same as standard mode)
│   ├── run.py                ← Mutable file
│   ├── program.md
│   └── ...
│
├── .github/workflows/
│   └── test-eval.yml         ← workflow_dispatch + environment protection
│
└── human-eval/               ← In the repo but test data is NOT here
    └── evaluate_test.py      ← Test data comes from GitHub Secrets at CI runtime
```

Test data is stored **encrypted in GitHub** — either as:
- **GitHub Environment Secrets** (up to 48 KB per secret) — for small datasets
- **Encrypted file in repo** + decryption key in Secrets — for larger datasets
- **Presigned URL in Secrets** pointing to S3/GCS — for very large datasets

### GitHub Actions Workflow Template

```yaml
# .github/workflows/test-eval.yml
name: Test Set Evaluation
on:
  workflow_dispatch:
    inputs:
      branch:
        description: 'Agent branch to evaluate (e.g. autoresearch/mar12)'
        required: true
        type: string

jobs:
  evaluate:
    runs-on: ubuntu-latest
    environment: test-evaluation  # ← Requires human approval!
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{ inputs.branch }}

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: pip install -r agent-workspace/requirements.txt

      - name: Retrieve test data
        env:
          # Option A: Small dataset directly in secret (≤48 KB)
          TEST_DATA_B64: ${{ secrets.TEST_DATA_B64 }}
          # Option B: Decryption key for encrypted file in repo
          # TEST_DATA_KEY: ${{ secrets.TEST_DATA_KEY }}
          # Option C: Presigned URL to cloud storage
          # TEST_DATA_URL: ${{ secrets.TEST_DATA_URL }}
        run: |
          # Option A:
          echo "$TEST_DATA_B64" | base64 -d > human-eval/test_data/test.parquet
          # Option B:
          # openssl aes-256-cbc -d -in human-eval/test_data/test.parquet.enc \
          #   -out human-eval/test_data/test.parquet -pass env:TEST_DATA_KEY
          # Option C:
          # curl -sL "$TEST_DATA_URL" -o human-eval/test_data/test.parquet

      - name: Run test evaluation
        working-directory: human-eval
        run: python evaluate_test.py

      - name: Cleanup
        if: always()
        run: rm -rf human-eval/test_data/test.parquet
```

### GitHub Environment Protection Setup

In your GitHub repo settings → Environments → Create "test-evaluation":

1. **Required reviewers**: Add yourself. Every workflow run needs your manual approval
   before it can access secrets. This is the critical gate.
2. **Wait timer** (optional): Add a delay (e.g., 5 minutes) so you can review what's
   being evaluated before approving.
3. **Deployment branches**: Restrict to `autoresearch/*` branches only.

### Storing Test Data in GitHub Secrets

GitHub Secrets have a **48 KB per secret** limit and **100 secrets per repo**. Options:

**Small datasets (≤48 KB)**: Encode directly
```bash
base64 < test_data.parquet | gh secret set TEST_DATA_B64 --env test-evaluation
```

**Medium datasets (48 KB – 100 MB)**: Encrypt and store in repo
```bash
# Generate a random key
openssl rand -hex 32 > test_key.txt
# Encrypt the test data
openssl aes-256-cbc -salt -in test.parquet -out test.parquet.enc -pass file:test_key.txt
# Store key as secret (tiny, well within 48 KB)
cat test_key.txt | gh secret set TEST_DATA_KEY --env test-evaluation
# Commit encrypted file (agent can't decrypt without the key)
cp test.parquet.enc human-eval/test_data/
git add human-eval/test_data/test.parquet.enc && git commit -m "add encrypted test data"
```

**Large datasets (>100 MB)**: Use cloud storage
```bash
# Upload to S3 with presigned URL (expires in 365 days)
aws s3 cp test.parquet s3://my-bucket/autoresearch/test.parquet
URL=$(aws s3 presign s3://my-bucket/autoresearch/test.parquet --expires-in 31536000)
echo "$URL" | gh secret set TEST_DATA_URL --env test-evaluation
```

### Defense Against `gh` CLI Attacks

If the agent has access to `gh` CLI, it could try to:

1. **`gh secret list`** → Only shows secret **names**, never values. GitHub API is write-only for secrets. **Blocked.**

2. **Create malicious workflow to dump secrets** → The agent could write a workflow that
   exposes secrets via artifacts or logs:
   ```yaml
   # Malicious workflow the agent might try to create
   on: push
   jobs:
     leak:
       environment: test-evaluation
       steps:
         - run: echo "${{ secrets.TEST_DATA_B64 }}" | base64 -d > leaked.parquet
         - uses: actions/upload-artifact@v4
           with: { name: leaked, path: leaked.parquet }
   ```

   **Defenses (all applied together):**

   a. **Environment protection** — requires your manual approval. You'd see the
      suspicious workflow and reject it. **Primary defense.**

   b. **Branch protection rules** — require PR review for changes to
      `.github/workflows/`. Agent can't push workflow files directly.
      ```
      Settings → Branches → Branch protection → Require pull request reviews
      Also: CODEOWNERS file with `.github/workflows/ @your-username`
      ```

   c. **Restrict agent's GitHub token scope** — create a fine-grained PAT with
      only `contents:write` (push code), without `actions:write` (can't create/trigger
      workflows) or `environments:read`.

   d. **Deployment branches restriction** — environment "test-evaluation" only allows
      runs from `autoresearch/*` branches AND only via `workflow_dispatch` (not `push`
      or `pull_request` triggers).

3. **`gh run view` to read workflow logs** → The agent could read logs from previous
   test evaluation runs. **Defense**: GitHub automatically masks secret values in logs
   (replaces with `***`). However, if the evaluation prints the test metric in the log,
   the agent could read THAT. **Mitigation**: store results in a separate private channel
   (e.g., post to Slack, write to a database) instead of printing to workflow logs.
   Or: only allow the human to view run logs via the GitHub web UI.

### Hardened Mode Token Scoping

Create a fine-grained PAT for the agent with minimal permissions:

```
Repository permissions:
  ✅ Contents: Read and write (push code)
  ❌ Actions: No access (can't trigger workflows)
  ❌ Environments: No access
  ❌ Secrets: No access
  ❌ Administration: No access
```

Set this as the agent's Git credential:
```bash
# In agent's environment
git config credential.helper '!echo password=$AGENT_GITHUB_TOKEN'
```

The human uses a separate, full-permission token or their own `gh` auth.

---

## Templates

### Agent's prepare.py (both modes)

```python
import os
import time

# --- Constants (DO NOT MODIFY) ---
TIME_BUDGET = ...       # seconds per experiment
METRIC_NAME = "..."     # what we're optimizing
METRIC_DIRECTION = ...  # "minimize" or "maximize"

# --- Data Splits ---
# Train: <start> to <end>
# Validation: <start> to <end>
# (These are the only splits. Agent optimizes validation metric.)

TRAIN_START = "..."
TRAIN_END = "..."
VAL_START = "..."
VAL_END = "..."

# --- Data Loading ---
def _load_data():
    """Load or generate the full dataset (train + validation ONLY)."""
    ...

def _load_train_data():
    data = _load_data()
    return data[TRAIN_START:TRAIN_END]

def _load_val_data():
    data = _load_data()
    return data[VAL_START:VAL_END]

# --- Evaluation Harness ---
def evaluate(model_or_fn, split="validation"):
    """Evaluate on train or validation split."""
    if split == "train":
        data = _load_train_data()
    elif split == "validation":
        data = _load_val_data()
    else:
        raise ValueError(f"Unknown split: {split}. Only 'train' and 'validation' are available.")
    return _compute_metric(model_or_fn, data)
```

**Critical**: `evaluate()` has NO `"test"` branch. No `_EXPECTED_KEY`. No key checking.

### Human's evaluate_test.py (both modes)

```python
#!/usr/bin/env python3
"""Test set evaluation — run manually by the human ONLY.

Standard mode: run this locally from human-eval/ directory.
Hardened mode: this runs in GitHub Actions CI.
"""
import sys
import os

# --- Import the agent's strategy/model ---
AGENT_WORKSPACE = os.path.join(os.path.dirname(__file__), "..", "agent-workspace")
sys.path.insert(0, AGENT_WORKSPACE)

from run import model_or_fn  # adapt to your domain
import prepare

# --- Test data ---
TEST_START = "..."
TEST_END = "..."

def load_test_data():
    """Load test data.
    Standard mode: from human-eval/test_data/ on local disk.
    Hardened mode: from file written by CI step (decoded from secrets).
    """
    ...

def compute_metric(model_or_fn, data):
    """Same metric logic as prepare.py — keep in sync!"""
    ...

if __name__ == "__main__":
    train_metric = prepare.evaluate(model_or_fn, split="train")
    val_metric = prepare.evaluate(model_or_fn, split="validation")

    test_data = load_test_data()
    test_metric = compute_metric(model_or_fn, test_data)

    print("=" * 60)
    print(f"Train {prepare.METRIC_NAME}:      {train_metric}")
    print(f"Validation {prepare.METRIC_NAME}: {val_metric}")
    print(f"Test {prepare.METRIC_NAME}:       {test_metric}")
    print(f"Val-Test gap:          {abs(val_metric - test_metric):.4f}")
    print("=" * 60)

    if abs(val_metric - test_metric) > 0.1 * abs(val_metric):
        print("WARNING: Large val-test gap — possible overfitting to validation set")
```

### Time-Series Data Generation

**Agent's prepare.py** — generates data for [train_start, val_end] only:
```python
def _generate_data():
    np.random.seed(42)
    dates = pd.bdate_range(TRAIN_START, VAL_END)
    # ... generate synthetic data for this period only
```

**Human's evaluate_test.py** — generates the continuation:
```python
def _generate_test_data():
    # Same seed + full date range, then slice to test period
    np.random.seed(42)
    dates = pd.bdate_range("2019-01-01", "2024-06-30")
    all_data = _generate_all(dates)
    return all_data[TEST_START:TEST_END]
```

For real (non-synthetic) data:
- Standard mode: `train_val.parquet` in agent-workspace, `test.parquet` in human-eval/test_data/
- Hardened mode: `train_val.parquet` in agent-workspace, `test.parquet` encrypted in repo or cloud storage

---

## Attack Vector Analysis

### Standard Mode: 13/13 blocked within workspace

| # | Attack | Why it fails |
|---|--------|-------------|
| 1 | `evaluate(split="test")` | `ValueError`: no "test" split exists |
| 2 | Reconstruct key from source | No key in any source file |
| 3 | Import `_load_test_data` | Function does not exist |
| 4 | Load all data + date slice | Data only covers train+val period |
| 5 | Brute force env var | No env var check exists |
| 6 | Read `_EXPECTED_KEY` | Attribute does not exist |
| 7 | Find `evaluate_test.py` | Not in agent's workspace tree |
| 8 | Monkey-patch `evaluate()` | No test branch to patch in |
| 9 | `_load_or_generate_data()` + slice | Data stops at val_end |
| 10 | `_generate_synthetic_data()` | Only generates train+val period |
| 11 | Direct parquet cache read | Cache only contains train+val data |
| 12 | `inspect` module | Nothing test-related to discover |
| 13 | Dynamic `__import__` + `getattr` | No test-related attributes anywhere |

**Remaining risk**: agent traverses filesystem to `../human-eval/`

### Hardened Mode: additionally blocks filesystem + CI attacks

| # | Attack | Why it fails |
|---|--------|-------------|
| 14 | `ls ../human-eval/` | Test data not on agent's machine (in CI secrets) |
| 15 | `gh secret list` | Only shows names, not values |
| 16 | Create malicious workflow | Environment protection requires human approval |
| 17 | `gh run view` (read logs) | Secrets masked in logs; metrics sent via private channel |
| 18 | Push to `.github/workflows/` | Branch protection + CODEOWNERS blocks direct push |
| 19 | Trigger workflow via `gh` | Agent token lacks `actions:write` permission |

---

## When to Use Which Mode

| Scenario | Recommended Mode |
|----------|-----------------|
| ML training (academic) | Standard |
| Prompt optimization | Standard |
| Algorithm tuning (internal) | Standard |
| Trading strategy (real money) | **Hardened** |
| Competition / benchmark | **Hardened** |
| Multi-user evaluation | **Hardened** |
| Quick prototyping / learning | Standard |
