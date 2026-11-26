# Platform compliance and security

Instagram's terms restrict unauthorized automated access and collection of information. The
account owner's consent does not, by itself, establish permission from the platform.

## Sprint 1 rules (enforced by design)
| Rule | How AMAS complies |
|---|---|
| No automated Instagram login | No login code exists. |
| No passwords, cookies or session tokens | None are requested, stored or read. |
| No scraping or background playback | Input is only a recording the user made by hand, or manual entry. |
| No artificial views, likes, follows, comments or saves | Interventions are instructions the user performs; `ManualActuator` only records them. `MockActuator` is refused on non-demo experiments. `FutureAuthorizedActuator` always refuses. |
| No bypass of rate limits, access controls or bot detection | No network access to the platform at all. |
| No private messages or private account content | Only the Reels recommendation surface is observed. The protocol tells the user not to record DMs. |

## Privacy
- Local-first: database, recordings, frames and exports live in `data/` on the user's machine
  (git-ignored).
- **External model providers** are off by default and require both
  `AMAS_ALLOW_EXTERNAL_PROVIDERS=true` and per-experiment acceptance of an explicit privacy notice
  (frames may show other people's content and usernames). Only selected frames are sent, never the
  recording, credentials or tokens.
- Deletion: recording + frames (keeps labels) or a whole session with all derived data, from the UI
  or API. Exports are files the user controls.
- The API binds to 127.0.0.1 and has no authentication; do not expose it on a network.

## Future integrations
Any browser extension, automated capture or API integration needs a **separate platform
permissions and compliance review** before implementation, documented here, covering the
platform's terms, official API availability, data minimisation and user consent.
