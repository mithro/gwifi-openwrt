//
// gale EC Renode equivalence harness — STM32F0 embedded FLASH interface.
//
// Renode's stock STM32F072 platform leaves the flash controller as a bare Tag
// (every register reads 0). That breaks boot: chip/stm32/flash-f.c flash_pre_init
// reads FLASH_WRPR; a value of 0 means "all sectors write-protected NOW", which
// contradicts the (unprotected) option bytes, so the firmware tries to rewrite
// the option bytes and `system_reset`s to apply them — a boot loop.
//
// This model presents the real device's register state (STM32F0x2, RM0091
// "Embedded Flash memory" + "Option byte" chapters):
//   * WRPR  = 0xFFFFFFFF — no sector is write-protected (matches the dev unit:
//             option bytes WRP = 0xFF, security screw removed).
//   * SR.BSY is always 0 — modeled flash operations complete instantly
//     (deterministic; wait_busy() returns immediately).
//   * CR.LOCK starts set; the KEYR unlock key sequence clears it, OPTKEYR sets
//     OPTWRE — the genuine unlock handshake, so flashinfo/flashwp behave.
//   * OBR reports RDP level 0 (not read-protected), matching option byte 0xAA.
//   * ACR / AR / CR are read/write storage (latency, prefetch, address, control).
// Flash *content* programming is not performed here (the boot path never reaches
// it once reconciliation is a no-op); erase/program can be added if a test drives
// it. All values are deterministic — required for trace-equivalence.
//
namespace Antmicro.Renode.Peripherals.Miscellaneous
{
    using Antmicro.Renode.Core;
    using Antmicro.Renode.Logging;
    using Antmicro.Renode.Peripherals.Bus;

    public class GaleFlash : IDoubleWordPeripheral, IKnownSize
    {
        public GaleFlash(IMachine machine, long size = 0x400)
        {
            this.size = size;
            Reset();
        }

        public long Size => size;

        // Scenario-controlled FAULT INJECTION (default off -> equivalence tests unaffected).
        // Real flash CAN fail (write-protect violation, program error, stuck-busy); a complete
        // emulator models those so the firmware's EC_ERROR_* / WRPRTERR / PGERR / timeout paths
        // execute. A coverage scenario sets these, then drives a flash op (e.g. `flashwp now`
        // -> flash_physical_write); the equivalence battery never sets them, so behaviour there
        // is unchanged. `InjectWriteProtErr`/`InjectProgErr` latch the error on the next STRT and
        // self-clear; `StuckBusy` holds SR.BSY set so wait_busy() times out.
        public bool InjectWriteProtErr { get; set; }
        public bool InjectProgErr { get; set; }
        public bool StuckBusy { get; set; }

        public void Reset()
        {
            acr = 0x00000000;
            sr = 0x00000000;
            cr = CR_LOCK;        // flash control register locked after reset
            ar = 0x00000000;
            unlockState = 0;
            optUnlockState = 0;
        }

        public uint ReadDoubleWord(long offset)
        {
            switch(offset)
            {
                case ACR:  return acr;
                case SR:   return sr | (StuckBusy ? SR_BSY : 0u); // BSY=0 normally (instant op)
                case CR:   return cr;
                case OBR:  return OBR_LEVEL0;    // RDP level 0, not protected
                case WRPR: return 0xFFFFFFFF;    // no sector write-protected
                default:   return 0;
            }
        }

        public void WriteDoubleWord(long offset, uint value)
        {
            switch(offset)
            {
                case ACR:
                    acr = value;
                    break;
                case KEYR: // CR.LOCK unlock key sequence: KEY1 then KEY2
                    if(unlockState == 0 && value == KEY1) { unlockState = 1; }
                    else if(unlockState == 1 && value == KEY2) { cr &= ~CR_LOCK; unlockState = 0; }
                    else { unlockState = 0; }
                    break;
                case OPTKEYR: // option-byte write enable key sequence -> CR.OPTWRE
                    if(optUnlockState == 0 && value == KEY1) { optUnlockState = 1; }
                    else if(optUnlockState == 1 && value == KEY2) { cr |= CR_OPTWRE; optUnlockState = 0; }
                    else { optUnlockState = 0; }
                    break;
                case SR:
                    sr &= ~(value & SR_W1C); // EOP/PGERR/WRPRTERR are write-1-to-clear
                    break;
                case CR:
                    cr = value; // STRT launches a program/erase op; BSY stays 0 (instant) unless faulted
                    if((value & CR_STRT) != 0)
                    {
                        // Op result: set EOP (success), or a latched injected error (W1C by fw).
                        if(InjectWriteProtErr) { sr |= SR_WRPRTERR; InjectWriteProtErr = false; }
                        else if(InjectProgErr) { sr |= SR_PGERR; InjectProgErr = false; }
                        else { sr |= SR_EOP; }
                    }
                    break;
                case AR:
                    ar = value;
                    break;
            }
        }

        private uint acr, sr, cr, ar;
        private int unlockState, optUnlockState;
        private readonly long size;

        // Register offsets (RM0091, FLASH base 0x40022000)
        private const long ACR     = 0x00;
        private const long KEYR    = 0x04;
        private const long OPTKEYR = 0x08;
        private const long SR      = 0x0C;
        private const long CR      = 0x10;
        private const long AR      = 0x14;
        private const long OBR     = 0x1C;
        private const long WRPR    = 0x20;

        private const uint KEY1 = 0x45670123;
        private const uint KEY2 = 0xCDEF89AB;
        private const uint CR_LOCK   = 1u << 7;
        private const uint CR_OPTWRE = 1u << 9;
        private const uint CR_STRT   = 1u << 6;   // start program/erase
        private const uint SR_BSY      = 1u << 0;
        private const uint SR_PGERR    = 1u << 2;
        private const uint SR_WRPRTERR = 1u << 4;
        private const uint SR_EOP      = 1u << 5;
        private const uint SR_W1C    = (1u << 5) | (1u << 4) | (1u << 2); // EOP|WRPRTERR|PGERR
        private const uint OBR_LEVEL0 = 0x03FFFC00; // OPTERR=0, RDPRT=00 (level 0), USER/DATA = 0xFF
    }
}
