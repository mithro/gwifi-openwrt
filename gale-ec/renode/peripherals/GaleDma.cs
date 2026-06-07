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
// the firmware's expectations for the UART console TX path (mem->periph, one-
// directional) and makes console output observable for trace comparison.
//
// One-directional DMA (UART TX) runs as an instant block transfer on the CCR.EN
// edge. Full-duplex SPI is handled specially (see Transfer): an RX channel that
// targets an SPI DR is deferred, and the paired TX channel clocks each byte out and
// captures the simultaneous slave response into the RX buffer — so the raiden
// SPI-flash readback works end-to-end (ef4017).
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

        // USB-PD RX capture: number of TIM1-input-capture sample bytes the CC partner has
        // pre-staged into the channel's memory buffer (pd_phy.raw_samples). When the firmware
        // arms the TIM1-CCR1 source channel (pd_rx_start), this model reports these bytes as
        // captured WITHOUT overwriting the buffer (the staged samples ARE the captured CC
        // waveform), so dma_bytes_done() returns this count. 0 disables the special case.
        public uint TimRxSampleCount { get; set; }

        // USB-PD CC-partner RESPONSE QUEUE (for a live explicit contract). Each StageResponse
        // enqueues one encoded PD message (hex sample bytes). Every time the firmware arms the
        // TIM1-CCR1 RX DMA (pd_rx_start) — whether the synchronous GoodCRC wait after its own TX
        // or after a COMP-IRQ wake — this model dequeues the next response, writes it into the
        // capture buffer (raw_samples) and sets CNDTR so dma_bytes_done() reports it. This lets a
        // full SNK contract run (Source_Caps -> GoodCRC -> Accept -> PS_RDY) with no monitor
        // timing: the queue auto-advances on each arm, the harness only FireComps to wake the
        // task at its async waits. Empty queue -> falls back to the TimRxSampleCount behaviour.
        public void StageResponse(string hex)
        {
            pdQueue.Enqueue(Unhex(hex));
        }

        public void ClearResponses() { pdQueue.Clear(); pendingGoodCrc = false; nextIsContract = false; goodCrcCounter = 0; }

        // CONTEXT-AWARE PD CC-PARTNER (for a live explicit contract). Two delivery contexts are
        // distinguished so the FIFO never desyncs against gale's pd_rx_start pattern:
        //  * A pop is a CONTRACT message (Source_Caps/Accept/PS_RDY) when the harness armed it
        //    via ExpectContractMsg() right before FireComp (a message gale was asleep waiting for).
        //  * Otherwise the pop is the synchronous GoodCRC wait inside send_validate_message right
        //    after gale's own PD TX (detected as an SPI1 mem->DR transfer): deliver a GoodCRC whose
        //    msg_id matches gale's current protocol msg_id (read from RAM), from a pre-staged bank.
        // GoodCRcMsgIdAddress = &pd_protocol[0].msg_id (image-specific; 0 disables auto-GoodCRC).
        public uint GoodCrcMsgIdAddress { get; set; }
        public void SetGoodCrc(int id, string hex) { goodCrcBank[id & 7] = Unhex(hex); }
        public void ExpectContractMsg() { nextIsContract = true; }

        private static byte[] Unhex(string hex)
        {
            var b = new byte[hex.Length / 2];
            for(var i = 0; i < b.Length; i++)
            {
                b[i] = System.Convert.ToByte(hex.Substring(i * 2, 2), 16);
            }
            return b;
        }

        public void Reset()
        {
            isr = 0;
            for(var c = 1; c <= NumChannels; c++)
            {
                ccr[c] = cndtr[c] = cpar[c] = cmar[c] = 0;
            }
            pendingRx.Clear();
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

            // --- USB-PD TIM1 input-capture RX special case ------------------------
            // pd_rx_start() arms a periph->mem channel sourcing TIM1_CCR1 to capture the CC
            // edge timestamps. There is no analog comparator; the CC partner has pre-staged
            // the encoded sample bytes into the destination buffer (raw_samples). Report
            // TimRxSampleCount bytes as captured by leaving CNDTR = n - count (so
            // dma_bytes_done() = count) and DO NOT overwrite the buffer.
            if(!mem2mem && !dirMemToPeriph && pa == TIM1_CCR1)
            {
                // Context-aware delivery: a harness-armed contract message, else (after gale's
                // own PD TX) the GoodCRC gale is synchronously waiting for, else a queued response.
                byte[] resp = null;
                if(nextIsContract && pdQueue.Count > 0)
                {
                    resp = pdQueue.Dequeue();
                    nextIsContract = false;
                }
                else if(pendingGoodCrc && goodCrcBank[0] != null)
                {
                    // The EC's msg_id increments per validated TX, so the partner's GoodCRC ids
                    // run 0,1,2,... in TX order — a delivery counter matches without reading RAM
                    // (address-independent; works on both the captured and rebuilt firmwares).
                    var id = GoodCrcMsgIdAddress != 0 ? (sysbus.ReadByte(GoodCrcMsgIdAddress) & 7)
                                                      : (goodCrcCounter++ & 7);
                    resp = goodCrcBank[id];
                    pendingGoodCrc = false;
                }
                else if(pdQueue.Count > 0)
                {
                    resp = pdQueue.Dequeue();
                }
                if(resp != null)
                {
                    for(var i = 0; i < resp.Length; i++) { sysbus.WriteByte(ma + (uint)i, resp[i]); }
                    cndtr[c] = (uint)(n > resp.Length ? n - resp.Length : 0);
                    return;
                }
                if(TimRxSampleCount != 0)
                {
                    cndtr[c] = n > TimRxSampleCount ? n - TimRxSampleCount : 0;
                    return; // leave staged samples intact; no TCIF (firmware polls CNDTR)
                }
            }

            // --- Full-duplex SPI DMA special case ---------------------------------
            // gale's SPI master pairs a TX channel (mem->SPI_DR) with an RX channel
            // (SPI_DR->mem); each clocked byte produces one response byte. The generic
            // instant per-channel model would drain RX before TX ever clocks the bus.
            // Defer an RX channel that targets an SPI DR; when the paired TX channel
            // runs, clock each TX byte out, read back the slave response, and deposit it
            // into the deferred RX buffer — then complete BOTH channels together.
            if(!mem2mem && !dirMemToPeriph && IsSpiDr(pa))
            {
                pendingRx[pa] = new RxPend { Ch = c, Ma = ma, N = n, Minc = minc, Msize = msize };
                return; // completed by the paired TX transfer (do NOT latch TCIF yet)
            }
            if(dirMemToPeriph && IsSpiDr(pa))
            {
                // gale's USB-PD TX bit-bangs the CC line via SPI1 (DMAC_SPI_TX = ch3 -> SPI1_DR).
                // A TX is immediately followed (in send_validate_message) by a synchronous GoodCRC
                // wait, so arm the auto-GoodCRC for the next TIM1-CCR1 RX pop.
                if(pa == SPI1_DR) { pendingGoodCrc = true; }
                RxPend rx = pendingRx.ContainsKey(pa) ? pendingRx[pa] : null;
                for(uint i = 0; i < n; i++)
                {
                    sysbus.WriteDoubleWord(pa, ReadElem(ma, msize)); // clock out one TX byte
                    var resp = sysbus.ReadDoubleWord(pa);            // simultaneous slave response
                    if(minc) { ma += (uint)msize; }
                    if(rx != null && i < rx.N)
                    {
                        WriteElem(rx.Ma, rx.Msize, resp);
                        if(rx.Minc) { rx.Ma += (uint)rx.Msize; }
                    }
                }
                Complete(c, ma, pa);
                if(rx != null)
                {
                    cmar[rx.Ch] = rx.Ma;
                    Complete(rx.Ch, rx.Ma, cpar[rx.Ch]);
                    pendingRx.Remove(pa);
                }
                return;
            }

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
            Complete(c, ma, pa);
        }

        private void Complete(int c, uint ma, uint pa)
        {
            cmar[c] = ma;
            cpar[c] = pa;
            cndtr[c] = 0;                       // transfer complete
            isr |= (TCIF | GIF) << ((c - 1) * 4); // latch Transfer-Complete + Global flags
        }

        private static bool IsSpiDr(uint addr)
        {
            return addr == SPI1_DR || addr == SPI2_DR;
        }

        private class RxPend
        {
            public int Ch;
            public uint Ma;
            public uint N;
            public bool Minc;
            public int Msize;
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
        private readonly System.Collections.Generic.Dictionary<uint, RxPend> pendingRx =
            new System.Collections.Generic.Dictionary<uint, RxPend>();
        private readonly System.Collections.Generic.Queue<byte[]> pdQueue =
            new System.Collections.Generic.Queue<byte[]>();
        private readonly byte[][] goodCrcBank = new byte[8][];
        private bool pendingGoodCrc;
        private bool nextIsContract;
        private int goodCrcCounter;
        private readonly IBusController sysbus;
        private readonly long size;

        private const int NumChannels = 7;
        private const uint SPI1_DR = 0x4001300C; // SPI1 base 0x40013000 + DR 0x0C
        private const uint SPI2_DR = 0x4000380C; // SPI2 base 0x40003800 + DR 0x0C
        private const uint TIM1_CCR1 = 0x40012C34; // TIM1 base 0x40012C00 + CCR1 0x34 (PD RX)
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
