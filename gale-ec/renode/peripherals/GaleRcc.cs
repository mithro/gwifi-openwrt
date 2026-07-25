//
// gale EC Renode equivalence harness — STM32F0 RCC (Reset & Clock Control).
//
// A deterministic, RM0091-faithful replacement for Renode's stock "FLIPFLOP"
// RCC stub (which is (a) non-deterministic — it toggles its return value on
// every read — and (b) wrong: it forces RCC_CSR (offset 0x24) to always read 0,
// so the firmware's `LSION -> wait LSIRDY` handshake in system_pre_init can
// never complete and the EC deadlocks at boot).
//
// Modeled behavior (STM32F0x2 reference manual RM0091, RCC chapter):
//   * Each oscillator ENABLE bit drives its READY bit:
//       CR:   HSION(0)->HSIRDY(1), HSEON(16)->HSERDY(17), PLLON(24)->PLLRDY(25)
//       CR2:  HSI14ON(0)->HSI14RDY(1), HSI48ON(16)->HSI48RDY(17)
//       BDCR: LSEON(0)->LSERDY(1)
//       CSR:  LSION(0)->LSIRDY(1)
//     READY bits are read-only and derived (oscillators "lock" instantly in the
//     model — deterministic, which is what trace-equivalence requires).
//   * CFGR: the System-clock-switch status SWS[3:2] mirrors the requested
//     SW[1:0] (the switch completes immediately).
//   * CSR: a fixed, deterministic reset cause (PORRSTF|PINRSTF) is presented;
//     writing RMVF(24) clears the sticky reset flags. Both firmware images see
//     the identical reset cause, so their reset-flag-dependent paths match.
//   * All other registers are plain read/write storage (clock-enable and
//     reset registers, PLL/prescaler config) — read back exactly what was
//     written, the genuine hardware behavior for those fields.
//
namespace Antmicro.Renode.Peripherals.Miscellaneous
{
    using Antmicro.Renode.Core;
    using Antmicro.Renode.Logging;
    using Antmicro.Renode.Peripherals.Bus;

    public class GaleRcc : IDoubleWordPeripheral, IKnownSize
    {
        public GaleRcc(IMachine machine, long size = 0x400)
        {
            this.size = size;
            Reset();
        }

        public long Size => size;

        public void Reset()
        {
            for(var i = 0; i < regs.Length; i++)
            {
                regs[i] = 0;
            }
            regs[CR >> 2]  = 0x00000083; // HSION + HSIRDY + HSITRIM reset (0x10<<3)
            regs[CR2 >> 2] = 0x00000080; // HSI14TRIM reset (0x10<<3)
            // ResetFlags (the CSR reset cause) keeps its property value across Reset so a
            // scenario-set cause survives; default is POR|PIN (cold boot).
        }

        // Settable RCC_CSR reset-cause flags. Default POR|PIN (matches a cold boot). A coverage
        // scenario sets this BEFORE boot to a different cause (software / watchdog / low-power) so
        // system_pre_init's and other reset-flag-dependent branches run for each reset reason.
        public uint ResetFlags { get; set; } = POR_RSTF | PIN_RSTF;

        public uint ReadDoubleWord(long offset)
        {
            var idx = (offset & 0xFF) >> 2;
            if(idx >= regs.Length)
            {
                return 0;
            }
            var v = regs[idx];
            switch(offset & 0xFF)
            {
                case CR:   // HSI/HSE/PLL ready follow their enables
                    v &= ~((1u << 1) | (1u << 17) | (1u << 25));
                    if((v & (1u << 0)) != 0)  v |= (1u << 1);
                    if((v & (1u << 16)) != 0) v |= (1u << 17);
                    if((v & (1u << 24)) != 0) v |= (1u << 25);
                    break;
                case CFGR: // SWS mirrors SW
                    v = (v & ~(3u << 2)) | ((v & 3u) << 2);
                    break;
                case BDCR: // LSE ready follows enable
                    v &= ~(1u << 1);
                    if((v & (1u << 0)) != 0) v |= (1u << 1);
                    break;
                case CSR:  // LSI ready follows enable; present sticky reset cause
                    v &= ~(1u << 1);
                    if((v & (1u << 0)) != 0) v |= (1u << 1);
                    v |= ResetFlags;
                    break;
                case CR2:  // HSI14/HSI48 ready follow enables
                    v &= ~((1u << 1) | (1u << 17));
                    if((v & (1u << 0)) != 0)  v |= (1u << 1);
                    if((v & (1u << 16)) != 0) v |= (1u << 17);
                    break;
            }
            return v;
        }

        public void WriteDoubleWord(long offset, uint value)
        {
            var idx = (offset & 0xFF) >> 2;
            if(idx >= regs.Length)
            {
                return;
            }
            if((offset & 0xFF) == CSR && (value & RMVF) != 0)
            {
                ResetFlags = 0; // RMVF clears the sticky reset cause
            }
            // READY bits are read-only; store enables/config verbatim (derived on read).
            regs[idx] = value;
        }

        private uint[] regs = new uint[0x40]; // 0x100 bytes of register space (covers 0x00..0x34)
        private readonly long size;

        // Register offsets (RM0091)
        private const long CR   = 0x00;
        private const long CFGR = 0x04;
        private const long BDCR = 0x20;
        private const long CSR  = 0x24;
        private const long CR2  = 0x34;

        // CSR reset-cause flags
        private const uint POR_RSTF = 1u << 27;
        private const uint PIN_RSTF = 1u << 26;
        private const uint RMVF     = 1u << 24;
    }
}
