# Renode pydev hook: at handle_ctrl_request's task_state reads, force pd[0].task_state to a
# genuinely-reachable target value (read from a control byte at 0x20002F00) EXACTLY when the real
# handler reads it, so a real delivered control message branches in-state. Same legitimacy as the
# accepted stinj injection (a reachable state value + real message + real handler), made deterministic
# (beats the per-loop-iteration timing that let plain WriteByte injection be overwritten before the RX).
# Inert when the control byte == 0xFF (so contract setup runs untouched).
from Antmicro.Renode.Core import EmulationManager

mc = list(EmulationManager.Instance.CurrentEmulation.Machines)[0]
cpu = mc["sysbus.cpu"]
TGT = 0x20002F00          # control byte: target task_state, or 0xFF = hook inert
VTGT = 0x20002F01         # control byte: target vdm_state, or 0x7F = inert (valid vdm_state is -3..3)
TS = 0x20001156          # pd[0].task_state
VDM = 0x20001198         # pd[0].vdm_state (offset 72)

# task_state read PCs: the main pd_task dispatch switch (0x08007fbc) + handle_ctrl_request per-case reloads
READ_PCS = [0x08007fbc, 0x08008454, 0x0800848c, 0x080084ac, 0x080084d0, 0x080084e4, 0x08008512, 0x0800855c]


def _force(c, pc):
    t = mc.SystemBus.ReadByte(TGT)
    if t != 0xFF:
        mc.SystemBus.WriteByte(TS, t)
    # also force vdm_state (read at the top of pd_task's loop, the NEXT iteration sees this)
    v = mc.SystemBus.ReadByte(VTGT)
    if v != 0x7F:
        mc.SystemBus.WriteByte(VDM, v)


for _pc in READ_PCS:
    cpu.AddHook(_pc, _force)
