//
// gale EC Renode equivalence harness — STM32F0 DMA1 controller.
//
// Renode's stock STM32F072 platform models DMA as a Python stub that writes a
// magic constant to the channel peripheral-address register and throws
// ("name 'sysbus' is not defined") the moment a channel is programmed — which
// aborts emulation as soon as the firmware starts DMA-driven UART console TX.
//
// This is a real STM32F0 DMA1 model (RM0091 "DMA controller"): on the CCR.EN
// rising edge it performs the configured memory<->peripheral (or memory-to-
// memory) block transfer immediately and deterministically, drains CNDTR to 0,
// and latches the per-channel Transfer-Complete flag (TCIF) + Global flag (GIF)
// in ISR. The EC's dma.c detects completion by polling CNDTR (dma_bytes_done)
// and ISR.TCIF (dma_wait), so an instantaneous, deterministic transfer matches
// the firmware's expectations exactly and makes the UART console output (and any
// other DMA path, e.g. SPI) observable for trace comparison.
//
// Registers (DMA1 base 0x40020000):
//   ISR  0x00 (RO flags), IFCR 0x04 (W1C), then per channel c=1..7:
//   CCR  0x08+0x14*(c-1), CNDTR +0x04, CPAR +0x08, CMAR +0x0C
//
namespace Antmicro.Renode.Peripherals.Miscellaneous
{
    using Antmicro.Renode.Core;
    using Antmicro.Renode.Logging;
    using Antmicro.Renode.Peripherals.Bus;

    public class GaleDma : IDoubleWordPeripheral, IKnownSize
    {
        public GaleDma(IMachine machine, long size = 0x400)
        {
            this.size = size;
            this.sysbus = machine.GetSystemBus(this);
            Reset();
        }

        public long Size => size;

        public void Reset()
        {
            isr = 0;
            for(var c = 1; c <= NumChannels; c++)
            {
                ccr[c] = cndtr[c] = cpar[c] = cmar[c] = 0;
            }
        }

        public uint ReadDoubleWord(long offset)
        {
            if(offset == ISR)  { return isr; }
            if(offset == IFCR) { return 0; }
            if(!Decode(offset, out var c, out var reg)) { return 0; }
            switch(reg)
            {
                case 0x0: return ccr[c];
                case 0x4: return cndtr[c];
                case 0x8: return cpar[c];
                case 0xC: return cmar[c];
            }
            return 0;
        }

        public void WriteDoubleWord(long offset, uint value)
        {
            if(offset == ISR)  { return; }           // ISR is read-only
            if(offset == IFCR) { isr &= ~value; return; } // write-1-to-clear
            if(!Decode(offset, out var c, out var reg)) { return; }
            switch(reg)
            {
                case 0x0:
                    var wasEnabled = (ccr[c] & CCR_EN) != 0;
                    ccr[c] = value;
                    if(!wasEnabled && (value & CCR_EN) != 0)
                    {
                        Transfer(c); // EN rising edge -> run the block transfer
                    }
                    break;
                case 0x4: cndtr[c] = value & 0xFFFF; break;
                case 0x8: cpar[c] = value; break;
                case 0xC: cmar[c] = value; break;
            }
        }

        private void Transfer(int c)
        {
            var n = cndtr[c];
            var control = ccr[c];
            var mem2mem = (control & CCR_MEM2MEM) != 0;
            var dirMemToPeriph = (control & CCR_DIR) != 0; // read from memory
            var minc = (control & CCR_MINC) != 0;
            var pinc = (control & CCR_PINC) != 0;
            var msize = ElemSize((control >> 10) & 0x3);
            var psize = ElemSize((control >> 8) & 0x3);
            var ma = cmar[c];
            var pa = cpar[c];

            for(uint i = 0; i < n; i++)
            {
                if(mem2mem)
                {
                    // CPAR is the source, CMAR the destination (per RM0091 mem2mem)
                    WriteElem(ma, msize, ReadElem(pa, psize));
                    if(pinc) { pa += (uint)psize; }
                    if(minc) { ma += (uint)msize; }
                }
                else if(dirMemToPeriph)
                {
                    WriteElem(pa, psize, ReadElem(ma, msize));
                    if(minc) { ma += (uint)msize; }
                    if(pinc) { pa += (uint)psize; }
                }
                else // peripheral -> memory
                {
                    WriteElem(ma, msize, ReadElem(pa, psize));
                    if(pinc) { pa += (uint)psize; }
                    if(minc) { ma += (uint)msize; }
                }
            }

            cmar[c] = ma;
            cpar[c] = pa;
            cndtr[c] = 0;                  // transfer complete
            var shift = (c - 1) * 4;       // per-channel ISR field
            isr |= (TCIF | GIF) << shift;  // latch Transfer-Complete + Global flags
        }

        private uint ReadElem(uint addr, int sizeBytes)
        {
            switch(sizeBytes)
            {
                case 1: return sysbus.ReadByte(addr);
                case 2: return sysbus.ReadWord(addr);
                default: return sysbus.ReadDoubleWord(addr);
            }
        }

        private void WriteElem(uint addr, int sizeBytes, uint value)
        {
            switch(sizeBytes)
            {
                case 1: sysbus.WriteByte(addr, (byte)value); break;
                case 2: sysbus.WriteWord(addr, (ushort)value); break;
                default: sysbus.WriteDoubleWord(addr, value); break;
            }
        }

        private static int ElemSize(uint code)
        {
            return code == 1 ? 2 : (code == 2 ? 4 : 1);
        }

        private bool Decode(long offset, out int channel, out long reg)
        {
            channel = 0;
            reg = 0;
            if(offset < 0x08) { return false; }
            var rel = offset - 0x08;
            channel = (int)(rel / 0x14) + 1;
            reg = rel % 0x14;
            return channel >= 1 && channel <= NumChannels && (reg == 0 || reg == 4 || reg == 8 || reg == 0xC);
        }

        private uint isr;
        private readonly uint[] ccr = new uint[NumChannels + 1];
        private readonly uint[] cndtr = new uint[NumChannels + 1];
        private readonly uint[] cpar = new uint[NumChannels + 1];
        private readonly uint[] cmar = new uint[NumChannels + 1];
        private readonly IBusController sysbus;
        private readonly long size;

        private const int NumChannels = 7;
        private const long ISR  = 0x00;
        private const long IFCR = 0x04;

        private const uint CCR_EN      = 1u << 0;
        private const uint CCR_DIR     = 1u << 4;
        private const uint CCR_PINC    = 1u << 6;
        private const uint CCR_MINC    = 1u << 7;
        private const uint CCR_MEM2MEM = 1u << 14;
        private const uint GIF  = 1u << 0; // global flag (per channel, before shift)
        private const uint TCIF = 1u << 1; // transfer-complete flag (per channel)
    }
}
