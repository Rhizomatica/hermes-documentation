# HERMES Engine Connectors

Status: draft POC — structure only (no Go source).

## What changed

The earlier draft described two external C engines (hermes-radio-daemon and
Mercury) reached over a WebSocket bridge (Spike A) or a cgo link (Spike B).
That is superseded: **hermes-radio-daemon is the backend and includes Mercury
in-process** (D-03), and radio control is **in-process** with no CLI, no
WebSocket bridge and no cgo link (D-05).

## The seams that remain

hermes-radio-daemon does not reach out to other engines. The only boundaries
left are compatibility seams for things that are *not* the backend:

| Seam | What it is | Why it stays |
| --- | --- | --- |
| `radio_client` | radiod's drop-in replacement for `sbitx_client`, over shared memory | Scripts (`iwatch`, `caller.sh`, `mailkill.sh`) and Mercury's `hermes_shm` PTT keep working while the UI moves off them |
| UUCP / Postfix / Dovecot | Mail runs on its own; the backend keeps the two ties hermes-api has today: mailbox `email_*_user` create/update/delete and the mail log | Un-upgraded stations keep mailing over UUCP (D-23) |
| `.hmp` | The on-disk message format between stations | Kept so stations on the old format can still exchange messages |

## Mapping to the design docs

| Element | Source |
| --- | --- |
| In-process radio + Mercury | `../../COMPARISON.md` D-03, D-05 |
| Mail ties (`email_*_user`, mail log) | `../../COMPARISON.md` D-23 |
| `radio_client` for scripts | `../../README.md` "must keep working"; `../../api-rest.yaml` |
