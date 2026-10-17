# Contributing to ACS AI Orchestrator

Thank you for your interest in contributing to ACS AI! This guide outlines our development workflow, engineering standards, and submission guidelines.

---

## 1. Core Engineering Principles (Andrej Karpathy Guidelines)

All contributors must follow these four core principles:

1. **Think Before Coding**:
   - Understand the codebase before making changes.
   - Do not guess APIs, endpoints, or function signatures.
   - Clarify edge cases and failure modes upfront.
2. **Simplicity First**:
   - Write the minimum necessary code to solve the issue.
   - Avoid speculative generalization or premature abstractions (YAGNI).
   - Favor flat, direct control flow over complex nested patterns.
3. **Surgical Changes**:
   - Modify only the lines and functions strictly necessary.
   - Avoid formatting entire files or refactoring unrelated components.
   - Clean up temporary files, logs, and unused imports.
4. **Goal-Driven & Verification**:
   - Define clear acceptance criteria before coding.
   - Every feature or bug fix must be verified with automated tests.
   - Never submit changes without running the full test suite.

---

## 2. Development Setup

1. Fork or branch from `main`:
   ```bash
   git checkout -b feature/my-new-feature
   ```
2. Activate your virtual environment:
   ```bash
   source venv/bin/activate
   ```
3. Run the existing test suite:
   ```bash
   pytest tests/
   ```

---

## 3. Pull Request Guidelines

1. **Test Coverage**:
   - Add new tests in `tests/test_gate*.py` for any new functionality.
   - Regression tests must pass cleanly (`pytest tests/`).
2. **Security Checks**:
   - Run secret scanning before pushing (`git diff` inspection).
   - Never commit tokens, `.env` files, or SQLite databases.
   - Ensure CoreLock and Guardian fail-closed checks remain intact.
3. **Commit Messages**:
   - Use conventional commit messages:
     - `feat: add natural language mission parsing`
     - `fix: correct worktree checkout path traversal`
     - `docs: update installation instructions`
     - `test: add acceptance tests for gate 8`

---

## 4. Code of Conduct

Maintain respectful, constructive, and professional collaboration at all times.
