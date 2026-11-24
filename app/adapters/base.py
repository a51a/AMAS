"""Platform adapter interface.

An adapter describes what AMAS can do on a platform: which surfaces and
capture methods exist, which intervention actions are available, and how each
is carried out. Sprint 1 adapters are manual-only (supports_automation=False).
A future authorized adapter (official API / approved browser integration) plugs
in here without changing the experiment engine; it requires a separate
compliance review (docs/PLATFORM_COMPLIANCE.md).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ActionSpec:
    action_type: str
    title: str
    instructions: str
    confound_note: str = ""
    default_parameters: dict = field(default_factory=dict)
    reserved_for: str | None = None  # e.g. a separate experiment


class PlatformAdapter(ABC):
    platform: str
    surfaces: tuple[str, ...]
    capture_methods: tuple[str, ...]
    supports_automation: bool = False

    @abstractmethod
    def action_catalog(self) -> list[ActionSpec]: ...

    def get_action(self, action_type: str) -> ActionSpec:
        for a in self.action_catalog():
            if a.action_type == action_type:
                return a
        raise KeyError(f"Unknown action '{action_type}' for {self.platform}")

    def render_instructions(self, action_type: str, parameters: dict | None = None) -> str:
        spec = self.get_action(action_type)
        params = {**spec.default_parameters, **(parameters or {})}
        try:
            return spec.instructions.format(**params)
        except KeyError:
            return spec.instructions
