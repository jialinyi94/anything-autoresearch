# Code Templates

Read this file when you reach Phase 3 (Code Generation). It contains the templates
and requirements for each generated file.

For isolation architecture details (two-directory split, GitHub Secrets/CI),
read `references/hardened-isolation.md`.

## 3a. The Fixed Infrastructure (`prepare.py` equivalent)

This file lives in `agent-workspace/` and contains ONLY train and validation logic.
No test-related code, keys, or date ranges.

```python
import os
import time

# --- Constants (DO NOT MODIFY) ---
TIME_BUDGET = ...       # seconds per experiment
METRIC_NAME = "..."     # what we're optimizing
METRIC_DIRECTION = ...  # "minimize" or "maximize"

# --- Data Splits ---
# Train: used during experiment runs
# Validation: used to compute the metric the agent optimizes (agent sees this number)
# These are the ONLY splits in this file.

TRAIN_START = "..."
TRAIN_END = "..."
VAL_START = "..."
VAL_END = "..."

# --- Data / Input Preparation ---
# Download, preprocess, cache train + validation data ONLY
# Provide loader functions the mutable file can import

def _load_data():
    """Load or generate the full dataset (train + validation ONLY)."""
    ...

def _load_train_data():
    data = _load_data()
    return data[TRAIN_START:TRAIN_END]  # adapt to your data structure

def _load_val_data():
    data = _load_data()
    return data[VAL_START:VAL_END]

# --- Evaluation Harness (DO NOT MODIFY) ---
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

Requirements:
- All constants at the top, clearly labeled
- Data prep is idempotent (safe to run multiple times)
- Evaluation function is self-contained and deterministic
- `evaluate()` only accepts `"train"` or `"validation"` — NO `"test"` branch,
  no `_EXPECTED_KEY`, no key checking logic, no `_load_test_data()` function
- Data generation/loading covers ONLY the train+val period
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

This file lives in `human-eval/` (outside the agent's workspace). It is a standalone
script with its own test data loading — it does NOT call `evaluate(split="test")`.

Generate a **separate `evaluate_test.py`** that:
- Lives in `human-eval/`, NOT in agent-workspace
- Imports the agent's model/strategy from agent-workspace via `sys.path`
- Has its own `load_test_data()` function that loads test data from `human-eval/test_data/`
  (standard mode) or from files decoded from GitHub Secrets (hardened mode)
- Has its own `compute_metric()` function — same metric logic as prepare.py, kept in sync
- Prints a clear comparison: train metric vs validation metric vs test metric
- Includes an overfitting diagnostic: if val significantly beats test, warn the human
- Is meant to be run manually by the human, NEVER by the agent
- Must load model checkpoints / artifacts properly (not just a fresh random model)

Template:
```python
#!/usr/bin/env python3
"""Test set evaluation — run manually by the human ONLY.

This file lives OUTSIDE the agent's workspace.
Standard mode: run locally from human-eval/ directory.
Hardened mode: runs in GitHub Actions CI.
"""
import sys
import os

# --- Import the agent's strategy/model ---
AGENT_WORKSPACE = os.path.join(os.path.dirname(__file__), "..", "agent-workspace")
sys.path.insert(0, AGENT_WORKSPACE)

from run import model_or_fn  # adapt to your domain
import prepare

# --- Test data (agent has NO access to this) ---
TEST_START = "..."
TEST_END = "..."

def load_test_data():
    """Load test data from human-eval/test_data/.
    This function is self-contained — it does NOT call prepare.evaluate()."""
    test_data_path = os.path.join(os.path.dirname(__file__), "test_data")
    ...

def compute_metric(model_or_fn, data):
    """Same metric logic as prepare._compute_metric() — keep in sync!"""
    ...

if __name__ == "__main__":
    # Get train/val metrics via prepare.evaluate()
    train_metric = prepare.evaluate(model_or_fn, split="train")
    val_metric = prepare.evaluate(model_or_fn, split="validation")

    # Get test metric via our own function (NOT prepare.evaluate)
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

## 3c. The Mutable File (`train.py` equivalent)

This is the file the agent will modify. It should:
- Import constants and utilities from the fixed infrastructure
- Have clear sections with comments explaining what each part does
- Include sensible defaults that establish a working baseline
- Have hyperparameters / configuration at the top, clearly labeled as "edit these"
- Call the evaluation function and print results in the expected format
- Be self-contained enough that changes to one section don't cascade unpredictably

## 3d. The Agent Instructions (`program.md`)

This is the most critical file — it's the "brain" that drives autonomous research.
Generate it following this template, adapted to the user's specific problem.

Note: program.md should NOT mention the test set at all. The agent only knows about
train and validation splits.

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
- Access files outside this directory.

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
- **README.md** — project overview + deployment guide (see template below)
- **human-eval/README.md** — instructions for the human on how to run test evaluation

### README.md Template

Generate a README.md at the project root that includes:

```markdown
# <Project Name> — Autoresearch Framework

<Brief description of what this framework optimizes>

## Directory Structure

This framework uses a **two-directory architecture** to isolate the agent from test data:

```
<project>/
├── agent-workspace/    # Everything the AI agent can see and use
│   ├── program.md      # Agent's autonomous experiment loop instructions
│   ├── <fixed_file>    # Evaluation harness (read-only for agent)
│   ├── <mutable_file>  # The file the agent modifies each experiment
│   └── ...
└── human-eval/         # Test evaluation — agent has NO access
    ├── evaluate_test.py
    └── ...
```

## Deployment: Separating the Two Directories

For the isolation to be effective, the agent must not be able to access
`human-eval/`. How strictly you enforce this depends on your threat model:

### Option A: Same repo, different directories (convenient, basic isolation)

Keep both directories in the same repo. The agent is instructed to only work
within `agent-workspace/` and has no knowledge of `human-eval/`. This is
sufficient for most research use cases, but a determined agent could
traverse the filesystem to find `../human-eval/`.

### Option B: Separate repositories (recommended for important results)

Put `agent-workspace/` and `human-eval/` in **separate Git repos**.
The agent only has access to the agent-workspace repo. This prevents
filesystem traversal attacks entirely.

### Option C: Hardened mode with CI (recommended for high-stakes domains)

Store test data in **GitHub Secrets** and run test evaluation in
**GitHub Actions** on a disposable CI runner. The agent never has access
to test data, even indirectly. See `human-eval/README.md` for setup.

## Quick Start

1. Set up the agent workspace (give the agent access to `agent-workspace/` only)
2. Point the agent at `agent-workspace/program.md`
3. Let it run autonomously
4. When done, evaluate the best model using `human-eval/evaluate_test.py`
```

Adapt this template to the specific project. The key point: always include the
deployment options section so the human user understands how to physically
separate the directories for their threat model.
