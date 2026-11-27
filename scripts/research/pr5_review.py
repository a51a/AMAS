"""Synthetic PR #5 UI/API parity probe; no real data, images or external APIs.

Run: .venv/bin/python -m scripts.research.pr5_review
Requires Node for an isolated render of the actual intervention view. This is not
a full browser test. Exit 0 means the observations were produced, not all are correct.
"""
import json
import subprocess
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.services import accept_sample

RENDER = r'''
const fs = require('fs');
const vm = require('vm');
const payload = JSON.parse(fs.readFileSync(0, 'utf8'));
const source = fs.readFileSync(payload.source, 'utf8');
const start = source.indexOf('async function viewInterventions(id) {');
const end = source.indexOf('async function viewProfiles()', start);
if (start < 0 || end < 0) throw new Error('Renderer boundaries not found');
const view = {innerHTML: '', querySelectorAll: () => []};
const elements = {};
const document = {getElementById(id) {
  if (!view.innerHTML.includes(`id="${id}"`)) return null;
  return elements[id] ||= {value: '', checked: false};
}};
const context = vm.createContext({$view: view, document,
  expNav() {}, markNav() {}, demoBanner() {return '';},
  esc: v => String(v ?? ''), dt: v => String(v ?? ''), toast() {},
  api: async path => {
    if (!(path in payload.responses)) throw new Error(`Unexpected API: ${path}`);
    return payload.responses[path];
  },
});
vm.runInContext(source.slice(start, end), context);
(async () => {
  await context.viewInterventions('EXP-001');
  process.stdout.write(JSON.stringify({
    create_button_present: !!document.getElementById('aplan'),
    override_checkbox_present: !!document.getElementById('aoverride'),
    override_reason_present: !!document.getElementById('areason'),
    blocking_banner_present: view.innerHTML.includes('banner warn'),
  }));
})().catch(e => {console.error(e); process.exitCode = 1;});
'''


def main():
    with tempfile.TemporaryDirectory(prefix='amas-pr5-review-') as td:
        app = create_app(Settings(data_dir=Path(td), _env_file=None,
                                  allow_external_providers=False, ocr='off'))
        repo = app.state.repo
        try:
            for _ in range(2):
                sid = repo.create_session('EXP-001', checkpoint='T0', capture_method='synthetic')['session_id']
                for _ in range(50):
                    repo.add_observation(sid, dict(target_match='unrelated', review_status='confirmed',
                                                   recommendation_status='recommended', is_ad=False))
                accept_sample(repo, sid)
            sid = repo.create_session('EXP-001', checkpoint='ADHOC', capture_method='synthetic')['session_id']
            repo.add_observation(sid, dict(target_match='unknown', review_status='pending',
                                          recommendation_status='recommended', is_ad=False))
            with TestClient(app) as client:
                paths = ['/experiments/EXP-001', '/experiments/EXP-001/actions', '/experiments/EXP-001/plan']
                responses = {p: client.get('/api' + p).json() for p in paths}
                payload = {'source': str(Path('app/web/app.js').resolve()), 'responses': responses}
                render = subprocess.run(['node', '-e', RENDER], input=json.dumps(payload), text=True,
                                        capture_output=True, check=True)
                body = {'action_type': 'search_and_watch_target', 'actuator': 'manual'}
                blocked = client.post('/api/experiments/EXP-001/interventions', json=body)
                override = client.post('/api/experiments/EXP-001/interventions', json={**body,
                    'override_baseline_check': True, 'override_reason': 'Synthetic parity probe; not real consent'})
            result = dict(data_kind='SYNTHETIC REVIEW PROBE - NOT EXPERIMENT RESULTS',
                baseline_ready=responses[paths[0]]['summary']['baseline_readiness']['ready'],
                plan_status=responses[paths[2]]['status'],
                planning_without_override_http=blocked.status_code,
                planning_with_explicit_override_http=override.status_code,
                ui=json.loads(render.stdout))
            print(json.dumps(result, indent=2))
        finally:
            repo.db.close()


if __name__ == '__main__':
    main()
