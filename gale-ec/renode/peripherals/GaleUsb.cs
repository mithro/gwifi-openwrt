//
// gale EC Renode equivalence harness — STM32F0 USB full-speed DEVICE controller.
//
// Renode's stock STM32F072 platform leaves the USB device peripheral (and its packet
// memory) as bare Tags, so the firmware's usb_init / enumeration / the USB UART
// consoles (if00 EC, if01 AP) and the raiden SPI bridge (if03) cannot run. This is a
// model of the STM32F0x2 USB_FS device controller (RM0091 "Universal serial bus
// full-speed device interface (USB)") + its 1 KB packet-memory SRAM (PMA), driven by
// the firmware exactly as on hardware; a host bridge (see InjectSetup / the harness)
// drives control/bulk transfers so enumeration and the USB endpoints actually run.
//
// Registers (USB_FS base 0x40005C00):
//   EPnR  n*4  (n=0..7) — endpoint registers with the special toggle/rc_w0 semantics
//   CNTR  0x40 — control (FRES/PDWN + interrupt mask bits)
//   ISTR  0x44 — interrupt status (CTR ro, RESET, etc.; rc_w0)
//   FNR   0x48 — frame number (ro)
//   DADDR 0x4C — device address + EF (enable function)
//   BTABLE 0x50 — buffer-descriptor-table offset in PMA
// PMA: 1 KB SRAM at 0x40006000 (btable + endpoint buffers), accessed 16-bit.
//
// EPnR write semantics (RM0091 §USB_EPnR), modeled exactly:
//   CTR_RX(15)/CTR_TX(7): rc_w0  (write 0 clears, write 1 leaves unchanged; HW sets)
//   DTOG_RX(14)/DTOG_TX(6): toggle (write 1 toggles, write 0 leaves unchanged)
//   STAT_RX(13:12)/STAT_TX(5:4): toggle (each bit toggles if written 1)
//   SETUP(11): read-only;  EP_TYPE(10:9)/EP_KIND(8)/EA(3:0): normal r/w
//
namespace Antmicro.Renode.Peripherals.Miscellaneous
{
    using Antmicro.Renode.Core;
    using Antmicro.Renode.Core.Structure.Registers;
    using Antmicro.Renode.Logging;
    using Antmicro.Renode.Peripherals;
    using Antmicro.Renode.Peripherals.Bus;

    // 16-bit register peripheral (the EC accesses USB regs as REG16).
    public class GaleUsb : IWordPeripheral, IKnownSize, IGPIOReceiver
    {
        public GaleUsb(IMachine machine, long size = 0x400)
        {
            this.size = size;
            this.machine = machine;
            IRQ = new GPIO();
            Reset();
        }

        public GPIO IRQ { get; }
        public long Size => size;

        public void Reset()
        {
            for(var i = 0; i < ep.Length; i++) { ep[i] = 0; }
            cntr = 0x0003;   // FRES|PDWN at reset
            istr = 0;
            daddr = 0;
            btable = 0;
            fnr = 0;
            IRQ.Unset();
        }

        // Chip-select-style: not used; present so the platform can wire signals if needed.
        public void OnGPIO(int number, bool value) { }

        public ushort ReadWord(long offset)
        {
            if(offset < 0x20) { return ep[offset / 4]; }
            switch(offset)
            {
                case CNTR:  return cntr;
                case ISTR:  return istr;
                case FNR:   return fnr;
                case DADDR: return daddr;
                case BTABLE: return btable;
            }
            return 0;
        }

        public void WriteWord(long offset, ushort value)
        {
            if(offset < 0x20)
            {
                WriteEp(offset / 4, value);
                return;
            }
            switch(offset)
            {
                case CNTR:  cntr = value; break;
                case ISTR:  istr &= value; UpdateIrq(); break; // rc_w0: write 0 clears flags
                case DADDR: daddr = value; break;
                case BTABLE: btable = (ushort)(value & 0xFFF8); break;
            }
        }

        // EPnR special read-modify-write (toggle / rc_w0 / rw fields).
        private void WriteEp(long n, ushort v)
        {
            var c = ep[n];
            ushort nw = 0;
            nw |= (ushort)(((v & CTR_RX) != 0) ? (c & CTR_RX) : 0);          // rc_w0
            nw |= (ushort)((c & DTOG_RX) ^ (v & DTOG_RX));                   // toggle
            nw |= (ushort)((c & STAT_RX) ^ (v & STAT_RX));                   // toggle
            nw |= (ushort)(c & SETUP);                                       // read-only
            nw |= (ushort)(v & (EP_TYPE | EP_KIND | EA));                    // rw
            nw |= (ushort)(((v & CTR_TX) != 0) ? (c & CTR_TX) : 0);          // rc_w0
            nw |= (ushort)((c & DTOG_TX) ^ (v & DTOG_TX));                   // toggle
            nw |= (ushort)((c & STAT_TX) ^ (v & STAT_TX));                   // toggle
            ep[n] = nw;
            // When the firmware arms TX VALID, a host bridge would collect the TX buffer
            // (btable[n].tx_addr/tx_count in PMA) and deliver it. Hook point for the
            // host bridge lives in the harness; left as a no-op here until wired.
        }

        // --- host-side injection (used by the harness to drive enumeration/transfers) ---
        // Mark a correct-transfer (CTR) event on an endpoint and raise the USB IRQ, so
        // the firmware's usb_interrupt() services it. dir: true=RX(OUT/SETUP), false=TX.
        public void SignalTransfer(int endpoint, bool rx, bool setup)
        {
            if(rx)  { ep[endpoint] |= CTR_RX; if(setup) { ep[endpoint] |= SETUP; } }
            else    { ep[endpoint] |= CTR_TX; }
            istr = (ushort)((1u << 15) | (rx ? 0x10u : 0u) | (uint)(endpoint & 0xF));
            UpdateIrq();
        }

        public void SignalReset()
        {
            istr |= (1 << 10);
            UpdateIrq();
        }

        private void UpdateIrq()
        {
            // CNTR interrupt-enable bits (CTRM=15, RESETM=10, etc.) gate the IRQ line.
            var pending = (istr & cntr & 0xBF00) != 0 || ((istr & (1 << 15)) != 0 && (cntr & (1 << 15)) != 0);
            IRQ.Set(pending);
        }

        private readonly ushort[] ep = new ushort[8];
        private ushort cntr, istr, fnr, daddr, btable;
        private readonly IMachine machine;
        private readonly long size;

        private const long CNTR = 0x40, ISTR = 0x44, FNR = 0x48, DADDR = 0x4C, BTABLE = 0x50;
        private const ushort CTR_RX = 1 << 15, DTOG_RX = 1 << 14, STAT_RX = 3 << 12, SETUP = 1 << 11;
        private const ushort EP_TYPE = 3 << 9, EP_KIND = 1 << 8;
        private const ushort CTR_TX = 1 << 7, DTOG_TX = 1 << 6, STAT_TX = 3 << 4, EA = 0xF;
    }
}
