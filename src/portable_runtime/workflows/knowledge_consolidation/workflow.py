"""Compatibility import for the canonical knowledge workflows.

The implementation lives in :mod:`portable_runtime.workflows.daily_scan` so
there is one semantic write path. This module remains a stable import for
older deployments, but it does not import or write legacy ``Evidence`` or
``KnowledgeItem`` objects.
"""

from portable_runtime.workflows.daily_scan.workflow import (
    DailyScanWorkflow,
    KnowledgeConsolidationWorkflow,
)

__all__ = ["DailyScanWorkflow", "KnowledgeConsolidationWorkflow"]
