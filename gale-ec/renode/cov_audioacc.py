#!/usr/bin/env python3
"""AUDIO-ACCESSORY lever — exercises pd_task's Type-C accessory-detection arms that need CC line
voltage combinations the prior models could not present. Uses the NEW GaleAdc.ForceAudioAccessory
knob (both CC lines in the Ra band, < 400 mV) so that when gale sources it classifies cc1==RA &&
cc2==RA -> the audio-accessory arm (usb_pd_protocol.c:1584) + its new_cc_state/cc_debounce handling
(:1597/:1598/:1602). Also walks debug-accessory (both Rd, :1576) and the accessory connect/disconnect
transitions (Ra<->Rd<->open) so the cc_state-change debounce runs both directions. Genuine execution
through the real CC classifier (cc_voltage_to_status). RO + RW. Accumulates tmp/audioacc_edges.pkl.
Usage: uv run --python .venv python cov_audioacc.py [rw]
"""
import os
import pickle
import subprocess
import sys

import coverage_captured as C

RW = "rw" in sys.argv
HERE = os.path.dirname(os.path.abspath(__file__))
CAPTURED = os.path.abspath(os.path.join(HERE, "..", "..", "gale-ec-gale_v1.1.5337-0115719-2026-06-04.bin"))
BASE = os.path.join(HERE, "base.resc")
TMP = os.path.join(HERE, "tmp")


def fold(trace, ex, ed):
    if not os.path.exists(trace):
        return
    prev = None
    with open(trace) as f:
        for ln in f:
            ln = ln.strip()
            if not ln.startswith("0x"):
                prev = None
                continue
            try:
                pc = int(ln, 16)
            except ValueError:
                prev = None
                continue
            ex.add(pc)
            if prev is not None:
                ed.add((prev, pc))
            prev = pc
    os.remove(trace)


def main():
    os.makedirs(TMP, exist_ok=True)
    trace = os.path.join(TMP, "audioacc.txt")
    if os.path.exists(trace):
        os.remove(trace)

    def cc(s, t="0.05"):
        return ['sysbus.usart1 WriteChar %d' % ord(ch) for ch in (s + "\r")] + ['emulation RunFor "%s"' % t]

    c = ['$h=@%s' % HERE, '$bin=@%s' % CAPTURED, '$name="cap"', 'include @%s' % BASE,
         'emulation RunFor "1.5"']
    if RW:
        c += cc("sysjump rw", "0.5")
    c += ['cpu CreateExecutionTracing "trau" @%s PC' % trace]

    # Put gale into the source side so SRC_DISCONNECTED runs the CC accessory classification.
    c += cc("pd dualrole source") + ['emulation RunFor "0.5"']

    # (1) AUDIO accessory present: both CC in Ra band -> cc1==RA && cc2==RA (:1584). Let it debounce.
    c += ['sysbus.adc ForceAudioAccessory true']
    c += ['emulation RunFor "1.2"']
    # connect/disconnect cycles: Ra -> open -> Ra exercises new_cc_state change + cc_debounce both ways
    for _ in range(3):
        c += ['sysbus.adc ForceAudioAccessory false', 'emulation RunFor "0.5"']
        c += ['sysbus.adc ForceAudioAccessory true', 'emulation RunFor "0.6"']

    # (2) accessory TYPE change without going open: audio (Ra/Ra) -> debug (Rd/Rd) -> audio.
    for _ in range(2):
        c += ['sysbus.adc ForceAudioAccessory false', 'sysbus.adc ForceAccessory true', 'emulation RunFor "0.6"']
        c += ['sysbus.adc ForceAccessory false', 'sysbus.adc ForceAudioAccessory true', 'emulation RunFor "0.6"']
    c += ['sysbus.adc ForceAudioAccessory false', 'sysbus.adc ForceAccessory false', 'emulation RunFor "0.5"']

    # (3) POWERED-CABLE termination (Ra on CC1, Rd on CC2): cc1==RA && cc2!=RA -> the FALL-THROUGH of
    # the audio-accessory test (usb_pd_protocol.c:1584), the genuine residual the both-Ra case can't hit.
    c += cc("pd dualrole source") + ['emulation RunFor "0.4"']
    c += ['sysbus.adc ForceCableRa true', 'emulation RunFor "1.2"']
    for _ in range(2):
        c += ['sysbus.adc ForceCableRa false', 'emulation RunFor "0.5"']
        c += ['sysbus.adc ForceCableRa true', 'emulation RunFor "0.6"']
    # transition cable(Ra/Rd) -> audio(Ra/Ra) -> debug(Rd/Rd): all cc_state changes + debounce arms
    c += ['sysbus.adc ForceCableRa false', 'sysbus.adc ForceAudioAccessory true', 'emulation RunFor "0.6"']
    c += ['sysbus.adc ForceAudioAccessory false', 'sysbus.adc ForceAccessory true', 'emulation RunFor "0.6"']
    c += ['sysbus.adc ForceAccessory false', 'emulation RunFor "0.5"']

    # (4) same under the free-running DRP toggle (source half of the toggle sees the accessory).
    c += cc("pd dualrole on")
    c += ['sysbus.adc ForceAudioAccessory true', 'emulation RunFor "1.5"']
    c += ['sysbus.adc ForceAudioAccessory false', 'sysbus.adc ForceCableRa true', 'emulation RunFor "1.2"']
    c += ['sysbus.adc ForceCableRa false', 'emulation RunFor "0.6"']
    c += cc("tcpc 0") + cc("pd 0 state")

    c += ['cpu DisableExecutionTracing', 'quit']
    rescf = os.path.join(TMP, "audioacc.resc")
    with open(rescf, "w") as f:
        f.write("\n".join(c) + "\n")
    subprocess.run(C._renode_cmd("include @%s" % rescf),
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, timeout=600)

    ex, ed = set(), set()
    outp = os.path.join(TMP, "audioacc_edges.pkl")
    if os.path.exists(outp):
        try:
            pe2, pd2 = pickle.load(open(outp, "rb"))
            ex |= set(pe2); ed |= set(pd2)
        except Exception:
            pass
    fold(trace, ex, ed)
    pickle.dump((ex, ed), open(outp, "wb"))
    print("saved -> tmp/audioacc_edges.pkl: %d edges, %d PCs (RW=%s)" % (len(ed), len(ex), RW))


if __name__ == "__main__":
    main()
