#!/bin/bash
# validate.sh - Standard validation wrapper for ZeroCoder projects
# This script runs lint, typecheck, and tests based on project type.
# Exit code 0 = all pass, non-zero = validation failed.

set -e

echo "=== VALIDATION GATE ==="

# Track failures
FAILED=0

# Detect project type and run validation
if [ -f "package.json" ]; then
    echo "Detected: Node.js project"

    # Lint
    if grep -q '"lint"' package.json 2>/dev/null; then
        echo "Running lint..."
        npm run lint || { echo "LINT FAILED"; FAILED=1; }
    else
        echo "No lint script configured (skipping)"
    fi

    # Typecheck
    if grep -q '"typecheck"' package.json 2>/dev/null; then
        echo "Running typecheck..."
        npm run typecheck || { echo "TYPECHECK FAILED"; FAILED=1; }
    elif [ -f "tsconfig.json" ]; then
        echo "Running tsc --noEmit..."
        npx tsc --noEmit || { echo "TYPECHECK FAILED"; FAILED=1; }
    else
        echo "No typecheck configured (skipping)"
    fi

    # Tests
    if grep -q '"test"' package.json 2>/dev/null; then
        echo "Running tests..."
        npm test || { echo "TESTS FAILED"; FAILED=1; }
    else
        echo "No test script configured (skipping)"
    fi

elif [ -f "requirements.txt" ] || [ -f "pyproject.toml" ] || [ -f "setup.py" ]; then
    echo "Detected: Python project"

    # Lint (ruff or flake8)
    if command -v ruff &>/dev/null; then
        echo "Running ruff..."
        ruff check . || { echo "LINT FAILED"; FAILED=1; }
    elif command -v flake8 &>/dev/null; then
        echo "Running flake8..."
        flake8 . || { echo "LINT FAILED"; FAILED=1; }
    else
        echo "No linter available (skipping)"
    fi

    # Typecheck (mypy or pyright)
    if command -v mypy &>/dev/null; then
        echo "Running mypy..."
        mypy . || { echo "TYPECHECK FAILED"; FAILED=1; }
    elif command -v pyright &>/dev/null; then
        echo "Running pyright..."
        pyright || { echo "TYPECHECK FAILED"; FAILED=1; }
    else
        echo "No typecheck available (skipping)"
    fi

    # Tests (pytest)
    if command -v pytest &>/dev/null; then
        echo "Running pytest..."
        pytest || { echo "TESTS FAILED"; FAILED=1; }
    elif [ -d "tests" ]; then
        echo "Running python -m pytest..."
        python -m pytest || { echo "TESTS FAILED"; FAILED=1; }
    else
        echo "No test framework available (skipping)"
    fi

elif [ -f "Cargo.toml" ]; then
    echo "Detected: Rust project"

    echo "Running cargo clippy..."
    cargo clippy -- -D warnings || { echo "LINT FAILED"; FAILED=1; }

    echo "Running cargo test..."
    cargo test || { echo "TESTS FAILED"; FAILED=1; }

elif [ -f "go.mod" ]; then
    echo "Detected: Go project"

    echo "Running go vet..."
    go vet ./... || { echo "LINT FAILED"; FAILED=1; }

    echo "Running go test..."
    go test ./... || { echo "TESTS FAILED"; FAILED=1; }

elif [ -f "CMakeLists.txt" ]; then
    echo "Detected: CMake project"

    if [ -d "build" ]; then
        echo "Running ctest..."
        cd build && ctest --output-on-failure || { echo "TESTS FAILED"; FAILED=1; }
    else
        echo "No build directory found (run cmake first)"
        FAILED=1
    fi

else
    echo "Unknown project type - no validation configured"
    echo "Consider creating a validate.sh in your project root"
    exit 0
fi

echo ""
if [ $FAILED -eq 0 ]; then
    echo "=== ALL VALIDATION PASSED ==="
    exit 0
else
    echo "=== VALIDATION FAILED ==="
    echo "Fix the issues above before closing the feature."
    exit 1
fi
