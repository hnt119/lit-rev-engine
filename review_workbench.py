#!/usr/bin/env python3
"""Separate local reviewer entry point; the frozen retrieval engine is unchanged."""

from src.review_workbench.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
