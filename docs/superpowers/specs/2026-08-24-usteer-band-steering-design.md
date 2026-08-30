# usteer band steering — design

**Status:** approved 2026-08-24, not yet implemented
**Scope:** make 802.11v band steering demonstrably work on `ansells` and
`ansells-guest`. The IoT SSID is explicitly Phase 2 and out of scope here.

## Goal

Steer 5 GHz-capable clients onto the 5 GHz radio, and be able to *prove* it is
happening. Today nothing steers, and there is no instrument that would tell us
either way.

## Background: what the investigation actually found

All findings below were read from the usteer source at
`usteer-2025.10.04~1d6524c6`, confirmed by `apk list -I` to be the exact
installed package on the pucks, and from live `ubus` state on the welland fleet
on 2026-08-24.

### Band steering has never executed once

usteer tracks exactly two connected clients fleet-wide, both on puck10's
`wl-main-5g`. Both advertise 802.11v (`bss-transition-management: 1`), but both
report `bss-transition-response.age == 0`. usteer stamps that field whenever a
client answers a transition request, so a zero age on every tracked client
proves no request has ever been transmitted.

The cause is not a fault (`band_steering.c:67-69`):

```c
/* Band-Steering is only available on 2.4 GHz interfaces */
if (ln->node.freq > 4000)
    return;
```

Steering only iterates clients connected to the **2.4 GHz** BSS of a tracked
SSID. `wl-main-2g4` and `wl-guest-2g4` have zero clients on every puck. The
loop has always walked an empty list. Every BSS was verified `UP,LOWER_UP` on
its channel (2.4 GHz ch 6, 5 GHz ch 36) with the correct SSID, so this is
genuine client choice and not the known
`gwifi-openwisp-apply-breaks-beacon` NO-CARRIER failure.

### The association-steering path is inert, and this is the one real bug

`is_better_candidate()` (`policy.c:89`) can only return non-zero via three
reasons. All three are dead under the current config:

| reason | why it can never fire |
|---|---|
| `below_assoc_threshold` | returns false immediately when `load_balancing_threshold == 0` — ours is 0 |
| `better_signal_strength` | returns false when `signal_diff_threshold == 0` — ours is 0 |
| `has_better_load` | `policy.c:110` reads `has_better_load(a,b) && !has_better_load(a,b)` — an upstream bug, always false |

So `find_better_candidate()` always returns NULL and `assoc_steering = 1` has
never denied anything on any SSID.

The trap is the naming. `band_steering_threshold = 5` is the **only**
band-preference control for the association path, and its sole consumer
short-circuits on the line above it (`policy.c:32-38`):

```c
if (!config.load_balancing_threshold)
    return false;                                    /* always returns here */

if (ref_5g && !node_5g)
    n_assoc_new += config.band_steering_threshold;   /* penalise 5 -> 2.4  */
else if (!ref_5g && node_5g)
    n_assoc_cur += config.band_steering_threshold;   /* favour   2.4 -> 5  */
```

A setting literally called `band_steering_threshold` is dead config, while the
band steering that *does* work lives in another file and never reads it.

`signal_diff_threshold` is deliberately **not** the lever: 5 GHz has higher
path loss, so its signal is usually worse at equal distance and that comparison
would push clients the wrong way.

### 2.4 GHz-only devices cannot be steered — structurally

This is the safety requirement, and it is guaranteed by two independent gates
rather than by configuration:

**Gate A — the 802.11v nudge requires the client to advertise BSS-TM.**
`band_steering.c:94` sends a request only `if (si->bss_transition)`.
`bss_transition` is set in exactly one place, `local_node.c:430-434`, by
parsing the client's own Extended Capabilities IE (WNM octet, bit 3).

**Gate B — an assoc denial requires the client to have been seen on 5 GHz.**
`find_better_candidate()` (`policy.c:124-135`) walks `sta->nodes`, the list of
BSSes where that specific MAC has actually been observed, skipping sightings
older than `seen_policy_timeout` (30 s) and any different SSID. A single-band
radio is never observed on a 5 GHz BSS, so no candidate can exist.

Additionally, probe and auth requests are never denied at all: `probe_steering`
is hardcoded to 0 at `main.c:107` and is not UCI-parseable (which is why it
never appears in `get_config`), and `EVENT_TYPE_AUTH` returns immediately at
`policy.c:182`.

Both gates derive from the device's own behaviour — what it advertises and
where it has been heard — so no vendor allowlist is needed and future
dual-band IoT silicon is handled correctly with no maintenance.

We have live evidence Gate A works: both tracked clients are correctly flagged
`11v=1` by the same parser that will return 0 for an ESP8266.

### Why the IoT SSID is Phase 2

The client population there is ~88% Espressif (ESP8266/ESP32), which is
single-band 2.4 GHz silicon — 57 of the 65 clients on `wl-iot-2g4`, plus one
Tuya. Zero clients fleet-wide have been seen on both bands. Steering could
move at most the handful of Raspberry Pis.

Independently, the IoT BSSes lack the **AP-side** switch:

```
wifi_wl_main_2g4.bss_transition='1'     wifi_wl_iot_2g4  -> absent
wifi_wl_main_5g.bss_transition='1'      wifi_wl_iot_5g   -> absent
wifi_wl_guest_2g4.bss_transition='1'
wifi_wl_guest_5g.bss_transition='1'
```

Without `bss_transition` the IoT BSSes do not advertise WNM at all, so adding
`ansells-iot` to `ssid_list` alone would have steered nothing regardless of
client behaviour. `ieee80211k` is likewise absent there. Enabling either
partially conflicts with that SSID's documented high-compatibility intent, so
it needs its own decision.

## Design

### A. Configuration

Two values, added to `USTEER_CONFIG` in `openwisp/build-templates.py`. The
section must stay named `usteer1`: openwisp merges `/etc/config/*` by section
name, and an anonymous section appends a fresh copy on every apply (this
previously produced five `usteer` sections per puck).

| setting | value | why |
|---|---|---|
| `load_balancing_threshold` | `1` | un-gates the comparison so the existing `band_steering_threshold = 5` bias applies. The only actual fix. |
| `event_log_types` | `['assoc_req_accept', 'assoc_req_deny']` | visibility. Deliberately excludes `probe_req_*`, which with 65 IoT devices would flood the per-net rsyslog. |

Valid event names come from `event.c:26-37`. Note there is **no**
band-steering event type at all, so logging cannot report that a nudge was
sent — component B is the real instrument.

`ssid_list` is unchanged: `['ansells', 'ansells-guest']`.

### B. `tools/fleet/steer_report.py`

Read-only audit tool, one `ubus call usteer connected_clients` per puck.
Reports per client: 802.11v capability, `bss-transition-response`
status-code/age, kick count, roam state, band and signal. Pure parsing logic
separated from I/O so it is unit-testable without hardware, matching the
existing `galeflash` package layout.

This is what tells us whether steering fired. It replaces guessing from logs.

### C. Functional test

Test bed is `ansells-guest`: zero current users, so zero blast radius.

Test client is `rpi4-pmod` — Raspberry Pi 4 Model B Rev 1.5, dual-band, and
critically **dual-homed**: it holds both an `eth0` and a `wlan0` DHCP lease, so
management stays on ethernet while its wifi is reconfigured. Guest's
`isolate=1` is therefore irrelevant.

1. Snapshot the Pi's current wpa_supplicant config.
2. Arm an auto-revert timer **before** switching, so the Pi self-heals even if
   the wifi path is lost.
3. Add an `ansells-guest` profile pinned to 2.4 GHz via
   `freq_list=2412 2417 2422 2427 2432 2437 2442 2447 2452 2457 2462 2467 2472`.
4. Wait ≥60 s — `usteer_policy_can_perform_roam()` requires
   `connected_since >= roam_trigger_interval`.
5. Expected sequence, observed via `steer_report.py`: the MAC appears on
   `wl-guest-2g4` with `11v=1`, then `bss-transition-response.age` becomes
   non-zero, then the MAC appears on `wl-guest-5g`.
6. Restore the snapshot.

The guest passphrase comes from `gdoc2netcfg wifi show-login`; it is never
printed or committed.

### D. Rollout

Canary first with `ubus call usteer update_config`. usteer has **no UCI
write-back anywhere** in its source, so this is runtime-only and a reboot
reverts it — a self-healing canary.

Use `update_config`, never `set_config`: `ubus.c:259` shows `set_config` calls
`usteer_init_defaults()` first, which would wipe `network`, `ssid_list` and
everything else not restated in the same call.

**But `update_config` is only a merge for SCALARS.** Proven the hard way on
puck07, 2026-08-26: a call carrying just two integers silently emptied
`ssid_list`, leaving usteer tracking no SSIDs at all. `ubus.c:262-283`:

```c
case CFG_BOOL:
    if (!tb[i]) continue;                 /* absent -> preserved */
case CFG_I32:
case CFG_U32:
    if (!tb[i]) continue;                 /* absent -> preserved */
case CFG_ARRAY_CB:
case CFG_STRING_CB:
    config_data[i].ptr.CB.set(tb[i]);     /* NO absence check; set(NULL) clears */
```

Scalars skip when absent; array and string callbacks are invoked
unconditionally, so an omitted list is set from NULL and ends up empty.

**Rule: every `update_config` call MUST restate every array/string field it
wants to keep** — at minimum `ssid_list` and `interfaces`. Always diff
`get_config` before and after and confirm nothing but the intended keys moved;
do not assume omission is safe. Recovery is `/etc/init.d/usteer restart`,
which re-reads UCI.

Once the canary verifies, commit to the template and run
`build-templates.py` for both sites.

## Testing

- Unit tests for `steer_report.py` parsing against captured `connected_clients`
  JSON fixtures, in `tools/fleet/tests/`.
- Template assertions in `tests/openwisp/test_build_templates.py`:
  `load_balancing_threshold` and `event_log_types` present; `ssid_list` still
  excludes `ansells-iot`; section still named `usteer1`.
- Baseline before this work: 237 fleet + 19 openwisp tests passing.

## Risks

| risk | mitigation |
|---|---|
| `load_balancing_threshold = 1` also influences puck-to-puck roaming on main/guest | only 2 clients on those SSIDs; reversible instantly via `update_config` |
| Band steering is unproven in this deployment — this is its first real exercise | canary on one puck, on the zero-user guest SSID, with the audit tool watching |
| Losing management of the test Pi | manage over `eth0`; auto-revert armed before the change |
| Template apply appends a duplicate usteer section | section stays named `usteer1` (regression-tested) |

## Out of scope

- Adding `ansells-iot` to `ssid_list` (Phase 2).
- Enabling `bss_transition` / `ieee80211k` on the IoT BSSes (Phase 2, needs its
  own decision against that SSID's compatibility intent).
- The upstream `has_better_load` bug — reported behaviour, not fixed here.
- Deploying pucks 16–22 to spread the intrinsic 2.4 GHz IoT load.

---

## Addendum 2026-08-29 — the association path was reverted in production

The design above is **partly wrong in practice**, and the record has to say so.

### What happened

The association-path settings shipped to both sites on 2026-08-26:

```
option assoc_steering        '1'
option load_balancing_threshold '1'
option signal_diff_threshold '10'
```

Within three days every AP at welland was **denying associations** —
`hostapd status_code=17`, `usteer reason=better_candidate`. Clients could not
join anywhere. It was reverted by hand on the welland controller on
2026-08-29, keeping only `roam_trigger_snr '34'` and the two
`event_log_types`.

### Why the design was wrong

The "Background" section is right that all three association reasons were
gated off, and right that turning them on makes `is_better_candidate()` live.
What it did not follow through is what happens when **every** node evaluates
that predicate **simultaneously and symmetrically**:

* `better_signal_strength()` compares raw signal and is **band-blind** — 5 GHz
  arrives weaker than 2.4 GHz from the same distance, so the comparison does
  not mean what "better" implies;
* `below_assoc_threshold()` compares association **counts** and ignores signal
  entirely.

Neither predicate is antisymmetric, so for a client heard by several APs each
AP can conclude that a *different* AP is the better candidate — and each
defers. `assoc_steering='1'` turns every one of those deferrals into a denial.
The result is not "steered to the best AP" but "refused by all of them".

This is a **fleet-wide deadlock, not a threshold-tuning problem**. Raising or
lowering `signal_diff_threshold` does not fix a comparison that is symmetric
in the wrong way.

### What is kept

`roam_trigger_snr '34'` drives `usteer_local_node_roam_check()` — the **roam**
path — and was never implicated in the denials. It stays on, as do the two
`event_log_types` (observability only). Note the consequence: with
`signal_diff_threshold` unset, `find_better_candidate()`'s
`UEV_SELECT_REASON_SIGNAL` requirement (`policy.c:314`) can never be
satisfied, so the roam state machine runs but has no signal-reason candidate
to move toward. In practice that buys 802.11k neighbour reports and beacon
requests, **not** active kicks. That is the accepted trade until the
band-blind comparison is solved.

### Revised risk assessment

The original risk table said `load_balancing_threshold = 1` was "reversible
instantly via `update_config`". That was true of the *mechanism* and
irrelevant to the *impact*: the failure denies new associations rather than
degrading existing ones, so it is invisible on already-connected clients —
exactly the population a canary watches — and only surfaces as devices roam
or reconnect. **A one-puck canary could not have caught this**, because the
deadlock needs several APs running the config at once.

### Before re-enabling any of it

1. Make the candidate comparison band-aware, or restrict steering to within a
   single band.
2. Make the predicate antisymmetric, or add a tie-break so two APs cannot both
   defer.
3. Exercise it on **several** APs at once and measure association *success*,
   not just roam events — the metric the original plan lacked.
