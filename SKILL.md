---
name: anything-autoresearch
description: Build Karpathy-style autoresearch: AI agent autonomously runs experiment loops to optimize a metric. Trigger on "autoresearch", "自主实验", autonomous overnight optimization.
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

  **Two isolation modes** — ask the user which one they want:

  **Standard mode** (default) — two-directory split + Claude Code hooks enforcement:
  - Agent's `prepare.py` only has train/val — no test code, keys, or date ranges
  - `evaluate()` only accepts "train" / "validation" — no "test" branch at all
  - `human-eval/` directory lives outside agent's workspace with test data and `evaluate_test.py`
  - Train-val gap monitoring with hard discard threshold
  - **Claude Code hooks** block filesystem traversal to `human-eval/`:
    - `enforce-branch.sh`: blocks all tool calls if agent is not on an `autoresearch/*` branch
    - `protect-human-eval.sh`: blocks any tool call referencing `human-eval/`

  **Hardened mode** — for high-stakes domains (finance, competition, real money):
  - Everything in standard mode, PLUS:
  - Test data encrypted and stored in GitHub Secrets / CI environment
  - Test evaluation runs in GitHub Actions (disposable CI runner), not on agent's machine
  - Environment protection rules require human approval before secrets are accessible
  - Agent's `gh` CLI access restricted to prevent workflow injection attacks
  - **Read `references/hardened-isolation.md`** for the full architecture

  Recommend hardened mode for trading strategies, real-money decisions, and competitions.

  **Time-series specific**: NEVER randomly split — always chronological. Add gap/purge period between splits. Validation set must be fixed across all experiments.

  For domains without natural "data" (compiler optimization, algorithm design): reframe as development benchmarks (validation) vs held-out benchmarks (test).

**7. The Search Space** — What to explore, what's known to work/fail, domain knowledge?

Ask follow-up questions: crash handling, non-determinism, metric comparability, secondary metrics, validation set size, test set storage location.

### Phase 2: Architecture Design

Present the project structure for confirmation.

**Standard mode** (two-directory split + hooks):
```
<project>/
├── agent-workspace/          ← Agent's working directory (git repo)
│   ├── .claude/
│   │   ├── settings.json     ← Hooks configuration
│   │   └── hooks/
│   │       ├── enforce-branch.sh      ← Blocks tools if not on autoresearch/* branch
│   │       └── protect-human-eval.sh  ← Blocks access to human-eval/
│   ├── prepare.py            ← ONLY train+val data, NO test anything
│   ├── run.py                ← Mutable file
│   ├── program.md            ← No mention of test set
│   ├── results.tsv
│   ├── pyproject.toml
│   └── .gitignore
│
└── human-eval/               ← Outside agent's reach (hooks-enforced)
    ├── evaluate_test.py      ← Imports from agent-workspace, evaluates on test data
    ├── test_data/
    └── README.md
```

**Hardened mode** (standard + GitHub Secrets/CI):
```
<project>/
├── agent-workspace/          ← Same as standard mode
│   └── ...
├── human-eval/               ← evaluate_test.py (also in CI workflow)
│   └── ...
└── .github/workflows/
    └── test-eval.yml         ← workflow_dispatch, environment protection
```
Test data stored as encrypted GitHub Secrets or downloaded from protected storage during CI.
Human clicks "Run workflow" in GitHub UI → CI runner evaluates → results in workflow logs.

Domain naming conventions:
- ML: `prepare.py` + `train.py`
- Prompt engineering: `harness.py` + `prompt.py`
- Trading strategy: `backtest.py` + `strategy.py`
- Algorithm: `benchmark.py` + `solver.py`
- Simulation: `simulator.py` + `config.py`

### Phase 3: Code Generation

Generate all files. The code must actually work — no pseudocode.

**Read `references/code-templates.md` for detailed templates and requirements** for each file: the fixed infrastructure, the mutable file, `program.md` (with experiment loop, keep/discard logic, train-val gap threshold), `evaluate_test.py`, Claude Code hooks, and supporting files.

If using **hardened mode**, also **read `references/hardened-isolation.md`** for the two-directory architecture where the agent's workspace contains zero test-related code or data.

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

- **All autoresearch branches must use the `autoresearch/` prefix.** E.g. `autoresearch/mar12`, `autoresearch/mar12-agent0`. Claude Code hooks depend on this prefix to activate test set protection. Without it, hooks won't fire and isolation is bypassed.
- **Generate working code, not pseudocode.** Every file should be runnable.
- **The evaluation harness is sacred.** Wrong metric computation = all experiments meaningless.
- **Parseable output is critical.** Agent reads metrics from stdout via grep.
- **Git discipline matters.** Each experiment = one commit. Revert = `git reset --hard HEAD~1`.
- **Mutable file should be self-contained.** No deep import chains.
- **Seed everything reproducible.** Fixed random seeds where possible.
- **Test set isolation is non-negotiable.** Standard mode: two-directory split, agent workspace has zero test data. Hardened mode: adds GitHub Secrets + CI for air-gapped evaluation. Think Kaggle private leaderboard.
- **Monitor the train-val gap.** Growing gap = overfitting. Hard threshold in program.md for high-risk domains (finance, small datasets).
- **Time-series = chronological splits.** Never shuffle. Gap/purge between splits.
