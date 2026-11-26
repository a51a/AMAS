"""REST API for the AMAS Control Center (local only, no auth: binds to 127.0.0.1)."""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse, Response
from pydantic import BaseModel

from app.actuator.base import ActuatorUnavailable, get_actuator
from app.adapters.registry import adapter_for
from app.models.schemas import (
    InterventionComplete,
    InterventionCreate,
    ManualObservation,
    ObservationPatch,
    ProfileUpdate,
    RecommendationStatus,
    SessionCreate,
    utcnow,
)
from app.observer import pipeline
from app.observer.media import MediaError
from app.observer.classifiers.ocr import ocr_available
from app.services import (
    ProtocolError,
    accept_sample,
    compute_plan,
    compute_summary,
    dumps,
    export_csv,
    export_json,
    unaccept_sample,
)
from app.storage.repository import NotFound, Repository
from app.strategist.rules import intervention_gate

router = APIRouter(prefix="/api")


def repo(request: Request) -> Repository:
    return request.app.state.repo


def settings(request: Request):
    return request.app.state.settings


def _nf(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except NotFound as e:
        raise HTTPException(404, str(e))


# ---------------- system ----------------
@router.get("/status")
def status(request: Request):
    s = settings(request)
    return {
        "classifier_default": s.classifier,
        "external_providers_enabled": s.allow_external_providers,
        "anthropic_model": s.anthropic_model,
        "ocr_available": ocr_available(),
        "ffmpeg_available": shutil.which("ffmpeg") is not None,
        "privacy_notice": pipeline.PRIVACY_NOTICE,
        "data_dir": str(s.data_dir.resolve()),
    }


# ---------------- experiments ----------------
@router.get("/experiments")
def list_experiments(request: Request):
    r = repo(request)
    out = []
    for e in r.list_experiments():
        summ = compute_summary(r, e["experiment_id"])
        out.append({**e, "summary": {
            "baseline_share": (summ["baseline"] or {}).get("direct_share"),
            "latest_share": ((summ["latest"] or {}).get("metrics") or {}).get("direct_share"),
            "change_pp": ((summ["latest"] or {}).get("vs_baseline") or {}).get("change_pp"),
            "sessions": len(summ["sessions"]),
            "exposures": sum(s["metrics"]["exposures_total"] for s in summ["sessions"]),
        }})
    return out


@router.get("/experiments/{experiment_id}")
def get_experiment(experiment_id: str, request: Request):
    r = repo(request)
    exp = _nf(r.get_experiment, experiment_id)
    return {
        "experiment": exp,
        "profile": r.get_profile(exp["profile_id"]),
        "sessions": r.list_sessions(experiment_id),
        "interventions": r.list_interventions(experiment_id),
        "summary": compute_summary(r, experiment_id),
    }


@router.post("/experiments/{experiment_id}/metrics")
def recompute_metrics(experiment_id: str, request: Request):
    return _nf(compute_summary, repo(request), experiment_id, store=True)


@router.get("/experiments/{experiment_id}/plan")
def get_plan(experiment_id: str, request: Request):
    return _nf(compute_plan, repo(request), experiment_id)


class Consent(BaseModel):
    accepted: bool


@router.post("/experiments/{experiment_id}/external-consent")
def set_consent(experiment_id: str, body: Consent, request: Request):
    return _nf(repo(request).set_external_consent, experiment_id, body.accepted)


@router.get("/experiments/{experiment_id}/export")
def export(experiment_id: str, request: Request, format: str = "json"):
    r = repo(request)
    exp = _nf(r.get_experiment, experiment_id)
    tag = "DEMO-" if exp["is_demo"] else ""
    if format == "csv":
        return PlainTextResponse(export_csv(r, experiment_id), media_type="text/csv", headers={
            "Content-Disposition": f'attachment; filename="{tag}{experiment_id}-observations.csv"'})
    if format == "json":
        return Response(dumps(export_json(r, experiment_id)), media_type="application/json", headers={
            "Content-Disposition": f'attachment; filename="{tag}{experiment_id}-export.json"'})
    raise HTTPException(400, "format must be csv or json")


# ---------------- sessions ----------------
@router.post("/experiments/{experiment_id}/sessions")
def create_session(experiment_id: str, body: SessionCreate, request: Request):
    return _nf(repo(request).create_session, experiment_id, checkpoint=body.checkpoint.value,
               capture_method=body.capture_method.value, label=body.label, captured_at=body.captured_at,
               notes=body.notes)


@router.get("/sessions/{session_id}")
def get_session(session_id: str, request: Request):
    r = repo(request)
    s = _nf(r.get_session, session_id)
    return {"session": s, "observations": r.list_observations(session_id=session_id),
            "frame_count": len(r.list_frames(session_id))}


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str, request: Request):
    _nf(repo(request).delete_session, session_id)
    return {"deleted": session_id}


@router.delete("/sessions/{session_id}/recording")
def delete_recording(session_id: str, request: Request):
    return _nf(repo(request).delete_recording, session_id)


@router.post("/sessions/{session_id}/recording")
def upload_recording(session_id: str, request: Request, file: UploadFile = File(...)):
    r = repo(request)
    _nf(r.get_session, session_id)
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in pipeline.ALLOWED_SUFFIXES:
        raise HTTPException(400, "Upload an MP4 or MOV screen recording.")
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, dir=settings(request).data_dir) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = Path(tmp.name)
    try:
        return pipeline.import_recording(r, settings(request), session_id, tmp_path,
                                         original_name=file.filename, move=True)
    except (MediaError, ValueError) as e:
        raise HTTPException(400, str(e))
    finally:
        tmp_path.unlink(missing_ok=True)


class PathImport(BaseModel):
    path: str


@router.post("/sessions/{session_id}/recording/from-path")
def import_from_path(session_id: str, body: PathImport, request: Request):
    """Import a recording that already sits on this computer (avoids a browser upload of large files)."""
    p = Path(body.path).expanduser()
    if not p.is_file():
        raise HTTPException(400, f"File not found: {p}")
    try:
        return pipeline.import_recording(repo(request), settings(request), session_id, p)
    except (MediaError, ValueError) as e:
        raise HTTPException(400, str(e))


class Boundaries(BaseModel):
    boundary_seconds: list[float]


@router.post("/sessions/{session_id}/segments/manual")
def manual_segments(session_id: str, body: Boundaries, request: Request):
    try:
        return pipeline.set_manual_boundaries(repo(request), session_id, body.boundary_seconds)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/sessions/{session_id}/segments/auto")
def auto_segments(session_id: str, request: Request):
    r = repo(request)
    s = _nf(r.get_session, session_id)
    if not s.get("recording_ref"):
        raise HTTPException(400, "Session has no recording.")
    return pipeline.extract_and_segment(r, settings(request), session_id)


class ClassifyRequest(BaseModel):
    classifier: str = "mock"
    include_reviewed: bool = False


@router.post("/sessions/{session_id}/classify")
def classify(session_id: str, body: ClassifyRequest, request: Request):
    r = repo(request)
    s = _nf(r.get_session, session_id)
    try:
        if body.classifier != "mock":  # privacy gate before any provider client is created
            pipeline.assert_external_allowed(settings(request), r.get_experiment(s["experiment_id"]))
        clf = pipeline.get_classifier(body.classifier, settings(request))
        return pipeline.classify_session(r, settings(request), session_id, clf, include_reviewed=body.include_reviewed)
    except pipeline.PrivacyGateError as e:
        raise HTTPException(403, str(e))
    except (ValueError, RuntimeError) as e:
        raise HTTPException(400, str(e))


class BulkEligibility(BaseModel):
    recommendation_status: RecommendationStatus
    only_undetermined: bool = True


@router.post("/sessions/{session_id}/eligibility")
def bulk_eligibility(session_id: str, body: BulkEligibility, request: Request):
    r = repo(request)
    _nf(r.get_session, session_id)
    return pipeline.bulk_set_eligibility(r, session_id, body.recommendation_status.value,
                                         only_undetermined=body.only_undetermined)


class AcceptSample(BaseModel):
    accepted: bool = True
    deviation_note: str | None = None


@router.post("/sessions/{session_id}/accept")
def accept_session(session_id: str, body: AcceptSample, request: Request):
    """Explicitly accept a sample for the protocol (R4). Incomplete samples need a recorded deviation note."""
    r = repo(request)
    _nf(r.get_session, session_id)
    if not body.accepted:
        return unaccept_sample(r, session_id)
    try:
        return accept_sample(r, session_id, deviation_note=body.deviation_note)
    except ProtocolError as e:
        raise HTTPException(409, {"message": str(e), "problems": e.problems})


@router.post("/sessions/{session_id}/observations")
def add_manual(session_id: str, body: ManualObservation, request: Request):
    return _nf(repo(request).add_manual_observation, session_id, body)


@router.post("/sessions/{session_id}/observations/bulk")
def add_manual_bulk(session_id: str, body: list[ManualObservation], request: Request):
    r = repo(request)
    _nf(r.get_session, session_id)
    return [r.add_manual_observation(session_id, m) for m in body]


# ---------------- observations ----------------
@router.patch("/observations/{observation_id}")
def patch_observation(observation_id: str, body: ObservationPatch, request: Request):
    r = repo(request)
    _nf(r.get_observation, observation_id)
    return pipeline.apply_correction(r, observation_id, body.model_dump(mode="json", exclude_unset=True))


@router.delete("/observations/{observation_id}")
def delete_observation(observation_id: str, request: Request):
    _nf(repo(request).delete_observation, observation_id)
    return {"deleted": observation_id}


@router.post("/observations/{observation_id}/merge-next")
def merge_next(observation_id: str, request: Request):
    try:
        return pipeline.merge_with_next(repo(request), observation_id)
    except ValueError as e:
        raise HTTPException(400, str(e))


class Split(BaseModel):
    at_seconds: float


@router.post("/observations/{observation_id}/split")
def split(observation_id: str, body: Split, request: Request):
    try:
        return pipeline.split_at(repo(request), observation_id, body.at_seconds)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/observations/{observation_id}/frames")
def observation_frames(observation_id: str, request: Request):
    r = repo(request)
    o = _nf(r.get_observation, observation_id)
    frames = r.list_frames(o["session_id"])
    start, end = o.get("video_offset_seconds"), o.get("segment_end_seconds")
    if start is None or end is None:
        return []
    return [{"frame_id": f["frame_id"], "offset_seconds": f["offset_seconds"]}
            for f in frames if start - 1e-6 <= f["offset_seconds"] < end - 1e-6]


@router.get("/frames/{frame_id}")
def frame_image(frame_id: int, request: Request):
    f = repo(request).get_frame(frame_id)
    if not f or not Path(f["path"]).exists():
        raise HTTPException(404, "frame not found")
    return FileResponse(f["path"], media_type="image/jpeg")


# ---------------- interventions ----------------
@router.get("/experiments/{experiment_id}/actions")
def action_catalog(experiment_id: str, request: Request):
    exp = _nf(repo(request).get_experiment, experiment_id)
    adapter = adapter_for(exp["platform"])
    return {"platform": adapter.platform, "supports_automation": adapter.supports_automation,
            "actions": [a.__dict__ for a in adapter.action_catalog()]}


@router.post("/experiments/{experiment_id}/interventions")
def create_intervention(experiment_id: str, body: InterventionCreate, request: Request):
    r = repo(request)
    exp = _nf(r.get_experiment, experiment_id)
    gate = intervention_gate(compute_summary(r, experiment_id), r.list_interventions(experiment_id))
    parameters = dict(body.parameters)
    if not gate["open"]:
        reason = (body.override_reason or "").strip()
        if not body.override_baseline_check:
            raise HTTPException(409, {"message": "Baseline or review data is not ready for a T1 intervention.",
                                      "problems": gate["problems"]})
        if not reason:
            raise HTTPException(400, "override_reason is required when override_baseline_check is true.")
        parameters["baseline_override"] = {"reason": reason, "problems": gate["problems"], "at": utcnow()}
    try:
        act = get_actuator(body.actuator, adapter_for(exp["platform"]))
        values = act.plan(exp, body.action_type, parameters, body.description)
    except ActuatorUnavailable as e:
        raise HTTPException(403, str(e))
    except KeyError as e:
        raise HTTPException(400, str(e))
    return r.add_intervention(experiment_id, values)


@router.post("/interventions/{action_id}/complete")
def complete_intervention(action_id: str, body: InterventionComplete, request: Request):
    r = repo(request)
    a = _nf(r.get_intervention, action_id)
    exp = r.get_experiment(a["experiment_id"])
    try:
        act = get_actuator(a["actuator"], adapter_for(exp["platform"]))
        values = act.complete(a, completed_at=body.completed_at, evidence_notes=body.evidence_notes,
                              skipped=body.skipped)
    except ActuatorUnavailable as e:
        raise HTTPException(400, str(e))
    return r.update_intervention(action_id, values)


# ---------------- profiles ----------------
@router.get("/profiles")
def list_profiles(request: Request):
    return repo(request).list_profiles()


@router.get("/profiles/{profile_id}")
def get_profile(profile_id: str, request: Request):
    r = repo(request)
    return {"profile": _nf(r.get_profile, profile_id), "versions": r.profile_versions(profile_id)}


@router.put("/profiles/{profile_id}")
def update_profile(profile_id: str, body: ProfileUpdate, request: Request):
    changes = body.model_dump(mode="json", exclude_unset=True)
    return _nf(repo(request).update_profile, profile_id, changes)
