# Broadcast messages

> **Tentative proposal, 2026-10-12.** Nothing here is implemented yet. The wire format
> belongs to hermes-broadcast and Mercury, which keep `WIRE-FORMAT.md` identical; the
> changes below need agreeing there before anyone builds them.

A broadcast message goes to every station of an **area** at once, over Mercury's
one-way broadcast plane. It complements UUCP, which delivers to one station at a time
with acknowledgements. The API side is in [api-rest.yaml](api-rest.yaml): `broadcast` on
a message, `GET /areas`, `POST /messages/{id}/stop`, and `broadcast` in the modem
configuration.

## What exists today

- **The carousel.** [hermes-broadcast](https://github.com/Rhizomatica/hermes-broadcast)
  and Mercury send an object as a RaptorQ fountain carousel. Every frame carries the
  transfer parameters, so a receiver can start on any frame and decodes once it holds
  slightly more than the object's worth of symbols. The object is at most 1.44 MB.
- **The mode.** Sender and receivers must use the same Mercury mode; nothing negotiates
  it. Mercury listens for broadcasts in its idle mode (`-m`, or `MODE` while no ARQ link
  is up).
- **Encrypted broadcast.** The installer's `hermes-broadcast-send` encrypts a file to the
  network's NNCP area, tosses it in a private spool, packs the result with
  `nncp-bundle -tx` and hands the bundle to `broadcast_daemon`. Receivers run
  `nncp-bundle -rx` and `nncp-toss` on what they decode. Mercury's bench trial
  (`mercury/docs/BROADCAST-NNCP-TRIAL.md`) shows NNCP accepting such a bundle on a second,
  independently keyed node.
- **Plain broadcast.** Mercury wraps a file in a small bundle: a length, the basename and
  the file. Nothing says who sent it, what it is or whether it is still wanted.

## The problem with one packet per subscriber

Tossing an area packet makes one outgoing packet for each subscriber, each encrypted to
that node, and `nncp-bundle -tx <subscribers>` packs all of them. A broadcast to an area of
20 stations therefore carries 20 copies of the message, and the carousel runs about 20
times as long. On HF that is the difference between minutes and an hour.

## One object, carried two ways

A broadcast is one **object**: the header below, then the content (the message's `.hmp`
file, a file, or a control object), then a signature. The object is the same whether the
broadcast is encrypted or not, so the message id, expiry, supersedes, withdraw and author
work the same way in both cases.

- **Plain:** the object itself is what the carousel sends.
- **Encrypted:** the object is sent as an NNCP area packet (`nncp-file … area:<area>:`),
  in one bundle for the area's broadcast node (next section). NNCP adds the encryption
  and its own signature; the object inside is unchanged.

## Encrypted: one bundle for a broadcast pseudo-node

Each area gets one more NNCP node identity, its **broadcast node** (for example
`<area>-bcast`). Every member holds the broadcast node's private keys, handed out with the
area's keys by `hermes-nncp-area-export`.

1. The sender encrypts the object to the area, as today (`nncp-file … area:<area>:`).
2. It tosses it in a private spool where the area's only subscriber is the broadcast node,
   so there is exactly one outgoing packet.
3. `nncp-bundle -tx <area>-bcast` packs that one packet, and the carousel sends it.
4. A receiver opens the packet as the broadcast node, finds the area packet inside and
   tosses it as usual: NNCP decrypts it with the area's keys, checks the sender's
   signature, drops it if its `MsgHash` was already seen, and relays it to the area's
   other subscribers over ARQ.

The shared broadcast-node key is only the envelope. What keeps the message private is the
area encryption inside it, and what proves who sent it is the sender's signature. A
non-member who learns the broadcast-node key still can't read or forge a message.

Step 4's relaying is what makes encrypted broadcast dependable: a station that missed the
carousel still gets the message later, over ARQ, from a neighbour that heard it.

**Needs verifying:** whether `nncp-toss` can open packets addressed to a second identity in
the station's own spool. If not, the broadcast node needs its own configuration and spool,
and the area packet has to be handed to the main spool after the envelope is opened, so
that `MsgHash` deduplication still covers both paths (broadcast and ARQ relay).

## The object: a signed header

Encryption on the air isn't allowed on amateur bands, so a station without
`settings.encryption.messages` sends broadcasts in the clear. Signing hides nothing, so
every object is signed. A plain broadcast gets what NNCP gives an encrypted one: a known
sender, a message identity and a way to withdraw.

The header goes once at the start of the object, not in every RaptorQ frame. It replaces
Mercury's current bundle layout and starts with a magic that layout can't produce.

| Field | Size | Meaning |
| --- | --- | --- |
| magic | 4 | `HBM1` |
| kind | 1 | 0 message (`.hmp` file), 1 file, 2 control |
| flags | 1 | reserved, 0 |
| `msg_id` | 16 | random; the broadcast's identity everywhere |
| created | 4 | Unix time, UTC |
| expires | 4 | Unix time, 0 for never; receivers drop it after |
| `supersedes` | 16 | `msg_id` this one replaces, or zeros |
| area | 1 + n | length-prefixed, at most 32 |
| sender | 1 + n | UUCP name, at most 32 |
| callsign | 1 + n | at most 16 |
| author | 1 + n | username (mailbox name) of the user who sent it, at most 32; empty when the station sends as itself |
| name | 1 + n | file name for kind 1, basename only; empty otherwise |
| signing key | 32 | the sender's Ed25519 public key |
| content length | 4 | |
| content | n | |
| signature | 64 | Ed25519 over everything before it |

About 200 bytes, or five seconds at DATAC3.

- **Who wrote it.** Optional. By default a broadcast comes from the station, and
  broadcasts with no user behind them (scripts, automatic notices) are the same. The
  sender can choose to name themselves (`with_author`); then `author` goes on the air,
  in the clear for plain broadcasts. The station's signature vouches for it, so a
  receiver can show it and reply to `<author>@<domain>` by UUCP mail. It is the
  station's word for its own user, not a personal signature.

- **Who sent it.** A receiver keeps a broadcast only if the signing key is the one it has
  for `sender`. With the area's `allow_unknown`, it keeps it anyway, with no origin and
  the named sender as a claim (`claimed_origin` in the API).
- **Signing keys.** NNCP stations use their node's Ed25519 signing key, which the other
  stations already have. UUCP-only stations need a key pair and a way to distribute the
  public half (open question below).
- **Integrity.** The signature also catches a wrong decode, such as symbols from two
  objects mixed under a reused 5-bit session id.
- **Control objects** (kind 2) are small signed objects with their own short carousel.
  The first is **withdraw** (`msg_id`): receivers drop a partial decode and mark a copy
  they already decoded as withdrawn (`POST /messages/{id}/stop` with `withdraw`). It
  names the `msg_id`, for encrypted broadcasts too; a withdraw for an encrypted one goes
  encrypted to the same area.
  The second is **position**: a station's own `latitude`, `longitude`, optional
  `altitude_m`, `source` (`gps`, `manual` or `estimated`) and `at` timestamp. Receivers
  store it as the sender's last-known position (dropping an older `at` for the same
  sender) and surface it through `GET /gps/stations`. Like every decoded callsign, a
  position is a claim, not an identity. Sent periodically when `gps.settings.report` is
  enabled, and signed like any broadcast.
- Old receivers don't know the magic. They should file the object as an unnamed file,
  which needs checking against Mercury's and hermes-broadcast's bundle parsers.

## On the air

- A broadcast waits while an ARQ call holds the modem. Mercury changes mode only while the
  link is idle, so while a broadcast is on the air, calls wait for it.
- The sender picks the mode per message; the default, and what the station listens in,
  is `modem.config.broadcast.mode`.
- **Cycles.** A receiver that falls short decodes nothing at all, and the sender can't
  know. Extra passes cost airtime but not delivery time: in Mercury's trial, 4×, 8× and
  16× delivered at the same moment. On a fading path, send more cycles. On a weak but
  steady path, more cycles don't help; pick a more robust mode. The API defaults to 2
  and allows up to 16.
- Any user can broadcast. Every broadcast is a transmission: it counts against the
  user's `settings.tx_rate_limit.broadcasts_per_hour`, goes in the audit log as
  `radio.tx` with the user who sent it, and names that user on the air only if they
  choose to. Its author or an operator can stop it.

## In the API

| On the wire | In `api-rest.yaml` |
| --- | --- |
| area | `broadcast.area`; `GET /areas` lists them, with `has_keys`, `members` and `allow_unknown` |
| NNCP area packet or signed plain object | `broadcast.encrypt` on create, `broadcast.encrypted` on the message |
| Mercury mode | `broadcast.mode`; `modem.config.broadcast.mode`; `modem.status.listen_mode` |
| passes of the carousel | `broadcast.cycles`, `frames_total`, `frames_sent`, `air_time_s` |
| `msg_id` (and NNCP's `MsgHash` on the encrypted path) | one message per broadcast, however many passes or paths bring it |
| author | `broadcast.with_author` on create; `author` on the incoming message |
| expires | `broadcast.expires_at` |
| `supersedes` | `broadcast.supersedes` (the local message id) |
| withdraw | `POST /messages/{id}/stop` with `withdraw`; `broadcast.withdrawn_at` on receivers |
| verified signer | `origin`; `claimed_origin` only for `allow_unknown` |

## Open questions

- [ ] **Broadcast node in NNCP.** Can `nncp-toss` open packets for a second identity in the
  same spool, or does the broadcast node need its own (see above)?
- [ ] **Keys for UUCP-only stations.** Plain broadcasts need a signing key per station. Do
  UUCP-only stations get one from the installer, with the public keys shipped like
  `conf/nncp/pub/`, or is broadcast NNCP-only?
- [ ] **Relaying plain broadcasts.** NNCP relays encrypted ones over ARQ. Should a station
  that heard a plain broadcast also pass it on to members that may have missed it?
- [ ] **Announcements.** Is a control object worth having that says "broadcast *X* in mode
  *M* at time *T*", so receivers are in the right mode?
