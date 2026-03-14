#!/usr/bin/env python3
"""Test the isolation layers in generated autoresearch code.

Updated for the two-directory + Claude Code hooks architecture:
- Layer 1: Two-directory split (agent-workspace/ vs human-eval/)
- Layer 2: evaluate() only accepts train/validation (ValueError on test)
- Layer 3: Claude Code hooks (enforce-branch.sh + protect-human-eval.sh)
- Layer 4: Train-val gap monitoring

Run against eval-3/eval-4 (mean reversion) output directory.
Usage: python test_isolation.py <agent-workspace-path> <project-root-path>
"""
import os
import sys
import json
import re
import stat
import subprocess

if len(sys.argv) < 3:
    print("Usage: python test_isolation.py <agent-workspace-path> <project-root-path>")
    print("  agent-workspace-path: path to agent-workspace/ directory")
    print("  project-root-path:    path to project root (parent of agent-workspace/ and human-eval/)")
    sys.exit(1)

AGENT_WORKSPACE = os.path.abspath(sys.argv[1])
PROJECT_ROOT = os.path.abspath(sys.argv[2])
HUMAN_EVAL = os.path.join(PROJECT_ROOT, "human-eval")

sys.path.insert(0, AGENT_WORKSPACE)

results = {"pass": 0, "fail": 0}


def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    results["pass" if condition else "fail"] += 1
    print(f"  [{status}] {name}")
    if detail:
        print(f"         {detail}")


# =============================================================
print("=" * 60)
print("Layer 1: Two-directory split")
print("=" * 60)

# evaluate_test.py must NOT be in agent-workspace
eval_test_in_workspace = os.path.exists(os.path.join(AGENT_WORKSPACE, "evaluate_test.py"))
check(
    "evaluate_test.py NOT in agent-workspace",
    not eval_test_in_workspace,
    "Should only exist in human-eval/"
)

# evaluate_test.py must be in human-eval/
eval_test_in_human = os.path.exists(os.path.join(HUMAN_EVAL, "evaluate_test.py"))
check(
    "evaluate_test.py IS in human-eval/",
    eval_test_in_human,
    f"Checked: {os.path.join(HUMAN_EVAL, 'evaluate_test.py')}"
)

# No test-related constants in agent's fixed infrastructure
# Find the fixed infrastructure file (backtest.py, prepare.py, harness.py, etc.)
infra_file = None
for candidate in ["backtest.py", "prepare.py", "harness.py", "benchmark.py", "simulator.py"]:
    path = os.path.join(AGENT_WORKSPACE, candidate)
    if os.path.exists(path):
        infra_file = path
        break

if infra_file:
    with open(infra_file) as f:
        infra_source = f.read()

    check(
        "No TEST_START/TEST_END in agent infrastructure",
        "TEST_START" not in infra_source and "TEST_END" not in infra_source,
        f"Checked {os.path.basename(infra_file)}"
    )
    check(
        "No _EXPECTED_KEY in agent infrastructure",
        "_EXPECTED_KEY" not in infra_source,
        f"Checked {os.path.basename(infra_file)}"
    )
    check(
        "No _load_test_data in agent infrastructure",
        "_load_test_data" not in infra_source and "load_test_data" not in infra_source,
        f"Checked {os.path.basename(infra_file)}"
    )
else:
    check("Fixed infrastructure file found", False, "None of backtest.py/prepare.py/harness.py/benchmark.py found")

# =============================================================
print()
print("=" * 60)
print("Layer 2: evaluate() rejects test split with ValueError")
print("=" * 60)

# Import the infrastructure module
infra_module = None
if infra_file:
    module_name = os.path.splitext(os.path.basename(infra_file))[0]
    import importlib
    infra_module = importlib.import_module(module_name)

if infra_module and hasattr(infra_module, "evaluate"):
    # Find the mutable file to get model/strategy/fn
    mutable_file = None
    for candidate in ["strategy.py", "train.py", "prompt.py", "solver.py", "config.py", "run.py"]:
        path = os.path.join(AGENT_WORKSPACE, candidate)
        if os.path.exists(path):
            mutable_file = candidate
            break

    # Test evaluate(split="test") raises ValueError
    try:
        # We need a callable to pass - try importing from mutable file
        if mutable_file:
            mutable_module = importlib.import_module(os.path.splitext(mutable_file)[0])
            # Try common function names
            fn = None
            for attr in ["generate_signals", "model", "solve", "run", "main"]:
                if hasattr(mutable_module, attr):
                    fn = getattr(mutable_module, attr)
                    break

            if fn:
                try:
                    infra_module.evaluate(fn, split="test")
                    check("ValueError on split='test'", False, "evaluate(split='test') did NOT raise!")
                except ValueError as e:
                    check("ValueError on split='test'", True, f"Correctly raised: {str(e)[:80]}")
                except Exception as e:
                    check("ValueError on split='test'", False, f"Wrong exception: {type(e).__name__}: {e}")

                # Verify train and validation work
                try:
                    infra_module.evaluate(fn, split="validation")
                    check("Validation split works", True)
                except Exception as e:
                    check("Validation split works", False, f"Error: {e}")

                try:
                    infra_module.evaluate(fn, split="train")
                    check("Train split works", True)
                except Exception as e:
                    check("Train split works", False, f"Error: {e}")
            else:
                check("Callable found in mutable file", False, f"No known function in {mutable_file}")
        else:
            check("Mutable file found", False, "None of strategy.py/train.py/prompt.py/solver.py found")
    except Exception as e:
        check("Import mutable file", False, f"Error: {e}")
else:
    check("evaluate() function found", False, "No evaluate() in infrastructure module")

# =============================================================
print()
print("=" * 60)
print("Layer 3: Claude Code hooks")
print("=" * 60)

hooks_dir = os.path.join(AGENT_WORKSPACE, ".claude", "hooks")
settings_path = os.path.join(AGENT_WORKSPACE, ".claude", "settings.json")

# Check enforce-branch.sh exists and is executable
enforce_path = os.path.join(hooks_dir, "enforce-branch.sh")
check(
    "enforce-branch.sh exists",
    os.path.exists(enforce_path),
    enforce_path
)
if os.path.exists(enforce_path):
    is_executable = os.stat(enforce_path).st_mode & stat.S_IXUSR
    check("enforce-branch.sh is executable", bool(is_executable))

    with open(enforce_path) as f:
        enforce_src = f.read()
    check(
        "enforce-branch.sh checks autoresearch/* prefix",
        "autoresearch/" in enforce_src and ("permissionDecision" in enforce_src or "deny" in enforce_src),
        "Must check branch name and deny if not autoresearch/*"
    )

# Check protect-human-eval.sh exists and is executable
protect_path = os.path.join(hooks_dir, "protect-human-eval.sh")
check(
    "protect-human-eval.sh exists",
    os.path.exists(protect_path),
    protect_path
)
if os.path.exists(protect_path):
    is_executable = os.stat(protect_path).st_mode & stat.S_IXUSR
    check("protect-human-eval.sh is executable", bool(is_executable))

    with open(protect_path) as f:
        protect_src = f.read()
    check(
        "protect-human-eval.sh checks for human-eval/ in tool input",
        "human-eval/" in protect_src and "tool_input" in protect_src,
        "Must extract tool_input fields and check for human-eval/"
    )
    check(
        "protect-human-eval.sh inspects multiple tool_input fields",
        "file_path" in protect_src and "command" in protect_src,
        "Should check file_path, command, pattern, path, prompt"
    )

# Check settings.json
check("settings.json exists", os.path.exists(settings_path))
if os.path.exists(settings_path):
    with open(settings_path) as f:
        settings = json.load(f)

    hooks_config = settings.get("hooks", {})
    pre_tool_use = hooks_config.get("PreToolUse", [])
    check(
        "PreToolUse hooks configured",
        len(pre_tool_use) > 0,
        f"Found {len(pre_tool_use)} PreToolUse hook group(s)"
    )

    if pre_tool_use:
        first_group = pre_tool_use[0]
        matcher = first_group.get("matcher", "")
        check(
            "Matcher covers file tools + Bash",
            all(t in matcher for t in ["Read", "Edit", "Write", "Bash", "Glob", "Grep"]),
            f"matcher: {matcher}"
        )

        hook_commands = [h.get("command", "") for h in first_group.get("hooks", [])]
        has_enforce = any("enforce-branch" in c for c in hook_commands)
        has_protect = any("protect-human-eval" in c for c in hook_commands)
        check("Settings references enforce-branch.sh", has_enforce)
        check("Settings references protect-human-eval.sh", has_protect)

# =============================================================
print()
print("=" * 60)
print("Layer 4: Train-val gap monitoring")
print("=" * 60)

# Check program.md has gap threshold
program_path = os.path.join(AGENT_WORKSPACE, "program.md")
if os.path.exists(program_path):
    with open(program_path) as f:
        program = f.read()
    check(
        "program.md has train_val_gap discard rule",
        "train_val_gap" in program and ("discard" in program.lower() or "丢弃" in program),
        "Found gap threshold rule"
    )

    threshold_match = re.search(r"train_val_gap.*?(?:>|exceeds?|超过|阈值)\s*([\d.]+)", program)
    if threshold_match:
        check("Gap threshold is specified", True, f"Threshold: {threshold_match.group(1)}")
    else:
        check("Gap threshold is specified", False, "No numeric threshold found")

    # program.md must NOT mention test set
    test_mentions = re.findall(r"test.?set|test.?split|test.?data", program, re.IGNORECASE)
    check(
        "program.md does NOT mention test set",
        len(test_mentions) == 0,
        f"Found mentions: {test_mentions}" if test_mentions else "Clean — no test references"
    )

    # Branch naming convention
    check(
        "program.md uses autoresearch/ branch prefix",
        "autoresearch/" in program,
        "Branch naming convention in setup section"
    )
else:
    check("program.md exists", False)

# =============================================================
# Final summary
print()
print("=" * 60)
total = results["pass"] + results["fail"]
print(f"TOTAL: {results['pass']}/{total} passed, {results['fail']} failed")
print("=" * 60)

sys.exit(0 if results["fail"] == 0 else 1)
