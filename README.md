# Anything-AutoResearch

A Claude Code skill that builds autonomous research frameworks inspired by [Karpathy's autoresearch](https://github.com/karpathy/autoresearch) pattern.

## What it does

Turns any research problem with a measurable metric into a self-running experiment loop where an AI agent iterates autonomously — for hours, overnight, or indefinitely.

**Core pattern:** single mutable file + fixed infrastructure + agent instructions (`program.md`) + fixed time budget + single metric + experiment loop (modify → run → evaluate → keep/discard → repeat)

## Key features

- **4-phase workflow**: Problem Clarification → Architecture Design → Code Generation → Verification
- **Three-layer data isolation** (inspired by Kaggle public/private leaderboard):
  - Physical: test data outside agent's working tree
  - Programmatic: `AUTORESEARCH_TEST_KEY` env-var gate
  - Train-val gap monitoring with hard discard threshold
- **Multi-agent support**: independent git worktrees via `launch_agents.sh` + `compare_agents.sh`
- **Time-series aware**: chronological splits, gap/purge periods
- **Generates working code**: `prepare.py`, mutable file, `program.md`, `evaluate_test.py`

## Domains

Works for ANY domain with a clear metric:

| Domain | Mutable File | Metric Example |
|--------|-------------|----------------|
| ML training | `train.py` | validation loss |
| Prompt engineering | `prompt.py` | answer relevance |
| Trading strategy | `strategy.py` | Sharpe ratio |
| Compiler optimization | `passes.py` | binary size |
| Simulation | `config.py` | residual error |
| Algorithm research | `solver.py` | throughput |

## Installation

```bash
# Via npx skills (if available)
npx skills install anything-autoresearch

# Or manually: copy SKILL.md to your Claude Code skills directory
cp SKILL.md ~/.claude/skills/anything-autoresearch/SKILL.md
```

## Usage

Tell Claude Code:
> "帮我用 autoresearch 搭建一个自主优化 [你的问题] 的框架"

or:
> "Set up an autoresearch loop for my [problem] — I want the agent to run experiments overnight"

## Benchmark

Tested on 3 domains (ML training, RAG prompt optimization, mean reversion strategy):

| Configuration | Pass Rate |
|--------------|-----------|
| With Skill | **100%** (25/25 assertions) |
| Without Skill | 15.7% (4/25 assertions) |

The skill's core value: without it, Claude generates good optimization code but misses the autoresearch-specific patterns (program.md, test set isolation, train-val gap monitoring, git keep/discard loop).
