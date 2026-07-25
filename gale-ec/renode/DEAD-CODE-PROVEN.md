# Provably-unreachable branches (per-branch proof) — captured gale EC firmware

Purpose: the campaign drives BOTH directions of every *reachable* conditional. A small set of branches
are **provably unreachable in gale's fixed build configuration** — their condition is a compile-time
constant or an invariant that no runtime input can change. These are NOT coverage gaps and NOT
"structurally impossible" excuses: each is listed with an airtight source-level proof. They are exactly
the "dead code" the task asks to *identify* (reachable-confirmation), and they apply identically to the
captured and rebuilt firmwares (same source) — i.e. they are NOT divergences.

**Discipline:** a branch is listed here ONLY with a concrete proof that its missing direction cannot
execute for ANY input under gale's config. Conservative — when in doubt, it stays a coverage target.

The honest coverage metric is therefore: **reachable-both-dirs / (rda_denominator − proven_dead)**.

---

## host_command.c host_packet_receive — fixed I2C transport sizes (I2C_MAX_HOST_PACKET_SIZE = 128)

gale uses the I2C host-command transport (CONFIG_HOSTCMD_I2C). `chip/stm32/i2c-stm32f0.c` sets, as
compile-time constants (I2C_MAX_HOST_PACKET_SIZE = 128, line 33):
- `i2c_packet.request_size = I2C_MAX_HOST_PACKET_SIZE` (line 235) → always 128
- `i2c_packet.request_max  = I2C_MAX_HOST_PACKET_SIZE` (→ always 128)
- `i2c_packet.response_max = I2C_MAX_HOST_PACKET_SIZE` (line 242) → always 128

`sizeof(struct ec_host_response)` = 8 (ec_commands.h:642). Therefore in host_packet_receive
(common/host_command.c):

- **:257** `if (pkt->request_size < sizeof(*r))` — `128 < 8` is ALWAYS FALSE. The
  EC_RES_REQUEST_TRUNCATED branch is unreachable.  (captured 0x08005330 + RW 0x08015330)
- **:261** `if (pkt->request_size > pkt->request_max)` — `128 > 128` is ALWAYS FALSE. The
  truncated branch is unreachable.
- **:273** `ASSERT(pkt->response_max >= sizeof(struct ec_host_response))` = `ASSERT(128 >= 8)` — the
  condition is ALWAYS TRUE, so the `panic_assert_fail(...)` (assert-fail) branch is unreachable.
  (captured 0x0800533e, 0x08005342, 0x08005350 + RW 0x0801533e/42/50)

Proof basis: I2C_MAX_HOST_PACKET_SIZE is a `#define` (compile-time constant); request_size/request_max/
response_max are assigned it unconditionally before host_packet_receive runs; no code path reassigns
them from runtime data. Confirmed there is no other host-command transport compiled for gale (no
CONFIG_HOSTCMD_SPI in board/gale).

STATUS: PROVEN DEAD (per-branch). ~6–8 branches across RO+RW.

---

## (candidate, pending config confirmation) gpio-f0-l.c:127 ASSERT — no level-triggered GPIO ints

`gpio_init`/`gpio_set_flags` does `ASSERT(!(flags & (GPIO_INT_F_LOW | GPIO_INT_F_HIGH)))`. gale's
board/gale/gpio.inc declares no level-triggered (GPIO_INT_LOW/GPIO_INT_HIGH) interrupt GPIOs (grep:
none). If every flags value passed lacks those bits, the assert-fail branch is unreachable.
STATUS: LIKELY DEAD — needs an exhaustive check that no caller ever passes a LOW/HIGH flag.
(captured 0x0800143a, 0x08001446 + RW mirrors)

---

## util.c memmove — 0x0800a8f4 `bhi` (same-alignment overlapping backward copy) unreachable-taken

memmove (captured 0x0800a8cc / RW 0x0801a8cc) reaches the block at 0x0800a8de only on the
**overlapping** path: `dest > src` AND `dest < src+len` (else 0x0800a8d0/0x0800a8d6 divert to the
forward memcpy at 0x0800a8d8). Within that block, 0x0800a8ec `bne` falls through ONLY when the two
pointers share alignment: `(dest ^ src) & 3 == 0`. Then 0x0800a8f2 `cmp dest, ((dest+len) & ~3)` /
0x0800a8f4 `bhi` is taken iff `dest > (dest+len) & ~3`.

Proof the taken edge is infeasible for any input that reaches it:
- same alignment ⇒ `(dest - src)` is a multiple of 4, and `dest > src` ⇒ `dest - src ≥ 4`.
- overlapping ⇒ `len > dest - src ≥ 4`, so `len ≥ 5`.
- therefore `(dest+len) & ~3 ≥ (dest+len) - 3 ≥ dest + 2 > dest`, i.e. `dest ≤ (dest+len)&~3` ALWAYS.
- so `bhi` (dest strictly greater) can never be taken on this path. The fall-through (word-aligned
  middle copy) is the only reachable direction. (captured 0x0800a8f4 + RW 0x0801a8f4)

Covered both-dir everywhere else in memmove via fcall_lib.py; this single edge is mathematically dead.

---

## printf.c vfnprintf — 0x08005b82 `beq` (64-bit-dispatch 'T' check) unreachable-taken

In the PF_64BIT (`%l...`) integer dispatch, after the va_arg(uint64) load the conversion char `c` is
tested d→X→b, and the fall-through reaches 0x08005b80 `cmp c,#0x54('T')` / 0x08005b82 `beq`.
The ONLY branch into 0x08005b80 is 0x08005bb6 `bne` (the `%b` test fall-through). But a post-`l`
`'T'` is caught **earlier** at 0x08005b5c (`if (c=='T')` immediately after the `l` modifier consumes
the next char, printf.c:185), which diverts to the timestamp setup at 0x08005b60 and never falls into
the d/X/b chain. Therefore by the time control reaches 0x08005b82, `c` is provably ≠ 'T', so the
`beq` (c=='T') can never be taken. The block IS reachable (e.g. `"%lc"`, `"%la"` → c ≤ 'd', not d/X/b/T)
which covers the not-taken direction; the taken direction is mathematically dead.
(captured 0x08005b82 + RW 0x08015b82)

---

## usb_pd_protocol.c pd_task — PD_STATE_SUSPENDED handler unreachable (no pd_set_suspend caller)

`PD_STATE_SUSPENDED` is set ONLY by `pd_set_suspend(port, enable)` (usb_pd_protocol.c:2703:
`set_state(port, enable ? PD_STATE_SUSPENDED : PD_DEFAULT_STATE)`). A tree-wide grep
(`grep -rn pd_set_suspend --include=*.c --include=*.h`) finds **zero callers** — the only caller on
other ChromeOS boards is `common/charge_manager.c`, and gale explicitly does NOT enable
CONFIG_CHARGE_MANAGER (board/gale/board.h:48 documents this). The host command `hc_usb_pd_control`
(EC_CMD_USB_PD_CONTROL) handles role/mux/swap but never suspend, and no `pd` console subcommand calls it.

Therefore `pd[port].task_state` is never PD_STATE_SUSPENDED, so the `case PD_STATE_SUSPENDED:` body
(usb_pd_protocol.c:1968-1980: `pd_rx_disable_monitoring(port); while (task_state==SUSPENDED)
task_wait_event(-1);`) is never entered. Confirmed unreached in coverage:
- **0x08008ce8** [unreached] — line 1974 `pd_rx_disable_monitoring(port)` (the SUSPENDED case body).
Same source for captured + rebuilt, so this is NOT a divergence. (The switch-dispatch comparison that
*tests* for SUSPENDED is evaluated every pd_task loop and is reachable-one-direction, not listed dead.)

---

NOTE: this registry is small (~tens of branches). The large remaining gap (pd_task deep state/timing,
etc.) is REACHABLE-but-hard, not dead — those stay active coverage targets. This file only removes
branches that are mathematically uncoverable, each with proof, so the eventual "100% of reachable"
claim is honest and auditable by an independent agent.
