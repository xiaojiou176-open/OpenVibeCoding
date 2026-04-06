# Evaluation Suite

This directory contains regression evaluations for structured model output.

## Current Baseline

- config: `tests/evals/promptfoo/promptfooconfig.yaml`
- runner: `bash scripts/run_evals.sh`
- default provider path: Gemini

## Goal

The suite is meant to catch workflow regressions, not just connectivity smoke.
Cases should verify structured output, classification, decision quality, and
tool-path selection.
