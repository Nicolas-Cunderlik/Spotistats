"""stemsim - dataset-driven pipeline for stem-based music similarity research.

Every dataset is mapped into one common model (schema.py) by an adapter
(datasets/), stored in a shared SQLite registry (registry.py), and processed
by independent, resumable stages (stages/). See section 9 of
investigation_and_plan.txt for the design, and `python -m stemsim --help`.
"""
