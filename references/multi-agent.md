# Multi-Agent Support

Read this file when the user wants to run multiple agents in parallel.

## How it works

Each agent gets its own git branch and (if applicable) its own compute resource.
They explore independently and never interfere with each other. The human
compares results across branches after experiments are done.

```
autoresearch/<tag>-agent0   ← Agent 0 (e.g. GPU 0)
autoresearch/<tag>-agent1   ← Agent 1 (e.g. GPU 1)
autoresearch/<tag>-agent2   ← Agent 2 (e.g. separate machine)
```

## Launcher script (`launch_agents.sh`)

Generate this script:

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

## Results comparison script (`compare_agents.sh`)

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

## program.md multi-agent section

Add this to program.md when in multi-agent mode:

```markdown
## Multi-Agent Mode

This experiment may run with multiple agents in parallel, each on a separate
branch (e.g. `autoresearch/<tag>-agent0`, `autoresearch/<tag>-agent1`).

- You are on your own branch. You do NOT need to coordinate with other agents.
- Do NOT read, merge, or cherry-pick from other agent branches.
- Focus on your own exploration — diversity of approaches across agents is valuable.
- The human will compare results across all branches after experiments are done.
```

## Resource isolation

Discuss with the user:
- GPUs: use `CUDA_VISIBLE_DEVICES=N` per agent to pin each to a specific GPU
- API rate limits: divide the budget (e.g., 3 agents × 5 req/min = 15 req/min total)
- Disk: git worktrees share the `.git` object store, so disk usage is minimal
- CPU: each worktree is independent, no contention

## Cleanup

After experiments, the human can:
1. Compare `results.tsv` across all agent worktrees
2. Cherry-pick the best commits from the winning branch into main
3. Remove worktrees: `git worktree remove ../autoresearch-agent0`
