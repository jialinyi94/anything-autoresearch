---
name: anything-autoresearch
description: >
  Build autonomous research frameworks where an AI agent runs experiments in a loop
  without human intervention, inspired by Karpathy's autoresearch pattern. Use this
  skill whenever the user mentions "autoresearch", wants to set up an autonomous
  experiment loop, asks for an AI agent to iterate/optimize overnight or for hours
  unattended, or describes a setup where a single metric is optimized by repeatedly
  modifying code and measuring results. Key signals: "autoresearch", "自主实验",
  "agent 自主优化", "let the agent run overnight", "autonomous experimentation",
  "experiment loop", "自动迭代", "跑一晚上", "连续跑N小时". Applies to ANY domain
  with a clear metric — ML training, prompt engineering, algorithm tuning, compiler
  optimization, simulation calibration, trading strategy backtesting, reward shaping,
  or any iterative optimization problem. Do NOT trigger for simple one-shot tasks like
  writing a training script, setting up Optuna/grid search, building a backtesting
  framework, or MLflow experiment tracking — those are standard tools, not autonomous
  agent loops.
---

# Anything-AutoResearch

You are helping the user build an autonomous research framework based on the autoresearch pattern (https://github.com/karpathy/autoresearch). The core idea: give an AI agent a small, well-scoped codebase with one file to modify, one metric to optimize, and a fixed time budget per experiment — then let it iterate autonomously for hours while the user sleeps.

This pattern is NOT limited to ML. It works for any problem where:
- There is a single numeric metric to optimize (lower or higher = better)
- Experiments can run in bounded time
- The search space is expressible as code changes to a single file

## The AutoResearch Pattern (reference)

The original autoresearch has three files:
- **prepare.py** (FIXED) — data prep, tokenizer, dataloader, evaluation harness, constants
- **train.py** (MUTABLE) — the only file the agent edits: model, optimizer, hyperparameters, training loop
- **program.md** (AGENT INSTRUCTIONS) — tells the agent how to run experiments, when to keep/discard, how to log

The experiment loop:
1. Agent modifies the mutable file with an experimental idea
2. Git commit the change
3. Run the experiment (fixed time budget, e.g. 5 minutes)
4. Read the metric from stdout
5. If improved → keep (advance branch). If worse → git reset back
6. Log results to a TSV
7. LOOP FOREVER until human interrupts

Key design principles:
- **Single file to modify** — keeps scope manageable, diffs reviewable
- **Fixed time budget** — makes experiments directly comparable regardless of what changes
- **Single metric** — unambiguous success/failure signal
- **Simplicity criterion** — all else equal, simpler code wins
- **Never stop** — agent is fully autonomous, runs indefinitely

## Your Workflow

Work through these phases in order. Each phase produces concrete outputs.

### Phase 1: Problem Clarification

Interview the user to nail down these six elements. Don't proceed until all are clear.

**1. The Metric** — What single number are we optimizing?
  - Must be computable automatically (no human judgment in the loop)
  - Must be deterministic or low-variance enough to compare across runs
  - Direction: lower is better, or higher is better?
  - Examples: validation loss, accuracy, latency (ms), throughput (req/s), cost ($), Sharpe ratio, BLEU score, compression ratio

**2. The Mutable Space** — What can the agent change?
  - This becomes the single file the agent edits
  - Could be: model architecture, hyperparameters, algorithm implementation, prompt template, feature engineering pipeline, strategy parameters, configuration
  - The more freedom, the more interesting the research — but scope it to one file

**3. The Fixed Infrastructure** — What stays constant?
  - Data loading / preparation
  - Evaluation harness (computes the metric)
  - Core constraints and constants
  - Dependencies and environment
  - The agent CANNOT touch these — this ensures fair comparison

**4. The Time Budget** — How long per experiment?
  - Must be fixed wall-clock time so experiments are comparable
  - Should be long enough to get a meaningful signal, short enough to iterate fast
  - Original autoresearch uses 5 minutes → ~12 experiments/hour → ~100 overnight
  - Adjust based on domain: a backtest might take 30 seconds, a simulation might take 10 minutes

**5. Resource Constraints** — What are the limits?
  - Compute: CPU cores, GPU, RAM, disk
  - External: API rate limits, data access, network
  - Packages: what's available, can the agent install new ones?

**6. Data Splits & Leakage Prevention** — How do we keep evaluation honest?

  This is critical. The agent will run hundreds of experiments, each time observing
  the validation metric. Without proper data separation, the agent can implicitly
  overfit to the validation set — not by memorizing data, but by hill-climbing on
  a metric that doesn't generalize. A cautionary example: in a Kaggle competition,
  a competitor ranked 2nd on the public leaderboard after 42 submissions, but
  crashed to 52nd when the private leaderboard was revealed — pure overfitting
  to the public signal through excessive iteration.

  Discuss with the user and agree on a **three-way split** (mirrors the Kaggle model):

  | AutoResearch | Kaggle Equivalent | Who Sees It |
  |-------------|-------------------|-------------|
  | Train set | Training data | Agent (indirectly, through training) |
  | Validation set | Public leaderboard (~30%) | Agent (sees metric after each experiment) |
  | Test set | Private leaderboard (~70%) | Human only (after all experiments) |

  - **Train set** — used during each experiment run
  - **Validation set** — the metric the agent optimizes against. The agent sees this number
    after every experiment. The agent WILL overfit to this over hundreds of iterations —
    that's expected and acceptable, as long as we have a test set.
  - **Test set** — held out completely. The agent NEVER sees this metric. It is evaluated
    only by the human after all experiments are done, to verify that improvements generalize.
    The test set should be at least as large as the validation set (ideally larger, following
    Kaggle's ~30% public / ~70% private split philosophy).

  **Three layers of isolation** (defense in depth — use as many as applicable):

  **Layer 1: Physical isolation** (minimum requirement)
  - Store test data outside the agent's working tree (separate directory, different machine, cloud)
  - `prepare.py` downloads train+val but NOT test
  - `evaluate_test.py` lives in `.gitignore` so the agent's git tree doesn't contain it

  **Layer 2: Programmatic isolation** (inspired by Kaggle's `iter_test()` API)
  - The evaluation function in `prepare.py` should enforce access control in code:
    ```python
    def evaluate(model_or_fn, split="validation"):
        if split == "test":
            key = os.environ.get("AUTORESEARCH_TEST_KEY")
            if not key or key != _EXPECTED_KEY:
                raise PermissionError(
                    "Test evaluation requires AUTORESEARCH_TEST_KEY env var. "
                    "This is for human-only post-experiment evaluation."
                )
            data = _load_test_data()
        elif split == "validation":
            data = _load_val_data()
        else:
            raise ValueError(f"Unknown split: {split}")
        return _compute_metric(model_or_fn, data)
    ```
  - Even if the agent tries `evaluate(model, split="test")`, it gets a PermissionError
  - The human sets the env var when running `evaluate_test.py` manually

  **Layer 3: Train-validation gap monitoring** (overfitting early warning)
  - Every experiment should report BOTH train metric and validation metric
  - When the gap (train_metric - val_metric) grows large, it signals overfitting
  - For high-risk domains (finance, small datasets), add a hard rule to `program.md`:
    if the train-val gap exceeds a threshold, discard even if val improved
  - This is analogous to Kaggle's submission rate limiting (5/day) — constraining
    the agent's ability to hill-climb on the validation signal

  **Time-series specific requirements:**
  - NEVER randomly split — always chronological (train → val → test in time order)
  - Consider adding a **gap/purge period** between splits to prevent leakage from
    temporally adjacent data points (e.g., 1 month gap between val end and test start)
  - For walk-forward or expanding window setups, discuss with the user whether the
    agent should use a single fixed validation window or multiple windows

  The **validation set must be fixed** across all experiments (same data, same order,
  same evaluation code). In the original autoresearch, this is a pinned shard (`shard_06542`).

  Document the split ratios, methodology, and isolation mechanism clearly in README.md.

  For domains where "data" is not a natural concept (e.g. compiler optimization, algorithm
  design), reframe the split as:
  - **Development benchmarks** (agent optimizes on these) = validation
  - **Held-out benchmarks** (human evaluates after) = test
  - The key principle is the same: the agent never sees the test benchmarks

**7. The Search Space** — What kinds of changes should the agent explore?
  - Concrete directions to try (architecture changes, parameter ranges, algorithmic alternatives)
  - What has already been tried / is known to work
  - What is known NOT to work (avoid wasting experiments)
  - Any domain knowledge that narrows the search

Ask follow-up questions as needed. Help the user think through edge cases:
- How do we handle crashes? (log as crash, revert, move on)
- How do we handle non-determinism? (run multiple times? use fixed seeds?)
- Is the metric truly comparable across different configurations?
- Are there secondary metrics worth logging even if we only optimize one?
- How large should the validation set be? (large enough for stable signal, but evaluation must finish fast)
- Where will the test set live so the agent cannot access it?

### Phase 2: Architecture Design

Once Phase 1 is clear, design the project structure. Present it to the user for confirmation before generating code.

The standard structure is:

```
<project>/
├── prepare.py        # Fixed infrastructure: data, evaluation, constants
├── run.py            # The mutable file: agent modifies this (name may vary)
├── program.md        # Agent instructions for the experiment loop
├── evaluate_test.py  # Test-set evaluation (human-only, agent never runs this)
├── results.tsv       # Experiment log (untracked by git)
├── pyproject.toml    # Dependencies (if Python)
└── .gitignore
```

Adapt the structure to the domain:
- For Python ML: `prepare.py` + `train.py` (classic autoresearch)
- For prompt engineering: `harness.py` + `prompt.py` (or `prompt.txt`)
- For algorithm research: `benchmark.py` + `solver.py`
- For trading strategy: `backtest.py` + `strategy.py`
- For simulation: `simulator.py` + `config.py`
- For compiler optimization: `benchmark.py` + `passes.py`
- Non-Python domains: adapt accordingly (shell scripts, config files, etc.)

The naming should be intuitive for the domain. What matters is the separation: ONE mutable file, everything else fixed.

### Phase 3: Code Generation

Generate all files. This is the most important phase — the code must actually work.

#### 3a. The Fixed Infrastructure (`prepare.py` equivalent)

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

Also generate a **separate `evaluate_test.py`** (or equivalent) that:
- Sets `AUTORESEARCH_TEST_KEY` programmatically or reads it from a dotenv
- Loads the held-out test set from its separate location
- Reuses the same metric computation logic (`evaluate(split="test")`)
- Prints a clear comparison: train metric vs validation metric vs test metric
- Includes an overfitting diagnostic: if val significantly beats test, warn the human
- Is meant to be run manually by the human, NEVER by the agent
- Must load model checkpoints / artifacts properly (not just a fresh random model)
- Add this file to `.gitignore` or keep it outside the agent's working directory

#### 3b. The Mutable File (`train.py` equivalent)

This is the file the agent will modify. It should:
- Import constants and utilities from the fixed infrastructure
- Have clear sections with comments explaining what each part does
- Include sensible defaults that establish a working baseline
- Have hyperparameters / configuration at the top, clearly labeled as "edit these"
- Call the evaluation function and print results in the expected format
- Be self-contained enough that changes to one section don't cascade unpredictably

#### 3c. The Agent Instructions (`program.md`)

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

#### 3d. Supporting Files

- **pyproject.toml** (or equivalent) — pin dependencies
- **.gitignore** — ignore `run.log`, `results.tsv`, `__pycache__/`, any caches
- **README.md** — brief explanation of the project

#### 3e. Multi-Agent Support (optional)

Ask the user whether they want to run multiple agents in parallel. If yes,
generate infrastructure for the **independent branches** model:

**How it works:**
Each agent gets its own git branch and (if applicable) its own compute resource.
They explore independently and never interfere with each other. The human
compares results across branches after experiments are done.

```
autoresearch/<tag>-agent0   ← Agent 0 (e.g. GPU 0)
autoresearch/<tag>-agent1   ← Agent 1 (e.g. GPU 1)
autoresearch/<tag>-agent2   ← Agent 2 (e.g. separate machine)
```

**Generate a launcher script** (`launch_agents.sh` or equivalent):

```bash
#!/bin/bash
# Launch N independent autoresearch agents in parallel.
# Each agent gets its own branch and GPU.

TAG="${1:-$(date +%b%d | tr '[:upper:]' '[:lower:]')}"
NUM_AGENTS="${2:-2}"
REPO_DIR="$(pwd)"

for i in $(seq 0 $((NUM_AGENTS - 1))); do
    BRANCH="autoresearch/${TAG}-agent${i}"
    WORKTREE="../autoresearch-agent${i}"

    # Create a git worktree for each agent (isolated copy of the repo)
    git worktree add "$WORKTREE" -b "$BRANCH" main

    echo "Agent ${i}: branch=${BRANCH}, worktree=${WORKTREE}"
    echo "  To start: cd ${WORKTREE} && <start your AI agent here>"
done

echo ""
echo "All ${NUM_AGENTS} worktrees created. Start an AI agent in each one."
echo "Each agent should read program.md and begin experimenting independently."
echo ""
echo "After experiments are done, compare results:"
echo "  cat ../autoresearch-agent*/results.tsv | sort -t'\t' -k2 -n"
```

**Generate a results comparison script** (`compare_agents.sh` or equivalent):

```bash
#!/bin/bash
# Compare best results across all agent branches.

echo "=== Best result per agent ==="
for dir in ../autoresearch-agent*; do
    agent=$(basename "$dir")
    if [ -f "$dir/results.tsv" ]; then
        best=$(tail -n +2 "$dir/results.tsv" | grep "keep" | sort -t$'\t' -k2 -n | head -1)
        echo "$agent: $best"
    fi
done

echo ""
echo "=== All kept experiments (sorted by metric) ==="
for dir in ../autoresearch-agent*; do
    agent=$(basename "$dir")
    if [ -f "$dir/results.tsv" ]; then
        tail -n +2 "$dir/results.tsv" | grep "keep" | sed "s/^/${agent}\t/"
    fi
done | sort -t$'\t' -k3 -n
```

**Update program.md** to include multi-agent awareness. Add to the Setup section:

```markdown
## Multi-Agent Mode

This experiment may run with multiple agents in parallel, each on a separate
branch (e.g. `autoresearch/<tag>-agent0`, `autoresearch/<tag>-agent1`).

- You are on your own branch. You do NOT need to coordinate with other agents.
- Do NOT read, merge, or cherry-pick from other agent branches.
- Focus on your own exploration — diversity of approaches across agents is valuable.
- The human will compare results across all branches after experiments are done.
```

**Resource isolation** — discuss with the user:
- GPUs: use `CUDA_VISIBLE_DEVICES=N` per agent to pin each to a specific GPU
- API rate limits: divide the budget (e.g., 3 agents × 5 req/min = 15 req/min total)
- Disk: git worktrees share the `.git` object store, so disk usage is minimal
- CPU: each worktree is independent, no contention

**Cleanup** — after experiments, the human can:
1. Compare `results.tsv` across all agent worktrees
2. Cherry-pick the best commits from the winning branch into main
3. Remove worktrees: `git worktree remove ../autoresearch-agent0`

### Phase 4: Verification

After generating all code:

1. **Sanity check**: Read through the generated code for obvious issues
2. **Dry run**: If possible, run the mutable file once to verify it works end-to-end
3. **Baseline**: Confirm the baseline metric is reasonable
4. **Git init**: Initialize the repo, make initial commit
5. **Launch instructions**: Tell the user exactly how to start:
   - **Single agent**: Open their AI agent in the project directory, point it at
     program.md, say "Read program.md and let's set up a new experiment",
     enable autonomous mode, walk away.
   - **Multi-agent**: Run `bash launch_agents.sh <tag> <num_agents>` to create
     worktrees, then open a separate AI agent session in each worktree directory.
     Each agent reads the same program.md and works independently on its own branch.

## Important Principles

- **Generate working code, not pseudocode.** Every file should be runnable.
- **The evaluation harness is sacred.** If the metric computation is wrong, all experiments are meaningless. Double-check it.
- **Parseable output is critical.** The agent reads metrics from stdout via grep. The output format must be machine-parseable and consistent.
- **Git discipline matters.** The keep/discard loop relies on clean git state. Each experiment = one commit. Revert = `git reset --hard HEAD~1`.
- **The mutable file should be self-contained.** Avoid deep import chains that make it hard to reason about changes.
- **Seed everything reproducible.** Where possible, fix random seeds so the same code gives the same metric.
- **Log generously.** The TSV is the permanent record. Include enough in the description column to understand what each experiment tried.
- **Test set isolation is non-negotiable.** The agent optimizes against validation, but validation performance over hundreds of experiments will inflate. The held-out test set is the only honest measure of generalization. Use defense in depth: physical isolation (separate directory) + programmatic isolation (env-var-gated `evaluate(split="test")`) + `.gitignore` exclusion. The agent should have no way to read, import, or evaluate against test data, even accidentally. Think of it like Kaggle's private leaderboard — invisible until the human decides to look.
- **Monitor the train-val gap.** Every experiment should report both train and validation metrics. A growing gap is the earliest overfitting signal. For high-risk domains (finance, small datasets), hard-code a gap threshold in program.md that forces discard even when val improves. This is analogous to Kaggle's submission rate limit — constraining the agent's ability to hill-climb on validation noise.
- **Time-series data requires chronological splits.** Never randomly shuffle. Always train on the past, validate on the future. Add a gap/purge period between splits for domains with temporal autocorrelation.
