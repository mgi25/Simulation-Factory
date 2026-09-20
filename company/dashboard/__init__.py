"""Deterministic, read-only CEO view over canonical Company OS records."""

from .brief import CEOBrief, build_brief
from .builder import CompanyStatePaths, build_snapshot
from .diff import SnapshotChange, SnapshotDiff, diff_snapshots
from .integrity import check_integrity
from .models import (
    AttentionItem, AttentionLevel, Availability, CEODecisionItem, CompanyStateSnapshot,
    DashboardError, ExecutiveDimension, ExecutiveSection, FormatView, FreshnessState,
    ProjectView, SourceReference, SourceSubsystem,
)
from .store import DashboardStore

__all__ = ["AttentionItem", "AttentionLevel", "Availability", "CEOBrief", "CEODecisionItem",
           "CompanyStatePaths", "CompanyStateSnapshot", "DashboardError", "DashboardStore",
           "ExecutiveDimension", "ExecutiveSection", "FormatView", "FreshnessState", "ProjectView",
           "SnapshotChange", "SnapshotDiff", "SourceReference", "SourceSubsystem", "build_brief",
           "build_snapshot", "check_integrity", "diff_snapshots"]

