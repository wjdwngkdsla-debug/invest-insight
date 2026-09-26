# IPO repair memory

The bounded quality-audit stage remembers failures; it does not train a model or
rewrite executable code. The main collector still runs on its existing schedule.

## Flow

1. Recheck missing values, including completely empty tier arrays on older IPOs.
2. Retry unresolved companies before healthy recent companies, oldest attempt first.
3. Parse into a copy. Preserve known tiers and locked operator values on partial parses.
4. Compare stage-aware validation results. Reject new errors or loss of known values;
   retain the previous record and keep an actionable review flag.
5. Save bounded public filing table excerpts for failed parsing in
   `data/ipo_parser_cases.json`. Never save credentials or complete HTTP responses.
6. On parser/evidence revision changes, replay excerpts offline. A passing probe only
   suggests a fresh full-document recheck, never authorizes a financial-value update.
7. Close a failure case only after a full repair passes validation for the same receipt.

## Retry policy

Repeated identical unresolved/rejected attempts wait 1, 2, 4, then at most 7 days.
Source/network errors retry the next day. New source identities, operator inputs, or
parser/evidence revisions bypass the cooldown. Explicit `--corp-code` also bypasses
it. Each normal audit still has the existing four-company cap. Other collectors are
not throttled by this audit-only policy.

The signature includes parser source hashes, source receipt IDs, and key operator
inputs. A newly filed document can bypass cooldown once the ordinary collector has
observed its receipt; this does not promise immediate discovery of an unseen filing.

## Bounds and inspection

- Up to 80 cases, at most 48,000 characters per excerpt, up to four tables per case.
- Prefer evicting resolved cases; when all are unresolved, evict the oldest and count
  that eviction. This file is a bounded diagnostic sample, not a full archive.
- Truncated or missing excerpts require full-document investigation, not offline success.
- Keep the last five attempt outcomes per company in `quality_repair_state`.
- `ipo_quality_report.json` includes retry states, sample counts, and probe candidates.
- The review sheet memo shows repeated attempt count, next retry, and failure reasons.

Source contradictions, missing publication, and unrecognized formats can still require
operator evidence or a reviewed parser patch. Backoff never hides an unresolved review.

## Verification

The scheduled workflow runs the Python regression suite before pulling Sheet edits
or rebuilding data. A test failure therefore stops those mutation steps.

Run `python -m unittest discover -s scripts/tests` and
`python -m scripts.audit_ipo_quality --write` for an offline audit.
Use `--refresh --corp-code <DART-ID> --limit 1 --write` for a bounded source recheck.
