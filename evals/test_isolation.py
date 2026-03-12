#!/usr/bin/env python3
"""Test the three layers of test set isolation in generated code."""
import os
import sys
import importlib

# Test on eval-3 (mean reversion) which has the most isolation features
OUTPUTS = os.path.join(
    os.path.dirname(__file__),
    "eval-3-mean-reversion/with_skill/outputs"
)
sys.path.insert(0, OUTPUTS)

# Ensure no test key is set (simulate agent environment)
os.environ.pop("AUTORESEARCH_TEST_KEY", None)

import backtest

results = {"pass": 0, "fail": 0}

def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    results["pass" if condition else "fail"] += 1
    print(f"  [{status}] {name}")
    if detail:
        print(f"         {detail}")

print("=" * 60)
print("Layer 1: Physical isolation")
print("=" * 60)

# Check .gitignore excludes evaluate_test.py
gitignore_path = os.path.join(OUTPUTS, ".gitignore")
if os.path.exists(gitignore_path):
    with open(gitignore_path) as f:
        gitignore = f.read()
    check(
        "evaluate_test.py in .gitignore",
        "evaluate_test.py" in gitignore,
        f".gitignore contains: {[l for l in gitignore.splitlines() if 'evaluate_test' in l]}"
    )
else:
    check(".gitignore exists", False, "No .gitignore file found")

# Check test data is NOT directly loadable as a public function
check(
    "_load_test_data is private (underscore prefix)",
    hasattr(backtest, "_load_test_data") and not hasattr(backtest, "load_test_data"),
    "load_test_data (public) should not exist; _load_test_data (private) should"
)

print()
print("=" * 60)
print("Layer 2: Programmatic isolation (AUTORESEARCH_TEST_KEY)")
print("=" * 60)

# Test 1: evaluate(split="test") WITHOUT key should raise PermissionError
from strategy import generate_signals

try:
    backtest.evaluate(generate_signals, split="test")
    check("PermissionError without key", False, "evaluate(split='test') did NOT raise!")
except PermissionError as e:
    check(
        "PermissionError without key",
        True,
        f"Correctly raised: {str(e)[:80]}..."
    )
except Exception as e:
    check("PermissionError without key", False, f"Wrong exception type: {type(e).__name__}: {e}")

# Test 2: evaluate(split="test") WITH WRONG key should raise PermissionError
os.environ["AUTORESEARCH_TEST_KEY"] = "wrong_key_12345"
try:
    backtest.evaluate(generate_signals, split="test")
    check("PermissionError with wrong key", False, "Did NOT raise with wrong key!")
except PermissionError:
    check("PermissionError with wrong key", True, "Correctly rejected wrong key")
except Exception as e:
    check("PermissionError with wrong key", False, f"Wrong exception: {type(e).__name__}")

# Test 3: evaluate(split="validation") should work fine without any key
os.environ.pop("AUTORESEARCH_TEST_KEY", None)
try:
    val_result = backtest.evaluate(generate_signals, split="validation")
    check(
        "Validation works without key",
        "sharpe_ratio" in val_result,
        f"Sharpe ratio: {val_result.get('sharpe_ratio', 'N/A')}"
    )
except Exception as e:
    check("Validation works without key", False, f"Error: {e}")

# Test 4: evaluate(split="train") should work fine
try:
    train_result = backtest.evaluate(generate_signals, split="train")
    check(
        "Train works without key",
        "sharpe_ratio" in train_result,
        f"Sharpe ratio: {train_result.get('sharpe_ratio', 'N/A')}"
    )
except Exception as e:
    check("Train works without key", False, f"Error: {e}")

# Test 5: evaluate(split="test") WITH CORRECT key should work
import hashlib
correct_key = hashlib.sha256(b"autoresearch-mean-reversion-test-2024").hexdigest()
os.environ["AUTORESEARCH_TEST_KEY"] = correct_key
try:
    test_result = backtest.evaluate(generate_signals, split="test")
    check(
        "Test works WITH correct key",
        "sharpe_ratio" in test_result,
        f"Sharpe ratio: {test_result.get('sharpe_ratio', 'N/A')}"
    )
except Exception as e:
    check("Test works WITH correct key", False, f"Error: {e}")

# Clean up
os.environ.pop("AUTORESEARCH_TEST_KEY", None)

print()
print("=" * 60)
print("Layer 3: Train-val gap monitoring")
print("=" * 60)

# Check that train and val metrics are both computed
check(
    "Train metric available",
    train_result is not None and "sharpe_ratio" in train_result,
    f"train_sharpe = {train_result.get('sharpe_ratio')}"
)
check(
    "Val metric available",
    val_result is not None and "sharpe_ratio" in val_result,
    f"val_sharpe = {val_result.get('sharpe_ratio')}"
)

# Check program.md has gap threshold
program_path = os.path.join(OUTPUTS, "program.md")
if os.path.exists(program_path):
    with open(program_path) as f:
        program = f.read()
    check(
        "program.md has train_val_gap discard rule",
        "train_val_gap" in program and ("discard" in program.lower() or "丢弃" in program),
        f"Found gap threshold rule"
    )
    # Check for specific threshold
    import re
    threshold_match = re.search(r"train_val_gap.*?>\s*([\d.]+)", program)
    if threshold_match:
        check(
            "Gap threshold is specified",
            True,
            f"Threshold: {threshold_match.group(1)}"
        )
    else:
        check("Gap threshold is specified", False, "No numeric threshold found")
else:
    check("program.md exists", False)

# Check chronological split (no random)
check(
    "Chronological split (dates defined)",
    hasattr(backtest, 'TRAIN_START') and hasattr(backtest, 'VAL_START') and hasattr(backtest, 'TEST_START'),
    f"Train: {backtest.TRAIN_START}~{backtest.TRAIN_END}, Val: {backtest.VAL_START}~{backtest.VAL_END}, Test: {backtest.TEST_START}~{backtest.TEST_END}"
)

# Check gap periods
from datetime import datetime
train_end = datetime.strptime(backtest.TRAIN_END, "%Y-%m-%d")
val_start = datetime.strptime(backtest.VAL_START, "%Y-%m-%d")
val_end = datetime.strptime(backtest.VAL_END, "%Y-%m-%d")
test_start = datetime.strptime(backtest.TEST_START, "%Y-%m-%d")

gap1 = (val_start - train_end).days
gap2 = (test_start - val_end).days

check(
    "Gap between train and val",
    gap1 > 7,
    f"{gap1} days gap (train ends {backtest.TRAIN_END}, val starts {backtest.VAL_START})"
)
check(
    "Gap between val and test",
    gap2 > 7,
    f"{gap2} days gap (val ends {backtest.VAL_END}, test starts {backtest.TEST_START})"
)

# Final summary
print()
print("=" * 60)
total = results["pass"] + results["fail"]
print(f"TOTAL: {results['pass']}/{total} passed, {results['fail']} failed")
print("=" * 60)
