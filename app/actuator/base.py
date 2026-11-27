"""Actuators apply (or describe) interventions.

ManualActuator: produces instructions for the account owner and records when
they confirm completion. MockActuator: simulates completion, demo experiments
only. FutureAuthorizedActuator: placeholder for officially supported
integrations; always refuses in Sprint 1.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.adapters.base import PlatformAdapter
from app.models.schemas import ActionStatus, Authorization, normalize_timestamp, utcnow


class ActuatorUnavailable(RuntimeError):
    pass


class Actuator(ABC):
    name: str

    def __init__(self, adapter: PlatformAdapter):
        self.adapter = adapter

    @abstractmethod
    def plan(self, experiment: dict, action_type: str, parameters: dict, description: str) -> dict:
        """Return intervention_actions column values for a new action."""

    def complete(self, action: dict, *, completed_at: str | None, evidence_notes: str, skipped: bool) -> dict:
        raise ActuatorUnavailable(f"{self.name} actions cannot be completed manually.")


class ManualActuator(Actuator):
    name = "manual"

    def plan(self, experiment, action_type, parameters, description):
        spec = self.adapter.get_action(action_type)
        return {
            "action_type": action_type,
            "description": description or spec.title,
            "parameters_json": parameters,
            "instructions": self.adapter.render_instructions(action_type, parameters)
                            + (f"\n\nNote: {spec.confound_note}" if spec.confound_note else ""),
            "actuator": self.name,
            "status": ActionStatus.PENDING_USER.value,
            "authorization": None,
        }

    def complete(self, action, *, completed_at, evidence_notes, skipped):
        if skipped:
            return {"status": ActionStatus.SKIPPED.value, "evidence_notes": evidence_notes}
        return {
            "status": ActionStatus.COMPLETED.value,
            "completed_at": completed_at or utcnow(),
            "authorization": Authorization.USER_MANUAL.value,
            "evidence_notes": evidence_notes,
        }


class MockActuator(Actuator):
    name = "mock"

    def plan(self, experiment, action_type, parameters, description):
        if not experiment.get("is_demo"):
            raise ActuatorUnavailable("MockActuator is only allowed on demo experiments.")
        return {
            "action_type": action_type,
            "description": (description or action_type) + " [SIMULATED]",
            "parameters_json": parameters,
            "instructions": "Simulated action. Nothing was done on any platform.",
            "actuator": self.name,
            "status": ActionStatus.SIMULATED.value,
            "authorization": Authorization.SIMULATED.value,
            # Demo-only; still timezone-validated so summaries never mix naive and aware times (D-027).
            "completed_at": normalize_timestamp(parameters.get("completed_at"), field="completed_at") or utcnow(),
        }


class FutureAuthorizedActuator(Actuator):
    name = "authorized"

    def plan(self, experiment, action_type, parameters, description):
        raise ActuatorUnavailable(
            "Automated platform actions are not available. They require an officially supported integration "
            "and a separate platform permissions and compliance review (docs/PLATFORM_COMPLIANCE.md)."
        )


def get_actuator(name: str, adapter: PlatformAdapter) -> Actuator:
    return {"manual": ManualActuator, "mock": MockActuator, "authorized": FutureAuthorizedActuator}[name](adapter)
