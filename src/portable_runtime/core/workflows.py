"""Workflow contract kept independent from concrete providers."""

from typing import Protocol

from .models import Run, Work


class Workflow(Protocol):
    id: str

    async def run(self, work: Work, run: Run) -> None: ...
