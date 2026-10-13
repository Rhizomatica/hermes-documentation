# Reticulum on the station

> **Tentative proposal, 2026-10-13.** Nothing here is implemented yet.

Reticulum, together with NNCP, is the station's **encrypted** option for communication;
UUCP and plain broadcasts are the clear one. How Reticulum and NNCP work together is left
for later.

A HERMES station joins [Reticulum](https://github.com/markqvist/reticulum) in three
roles:

1. **A node for its Wi-Fi.** Phones and computers on the station's network (Sideband,
   NomadNet, MeshChat) reach the station's Reticulum transport node, and its LXMF
   propagation node holds messages for them while they are offline.
2. **Backhaul over HF.** Stations link to each other over Mercury ARQ, one link per
   neighbouring station, brought up like a UUCP call. Reticulum routes over those links.
3. **An LXMF client.** Each user of the station has an LXMF address, and LXMF is a third
   message channel next to UUCP and broadcast, in the same inbox.

The API side is in [api-rest.yaml](api-rest.yaml) (the `reticulum` tag, `lxmf` on
messages, `lxmf_address` on users, `transport` on calls and schedules) and
[api-ws.yaml](api-ws.yaml) (the `reticulum` topic).

## Why ARQ, not the broadcast plane

Mercury's own doc (`mercury/docs/RETICULUM.md`) describes two ways to carry Reticulum.
Running `rnsd` on the broadcast plane works on the bench, but it doesn't fit a HERMES
station:

- Reticulum needs a 500-byte MTU, and the broadcast plane doesn't fragment. Only DATAC1,
  DATAC17 and QAM16C2 are big enough, while the station listens for broadcasts in one
  mode (DATAC3 by default).
- Mercury's broadcast port takes one client, which the broadcast carousel already uses.
- Announces flood a shared HF channel that moves a few hundred bits a second.

Over ARQ, Mercury retransmits and adapts its mode on its own, using every rung from MFSK
to QAM16C2. The cost is that a session joins two stations only, and only one at a time.

## Backhaul links

Each link joins this station to one neighbour (`/reticulum/links/{station}`). A session is
an ARQ connection carrying Reticulum packets, framed as Reticulum's `PipeInterface`
frames them (HDLC-style), since the ARQ pipe is a byte stream.

**Bringing a link up** (`bring_up`):

| | When | Notes |
| --- | --- | --- |
| `on_demand` | messages wait for that station | Announces alone never start a call, or they would keep the radio busy |
| `scheduled` | in schedules with `transport` = `reticulum` | Like UUCP's call schedules |
| `permanent` | always | Holds the modem; UUCP calls and broadcasts wait. Only for a dedicated backbone hop |

A session closes after `idle_timeout_s` without traffic. Announces and propagation-node
synchronisation travel while the link is up.

**Sharing the ARQ link.** Mercury runs one ARQ session at a time, for one client.
radiod owns Mercury and decides who gets the modem. Calls of every kind (UUCP, NNCP,
Reticulum) go through the same line, `POST /queue/call` and the schedules, each with its
`transport`. `modem.status.session_transport` says what the current session carries.

**Routing an incoming call.** Mercury accepts calls addressed to up to four secondary
callsigns (`MYCALL <primary> <secondary…>`), and `CONNECTED <src> <dst>` reports which one
was called. The station registers a second callsign for Reticulum, `<callsign>-R` by
default (`arq_callsign`). A call to it goes to Reticulum, and a call to the primary
callsign stays UUCP. A link names the other station's Reticulum callsign
(`peer_arq_callsign`).

## The propagation node

Backhaul links are up for minutes a day, and phones come and go. The station runs an LXMF
propagation node (`lxmd`), the Reticulum counterpart of the UUCP spool: a message for an
address that isn't reachable now waits there, and goes out when a link or the phone comes
back. Propagation nodes on linked stations synchronise while the link is up.

Anyone on the Wi-Fi may use it, as Reticulum expects, so its storage is capped
(`propagation.storage_limit_mb`).

## The LXMF client

- **Addresses.** Each user has an LXMF identity, created and held by the station the first
  time Reticulum is on (`lxmf_address` on the user). The station has its own identity for
  its notices (`as_station`). The keys live on the station's disk with the database, so
  backing up the station backs them up; losing the card loses the addresses.
- **On the user's phone.** A user can export their identity
  (`POST /users/{id}/lxmf-identity/export`, own identity only, with their password) and
  import it in Sideband, which takes it as Base32 of the private key. The phone and the
  station then answer for the same address. Whoever holds the key controls the address,
  so the export is audited and never cached.
- **Sending.** A message with `lxmf: {to, method}` becomes one LXMF message per recipient,
  from the user's address. Each recipient's `state` is LXMF's own (outbound, sending,
  sent, delivered, rejected, cancelled, failed). `delivered` is the recipient's proof,
  a real receipt, unlike UUCP and broadcast. `method` = `auto` sends direct when a path is
  known and otherwise through the propagation node.
- **Receiving.** A message to a user's address lands in the inbox with `lxmf.to_user`. Its
  sender is `lxmf.from.address`; `verified` is false while the station hasn't heard that
  identity announce. Messages with a wrong signature are dropped.
- **Address book.** `GET /reticulum/peers` lists the LXMF addresses heard announcing.
  Display names are claims.
- **Announcing.** The station announces its users' addresses on the Wi-Fi and, while links
  are up, over the backhaul (`announce_interval_s`, `POST /reticulum/announce`).

## Rules

- **Encryption.** Reticulum encrypts everything, including what crosses the air on
  backhaul links. It stays off until an admin turns on `settings.encryption.reticulum`,
  for a station licensed to use encryption, like the other encryption switches.
- **Identification.** ARQ sessions carry Mercury's callsigns, so backhaul calls identify
  the station.
- **Untrusted input.** LXMF titles, contents, display names and attachment names come
  from anyone; the same rules apply as for other text from the air.

## In the API

| Reticulum | In `api-rest.yaml` |
| --- | --- |
| `rnsd` transport node, local interfaces | `GET /reticulum`, `/reticulum/settings` (`local`) |
| `lxmd` propagation node | `/reticulum/settings` (`propagation`); `ReticulumStatus.propagation` |
| ARQ backhaul interface per neighbour | `/reticulum/links/{station}`; `POST /queue/call` with `transport`; schedules with `transport` |
| incoming ARQ service routing | `arq_callsign`, `peer_arq_callsign`; `modem.status.session_transport` |
| user LXMF identities | `lxmf_address` on users; `as_station` for the station's; export to Sideband |
| LXMF messages | `channel` = `lxmf`; `lxmf` on create and on the message |
| announces heard | `GET /reticulum/peers`; `reticulum` topic, `change: peer` |

## Open questions

- [ ] **How radiod runs Reticulum.** `rnsd` and `lxmd` are Python. radiod could run them
  beside it and bridge the ARQ link to a `PipeInterface`, or embed a native
  implementation. What do they cost in RAM on a 1 GB Pi?
- [ ] **What starts an on-demand call.** Waiting LXMF messages for a destination reached
  through a link, certainly. Should propagation-node synchronisation, or Reticulum
  resources other than LXMF, also start one?
- [ ] **The Reticulum callsign.** Is `<callsign>-R` acceptable as a callsign under the
  stations' licences, or is another form needed?
- [ ] **One address on two devices.** With the identity exported, the phone and the
  station both receive for the address. Which one gets a given message depends on paths
  and propagation-node sync; does the station's inbox need to show what reached the phone?
- [ ] **Reticulum with NNCP.** How the two encrypted transports share the work.
- [ ] **Mail and LXMF.** Should replies cross channels, for example an LXMF message to a
  user forwarded as UUCP mail to another station?
