"""Shared pipeline exceptions."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PipelineFailure(Exception):
    stage: str
    code: str
    message: str
    retryable: bool = False
    abort_run: bool = False
    partial_success: bool = False

    def __post_init__(self):
        super().__init__(self.message)
