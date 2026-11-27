"""Independent PR #7 edge cases, synthetic inputs only; no images or external APIs.

Run: .venv/bin/python -m scripts.research.pr7_review
Exit 0 means the probes ran, not that all reported behavior is correct.
"""
import json

from fastapi.testclient import TestClient

from app.main import create_app
from app.observer import pipeline
from app.observer.classifiers.mock import MockClassifier
from app.services import compute_summary, export_json
from scripts.research.pr3_review import fixture


def main():
    out = {'data_kind': 'SYNTHETIC REVIEW PROBES - NOT EXPERIMENT RESULTS'}
    with fixture() as (repo, settings):
        sid = repo.create_session('EXP-001', checkpoint='T0', capture_method='synthetic')['session_id']
        oid = repo.add_observation(sid, {'caption_text': 'Police pursuit on the highway',
            'recommendation_status': 'recommended', 'is_ad': False})['observation_id']
        pipeline.classify_session(repo, settings, sid, MockClassifier())
        before = repo.get_observation(oid)
        app = create_app(settings)
        try:
            with TestClient(app) as client:
                response = client.patch(f'/api/observations/{oid}', json={'confirm': True})
                after = response.json()
                exported = next(o for o in export_json(repo, 'EXP-001')['observations'] if o['observation_id'] == oid)
                explicit = client.patch(f'/api/observations/{oid}', json={'confidence': before['confidence']})
            out['V1_confirmed_unknown_keeps_machine_confidence'] = {
                'confirm_http': response.status_code, 'target_match': after['target_match'],
                'review_status': after['review_status'], 'before_confidence': before['confidence'],
                'after_confidence': after['confidence'], 'export_confidence': exported['confidence'],
                'machine_confidence': after['machine_label_json']['confidence'],
                'same_confidence_explicit_patch_http': explicit.status_code,
            }
        finally:
            app.state.repo.db.close()
    with fixture() as (repo, _):
        sid = repo.create_session('EXP-001', checkpoint='T2', capture_method='synthetic',
                                  captured_at='2026-06-01T10:00:00Z')['session_id']
        # A pre-D-027 row: observed_at could be stored without an offset. Both the session
        # and intervention timestamps are valid, so only this exposure needs a warning.
        repo.add_observation(sid, {'target_match': 'direct', 'review_status': 'confirmed',
            'recommendation_status': 'recommended', 'is_ad': False, 'observed_at': '2026-06-01T10:05:00'})
        repo.add_intervention('EXP-001', {'action_type': 'custom', 'actuator': 'manual',
            'status': 'completed', 'completed_at': '2026-06-01T09:00:00Z'})
        summary = compute_summary(repo, 'EXP-001')
        row = next(r for r in summary['sessions'] if r['session_id'] == sid)
        ttf = summary['time_to_first_target']
        out['V2_legacy_observation_timezone_assumption_is_unreported'] = {
            'session_capture_time_verified': row['capture_time_verified'],
            'time_to_first_target_measurable': ttf['measurable'],
            'hours_after_intervention': ttf['hours_after_intervention'],
            'has_timezone_warning': any('timezone' in w.lower() or 'read as utc' in w.lower()
                                        for w in summary['warnings']),
            'ttf_has_timezone_provenance': any('timezone' in k or 'verified' in k for k in ttf),
        }
    print(json.dumps(out, indent=2))


if __name__ == '__main__':
    main()
