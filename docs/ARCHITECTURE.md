# Architecture (Sprint 1)

```
 screen recording (.mov/.mp4, made by the user)       manual quick-log
            │                                                │
            ▼                                                ▼
 ┌──────────────────────── Observer ─────────────────────────────┐
 │ media.py      ffprobe, frame extraction (JPEG, 1 fps)          │
 │               16×16 grey thumbnails of the centre column       │
 │ segmentation  frame-diff boundaries → Reel segments, aHash     │
 │ classifiers   Mock (keywords) | VisionLLM(provider) | OCR opt. │
 │ pipeline      import → segment → classify → human correction   │
 └───────────────┬───────────────────────────────────────────────┘
                 ▼  content_observations (raw, one row per Reel)
 ┌──────── Storage (SQLite, data/amas.sqlite) ───────────────────┐
 │ interest_profiles(+versions) experiments observation_sessions │
 │ recording_frames content_observations intervention_actions    │
 │ experiment_metrics (derived snapshots, recomputable)          │
 └──────┬──────────────────────────────┬─────────────────────────┘
        ▼                              ▼
 Evaluation Engine (pure)        Taste Engine (profiles)
        │                              │
        └────────────► Strategist (rules-v1) ──► plan (text)
                                   │ user decides
                                   ▼
                     Actuator ── PlatformAdapter
              Manual | Mock(demo) | FutureAuthorized(refuses)
              InstagramManualAdapter | MockPlatformAdapter
                                   │
                    FastAPI (/api) + Control Center (/)
```

## Modules
| Module | Responsibility |
|---|---|
| `app/models/schemas.py` | Enums (TargetMatch, RecommendationStatus, ReviewStatus, Checkpoint…) and API models |
| `app/storage` | Schema, thread-safe connection, repository (all SQL lives here) |
| `app/taste_engine` | Profiles, versions, loading `experiments/EXP-001-biathlon/config.json` |
| `app/observer` | FFmpeg I/O, segmentation, classifiers, pipeline, privacy gate |
| `app/evaluator` | `sample_metrics`, `experiment_summary`, Wilson/Newcombe intervals |
| `app/strategist` | Deterministic rules → findings, recommended actions, next checkpoint |
| `app/actuator` | Plans/records actions; enforces who may do what |
| `app/adapters` | Platform capabilities and action catalog |
| `app/api`, `app/web` | REST API and vanilla JS dashboard |

## Key data rules
- **Topic vs eligibility are separate.** `target_match` (direct/adjacent/unrelated/unknown) and
  `topic_label` describe content; `recommendation_status` (recommended/followed_account/
  search_result/undetermined) and `is_ad` describe whether it counts.
- **Primary metric** = direct / eligible, eligible = `recommended` and not an identified ad.
  Unknown topics stay in the denominator. `undetermined` is excluded, flagged, and covered by the
  all-exposure metric.
- **Raw vs derived.** Observations are raw. Metrics are recomputed on demand and optionally
  snapshotted into `experiment_metrics` with `metric_version`.
- **Human labels win.** Re-classification skips `confirmed`/`corrected` rows; the original machine
  label is kept in `machine_label_json`.

## Extension points
- New classifier: implement `Classifier.classify` (or a `VisionProvider.label` for another LLM).
- New platform: implement `PlatformAdapter` (surfaces, capture methods, action catalog).
- Authorized automation: implement an actuator behind `FutureAuthorizedActuator` only after a
  compliance review; the experiment engine does not change.

## Runtime
Single process (uvicorn), binds to 127.0.0.1. Recording import runs synchronously (a 50-Reel
recording of ~10 minutes takes seconds to a minute at 1 fps). No auth: local use only.
