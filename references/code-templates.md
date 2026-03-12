# Code Templates

Read this file when you reach Phase 3 (Code Generation). It contains the templates and requirements for each generated file.

> **Note**: The templates below are for **standard mode** (convention-based isolation with
> `AUTORESEARCH_TEST_KEY`). If the user chose **hardened mode** (100% isolation), read
> `references/hardened-isolation.md` instead — the architecture is fundamentally different
> (two-directory split, no test code in agent's workspace at all).

## 3a. The Fixed Infrastructure (`prepare.py` equivalent)

This file contains:

```python
import os

# --- Constants (DO NOT MODIFY) ---
TIME_BUDGET = ...       # seconds per experiment
METRIC_NAME = "..."     # what we're optimizing
METRIC_DIRECTION = ...  # "minimize" or "maximize"

# --- Data Splits ---
# Train: used during experiment runs
# Validation: used to compute the metric the agent optimizes (agent sees this number)
# Test: HELD OUT — agent never sees this. Human evaluates after all experiments.
#
# The test set is NOT loaded or accessible from this file.
# Use evaluate_test.py (separate script, run manually) for final evaluation.

_EXPECTED_KEY = "..."   # hash or passphrase for test set access

# --- Data / Input Preparation ---
# Download, preprocess, cache train + validation data
# Do NOT download or prepare test data here
# Provide loader functions the mutable file can import

# --- Evaluation Harness (DO NOT MODIFY) ---
def evaluate(model_or_fn, split="validation") -> float:
    """Evaluate on train or validation split.
    Test split requires AUTORESEARCH_TEST_KEY env var (human-only)."""
    if split == "test":
        key = os.environ.get("AUTORESEARCH_TEST_KEY")
        if not key or key != _EXPECTED_KEY:
            raise PermissionError(
                "Test evaluation requires AUTORESEARCH_TEST_KEY. "
                "This is for human-only post-experiment evaluation."
            )
        data = _load_test_data()
    elif split in ("train", "validation"):
        data = _load_train_data() if split == "train" else _load_val_data()
    else:
        raise ValueError(f"Unknown split: {split}")
    return _compute_metric(model_or_fn, data)
```

Requirements:
- All constants at the top, clearly labeled
- Data prep is idempotent (safe to run multiple times)
- Evaluation function is self-contained and deterministic
- **Programmatic access control**: `evaluate(split="test")` raises PermissionError
  unless `AUTORESEARCH_TEST_KEY` env var is set — even if the agent tries, it fails
- **Only train and validation data are freely accessible** — test data requires auth
- The mutable file should call `evaluate()` on BOTH train and validation, printing both
  metrics so the agent and human can monitor the train-val gap
- Prints the metric in a parseable format at the end (same as autoresearch):

```
---
train_<metric_name>:  <value>
<metric_name>:        <value>
train_val_gap:        <value>
wall_seconds:         <value>
<other_stats>:        <value>
```

## 3b. The evaluate_test.py (human-only)

Generate a **separate `evaluate_test.py`** that:
- Sets `AUTORESEARCH_TEST_KEY` programmatically or reads it from a dotenv
- Loads the held-out test set from its separate location
- Reuses the same metric computation logic (`evaluate(split="test")`)
- Prints a clear comparison: train metric vs validation metric vs test metric
- Includes an overfitting diagnostic: if val significantly beats test, warn the human
- Is meant to be run manually by the human, NEVER by the agent
- Must load model checkpoints / artifacts properly (not just a fresh random model)
- Add this file to `.gitignore` or keep it outside the agent's working directory

## 3c. The Mutable File (`train.py` equivalent)

This is the file the agent will modify. It should:
- Import constants and utilities from the fixed infrastructure
- Have clear sections with comments explaining what each part does
- Include sensible defaults that establish a working baseline
- Have hyperparameters / configuration at the top, clearly labeled as "edit these"
- Call the evaluation function and print results in the expected format
- Be self-contained enough that changes to one section don't cascade unpredictably

## 3d. The Agent Instructions (`program.md`)

This is the most critical file — it's the "brain" that drives autonomous research. Generate it following this template, adapted to the user's specific problem:

```markdown
# <Project Name> — Autonomous Research

This is an experiment to have an AI agent autonomously optimize <what>.

## Setup

To set up a new experiment, work with the user to:

1. **Agree on a run tag**: propose a tag based on today's date (e.g. `mar12`).
   The branch `autoresearch/<tag>` must not already exist.
2. **Create the branch**: `git checkout -b autoresearch/<tag>` from current main.
3. **Read the in-scope files**: The repo is small. Read these files for full context:
   - `README.md` — repository context.
   - `<fixed_file>` — fixed constants, data prep, evaluation. Do not modify.
   - `<mutable_file>` — the file you modify. <description of what's in it>.
4. **Verify setup**: <any prerequisite checks>
5. **Initialize results.tsv**: Create `results.tsv` with just the header row.
6. **Confirm and go**: Confirm setup looks good.

Once you get confirmation, kick off the experimentation.

## Experimentation

Each experiment runs for a **fixed time budget of <N> seconds** (wall clock).
You launch it simply as: `<run_command>`.

**What you CAN do:**
- Modify `<mutable_file>` — this is the only file you edit. <specifics>.

**What you CANNOT do:**
- Modify `<fixed_file>`. It is read-only.
- Install new packages or add dependencies.
- Modify the evaluation harness.
- Access, read, or evaluate against the test set. You only see the validation metric.
  The test set exists for the human to verify generalization after experiments are done.

**The goal is simple: get the <best> validation <metric_name>.**

**Simplicity criterion**: All else being equal, simpler is better. A small
improvement that adds ugly complexity is not worth it. Conversely, removing
something and getting equal or better results is a great outcome.

**The first run**: Always establish the baseline first by running as-is.

## Output Format

The script prints a summary like this:

<expected output format>

Extract the key metric: `grep "^<metric_name>:" run.log`

## Logging Results

Log to `results.tsv` (tab-separated). Columns:

```
commit	<metric_name>	train_<metric_name>	train_val_gap	status	description
```

- commit: git hash (short, 7 chars)
- <metric_name>: the validation value achieved (0 for crashes)
- train_<metric_name>: the train value (0 for crashes)
- train_val_gap: difference between train and validation metric
- status: `keep`, `discard`, or `crash`
- description: short text of what this experiment tried

## The Experiment Loop

The experiment runs on a dedicated branch.

LOOP FOREVER:

1. Look at the git state
2. Modify `<mutable_file>` with an experimental idea
3. git commit
4. Run: `<run_command> > run.log 2>&1`
5. Read results: `grep "^<metric_name>:\|^train_<metric_name>:\|^train_val_gap:" run.log`
6. If grep is empty → crash. `tail -n 50 run.log` for stack trace.
   Try to fix, or give up and move on.
7. Record in results.tsv (do NOT commit this file)
8. Decision logic (in order):
   a. If train_val_gap exceeds <threshold> → **discard** even if val improved
      (this means you're overfitting — the improvement won't generalize)
   b. If <metric_name> improved AND gap is acceptable → **keep** the commit
   c. If <metric_name> equal or worse → **discard**, `git reset --hard HEAD~1`

**Timeout**: If a run exceeds <2x time budget> seconds, kill it and treat as failure.

**Crashes**: Use judgment. Typo → fix and rerun. Fundamentally broken idea → skip.

**Overfitting awareness**: You are like a Kaggle competitor with unlimited public
leaderboard submissions. Every experiment is a "submission" that reveals the
validation score. The more you iterate, the higher the risk of implicitly
overfitting to validation noise. Prefer simple, principled changes over complex
hacks. If you notice the train-val gap growing, prioritize regularization or
simplification over pushing the validation score harder.

**NEVER STOP**: Once the loop begins, do NOT pause to ask the human. The human
might be asleep. You are autonomous. If you run out of ideas, think harder —
re-read the code, try combining previous near-misses, try more radical changes.
The loop runs until the human interrupts you, period.

## Research Directions

<domain-specific suggestions for what to try, ordered by promise>
```

## 3e. Supporting Files

- **pyproject.toml** (or equivalent) — pin dependencies
- **.gitignore** — ignore `run.log`, `results.tsv`, `__pycache__/`, any caches
- **README.md** — brief explanation of the project
