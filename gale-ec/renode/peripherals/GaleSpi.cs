//
// gale EC Renode equivalence harness — minimal STM32F0 SPI controller (RM0091 SPI/I2S).
//
// PURPOSE: the stock Renode STM32SPI used for spi2 computes its status register (SR) internally and
// IGNORES writes to the BSY/FTLVL/FRLVL bits, so the firmware's spi_dma_wait() FIFO/BSY busy-wait
// TIMEOUT arms (chip/stm32/spi_master.c:173/187 `if (get_time() > timeout) return EC_ERROR_TIMEOUT`)
// can never be exercised — the SR loop always sees "not busy" and exits before the timeout test runs.
//
// This model is a register-faithful SPI controller with a ForceBusy knob: when ForceBusy is set, SR
// reports BSY|FTLVL|FRLVL so the busy-wait loop spins to its deadline and the timeout arm executes.
// It is registered AT the spi2 address ONLY in the dedicated spi_dma_wait coverage session (the flash
// read path is NOT exercised there, so this model does not bridge to the SPI-flash slave — it only
// needs to drive SR). Default (ForceBusy off): SR = TXE set, BSY clear (the not-busy steady state the
// stock controller presents), so any incidental SR read behaves normally. All other registers are plain
// read/write storage.
//
namespace Antmicro.Renode.Peripherals.Miscellaneous
{
    using Antmicro.Renode.Core;
    using Antmicro.Renode.Peripherals.Bus;

    public class GaleSpi : IDoubleWordPeripheral, IKnownSize
    {
        public GaleSpi(IMachine machine, long size = 0x400)
        {
            this.size = size;
            Reset();
        }

        public long Size => size;

        // spi_dma_wait() has TWO independent busy-wait loops reading different SR fields:
        //   loop 1: while ((sr & FTLVL) || (sr & BSY))   -> first  EC_ERROR_TIMEOUT arm
        //   loop 2: while (sr & FRLVL)                   -> second EC_ERROR_TIMEOUT arm
        // Covering loop 2 (iterate / exit / timeout) needs SR to show FRLVL set WHILE BSY/FTLVL are
        // CLEAR (so loop 1 has already exited). The original single-field model set BSY|FTLVL|FRLVL
        // together and so could never present that state. These knobs model the two phases separately.

        // ForceBusy: SR = BSY|FTLVL forever -> loop 1 spins to its 800ms deadline (first timeout arm).
        public bool ForceBusy { get; set; }
        // ForceFrlvl: SR = FRLVL only (BSY/FTLVL clear) forever -> loop 1 exits immediately, loop 2 spins
        // to its deadline (second timeout arm).
        public bool ForceFrlvl { get; set; }

        // BusyReads: report BSY|FTLVL for the next N SR reads, then clear -> loop 1 iterates a BOUNDED
        // number of times WITHIN the deadline (timeout-compare NOT-taken arm) then exits on FIFO/BSY clear.
        public int BusyReads { get; set; }
        // FrlvlReads: AFTER the BSY/FTLVL phase, report FRLVL for the next N SR reads then clear -> loop 2
        // iterates a bounded number of times then exits on FRLVL clear.
        public int FrlvlReads { get; set; }

        public void Reset()
        {
            for(var i = 0; i < regs.Length; i++)
                regs[i] = 0;
        }

        public uint ReadDoubleWord(long offset)
        {
            if(offset == SR)
            {
                // Phase 1 (BSY/FTLVL): drives loop 1. Bounded reads first, then ForceBusy (infinite).
                if(BusyReads > 0)
                {
                    BusyReads--;
                    return SR_BSY | SR_FTLVL;
                }
                if(ForceBusy)
                    return SR_BSY | SR_FTLVL;
                // Phase 2 (FRLVL only, BSY/FTLVL clear): drives loop 2 once loop 1 has exited.
                if(FrlvlReads > 0)
                {
                    FrlvlReads--;
                    return SR_FRLVL;
                }
                if(ForceFrlvl)
                    return SR_FRLVL;
                return SR_TXE;
            }
            var idx = offset / 4;
            return (idx >= 0 && idx < regs.Length) ? regs[idx] : 0u;
        }

        public void WriteDoubleWord(long offset, uint value)
        {
            var idx = offset / 4;
            if(idx >= 0 && idx < regs.Length)
                regs[idx] = value;
        }

        private readonly uint[] regs = new uint[8];   // CR1/CR2/SR/DR/CRCPR/RXCRCR/TXCRCR/I2SCFGR
        private readonly long size;

        // STM32F0 SPI register offsets
        private const long SR = 0x08;

        // SR bit fields (RM0091 SPI_SR)
        private const uint SR_TXE   = 1u << 1;            // TX buffer empty (steady not-busy state)
        private const uint SR_BSY   = 1u << 7;            // SPI busy
        private const uint SR_FRLVL = 3u << 9;            // RX FIFO level (9:10) nonzero
        private const uint SR_FTLVL = 3u << 11;           // TX FIFO level (11:12) nonzero
    }
}
