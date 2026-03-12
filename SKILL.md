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

## The AutoResearch Pattern

The original autoresearch has three files:
- **prepare.py** (FIXED) — data prep, evaluation harness, constants
- **train.py** (MUTABLE) — the only file the agent edits
- **program.md** (AGENT INSTRUCTIONS) — experiment loop, keep/discard rules, logging

The experiment loop: modify mutable file → git commit → run (fixed time budget) → read metric → if improved keep, else `git reset --hard HEAD~1` → log to TSV → LOOP FOREVER.

Key principles: single file to modify, fixed time budget, single metric, simplicity criterion, never stop.

## Your Workflow

Work through these phases in order. Each phase produces concrete outputs.

### Phase 1: Problem Clarification

Interview the user to nail down these seven elements. Don't proceed until all are clear.

**1. The Metric** — What single number are we optimizing?
  - Must be computable automatically, deterministic or low-variance
  - Direction: lower is better, or higher is better?
  - Examples: validation loss, accuracy, latency, Sharpe ratio, BLEU score

**2. The Mutable Space** — What can the agent change?
  - This becomes the single file the agent edits
  - Could be: model architecture, hyperparameters, prompt template, strategy parameters, configuration

**3. The Fixed Infrastructure** — What stays constant?
  - Data loading, evaluation harness, constants, dependencies
  - The agent CANNOT touch these — ensures fair comparison

**4. The Time Budget** — How long per experiment?
  - Fixed wall-clock time so experiments are comparable
  - Original autoresearch: 5 minutes → ~12 experiments/hour → ~100 overnight
  - Adjust by domain: backtest ~30s, simulation ~10min

**5. Resource Constraints** — Compute, API limits, packages?

**6. Data Splits & Leakage Prevention** — Critical for honest evaluation.

  The agent will run hundreds of experiments, each observing the validation metric.
  Without proper separation, it implicitly overfits (Kaggle cautionary tale: rank 2→52
  after private leaderboard reveal due to 42 submissions of hill-climbing).

  Agree on a **three-way split** (mirrors Kaggle public/private leaderboard):

  | AutoResearch | Kaggle Equivalent | Who Sees It |
  |-------------|-------------------|-------------|
  | Train set | Training data | Agent (indirectly) |
  | Validation set | Public LB (~30%) | Agent (sees metric) |
  | Test set | Private LB (~70%) | Human only |

  **Three layers of isolation** (defense in depth):

  **Layer 1: Physical** — test data outside agent's working tree; `evaluate_test.py` in `.gitignore`

  **Layer 2: Programmatic** — `evaluate(split="test")` requires `AUTORESEARCH_TEST_KEY` env var, else raises `PermissionError`. Even if the agent tries, it fails.

  **Layer 3: Train-val gap monitoring** — report both train and val metrics; discard if gap exceeds threshold even when val improves. Analogous to Kaggle's submission rate limiting.

  **Time-series specific**: NEVER randomly split — always chronological. Add gap/purge period between splits. Validation set must be fixed across all experiments.

  For domains without natural "data" (compiler optimization, algorithm design): reframe as development benchmarks (validation) vs held-out benchmarks (test).

**7. The Search Space** — What to explore, what's known to work/fail, domain knowledge?

Ask follow-up questions: crash handling, non-determinism, metric comparability, secondary metrics, validation set size, test set storage location.

### Phase 2: Architecture Design

Present the project structure for confirmation:

```
<project>/
├── prepare.py        # Fixed infrastructure: data, evaluation, constants
├── run.py            # The mutable file (name varies by domain)
├── program.md        # Agent instructions for the experiment loop
├── evaluate_test.py  # Test-set evaluation (human-only, in .gitignore)
├── results.tsv       # Experiment log (untracked)
├── pyproject.toml    # Dependencies
└── .gitignore
```

Domain naming conventions:
- ML: `prepare.py` + `train.py`
- Prompt engineering: `harness.py` + `prompt.py`
- Trading strategy: `backtest.py` + `strategy.py`
- Algorithm: `benchmark.py` + `solver.py`
- Simulation: `simulator.py` + `config.py`

### Phase 3: Code Generation

Generate all files. The code must actually work — no pseudocode.

**Read `references/code-templates.md` for detailed templates and requirements** for each file: the fixed infrastructure (with `AUTORESEARCH_TEST_KEY` gate), the mutable file, `program.md` (with experiment loop, keep/discard logic, train-val gap threshold), `evaluate_test.py`, and supporting files.

### Phase 3e: Multi-Agent Support (optional)

Ask the user if they want multiple agents in parallel. If yes, **read `references/multi-agent.md`** for the independent branches model with git worktrees, launcher/comparison scripts, and resource isolation guidance.

### Phase 4: Verification

After generating all code:

1. **Sanity check**: Read through generated code for obvious issues
2. **Dry run**: Run the mutable file once to verify end-to-end
3. **Baseline**: Confirm the baseline metric is reasonable
4. **Git init**: Initialize repo, make initial commit
5. **Launch instructions**:
   - **Single agent**: Open AI agent in project dir, point at program.md, enable autonomous mode, walk away
   - **Multi-agent**: Run `bash launch_agents.sh <tag> <N>`, open an agent in each worktree

## Important Principles

- **Generate working code, not pseudocode.** Every file should be runnable.
- **The evaluation harness is sacred.** Wrong metric computation = all experiments meaningless.
- **Parseable output is critical.** Agent reads metrics from stdout via grep.
- **Git discipline matters.** Each experiment = one commit. Revert = `git reset --hard HEAD~1`.
- **Mutable file should be self-contained.** No deep import chains.
- **Seed everything reproducible.** Fixed random seeds where possible.
- **Test set isolation is non-negotiable.** Defense in depth: physical + programmatic (`AUTORESEARCH_TEST_KEY`) + `.gitignore`. Think Kaggle private leaderboard.
- **Monitor the train-val gap.** Growing gap = overfitting. Hard threshold in program.md for high-risk domains (finance, small datasets).
- **Time-series = chronological splits.** Never shuffle. Gap/purge between splits.
