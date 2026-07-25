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
            IrqCh1 = new GPIO();      // DMA1 channel 1   -> NVIC IRQ 9
            IrqCh23 = new GPIO();     // DMA1 channels 2,3 -> NVIC IRQ 10
            IrqCh47 = new GPIO();     // DMA1 channels 4-7 -> NVIC IRQ 11
            Reset();
        }

        public long Size => size;

        // Per-IRQ-line DMA transfer-complete interrupt outputs (RM0091): a channel with CCR.TCIE set
        // asserts its NVIC line when its TCIF latches. The model was originally polling-only (dma_wait
        // polls CNDTR/TCIF); this models the real TC-interrupt path so dma_event_interrupt_channel_* run.
        public GPIO IrqCh1 { get; }
        public GPIO IrqCh23 { get; }
        public GPIO IrqCh47 { get; }
        // Opt-in (default off): fire the DMA TC interrupt on completion. Off = original polling behavior
        // (existing coverage/equivalence runs unaffected); a lever sets it true to exercise the DMA ISR.
        public bool DmaTcIrqEnabled { get; set; }

        // Opt-in (default off): ISR reads report TCIF set for ALL channels, so dma_wait()
        // (which polls ISR & TCIF(channel)) returns success immediately. A coverage lever sets this so
        // a direct-called spi_dma_wait gets past dma_wait() and into the SR busy-wait loop (paired with
        // GaleSpi ForceBusy). Additive: default off leaves the real polling/transfer behavior unchanged.
        public bool ForceAllTcif { get; set; }
        private const uint ALL_TCIF = 0x02222222u;   // TCIF (bit 1) of each channel nibble, channels 1-7

        // Recompute the three DMA IRQ lines from the latched TCIF flags gated by each channel's TCIE.
        private void UpdateDmaIrqs()
        {
            if(!DmaTcIrqEnabled) { IrqCh1.Set(false); IrqCh23.Set(false); IrqCh47.Set(false); return; }
            System.Func<int, bool> pend = ch => (isr & (TCIF << ((ch - 1) * 4))) != 0 && (ccr[ch] & CCR_TCIE) != 0;
            IrqCh1.Set(pend(1));
            IrqCh23.Set(pend(2) || pend(3));
            IrqCh47.Set(pend(4) || pend(5) || pend(6) || pend(7));
        }

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

        public void ClearResponses() { pdQueue.Clear(); pendingGoodCrc = false; nextIsContract = false; goodCrcCounter = 0; lastTx.Clear(); replyQueue.Clear(); reactedCount = 0; replyMsgId = 0; vdmReplyIdx = 0; }
        public void ClearTx() { lastTx.Clear(); reactedCount = 0; }

        // Force-deliver the next staged PD message into the CURRENTLY-ARMED TIM1_CCR1 RX channel's
        // buffer + set CNDTR, independent of the DMA-arm event. Needed for SNK_DISCOVERY where gale
        // arms RX ONCE at state-entry then waits (no re-arm), so the normal arm-time delivery never
        // fires for a later-staged Source_Cap. The harness calls this AFTER StageResponse while gale's
        // RX is armed, then FireComps so gale's pd_dequeue_bits sees dma_bytes_done>0 and decodes.
        // Returns 1 if delivered, 0 if no armed RX channel / nothing staged (readable for diagnostics).
        public uint DeliverRx()
        {
            for(int c = 1; c <= NumChannels; c++)
            {
                if(cpar[c] == TIM1_CCR1 && (ccr[c] & CCR_EN) != 0)
                {
                    byte[] resp = null;
                    if(nextIsContract && pdQueue.Count > 0) { resp = pdQueue.Dequeue(); nextIsContract = false; }
                    else if(replyQueue.Count > 0) { resp = replyQueue.Dequeue(); }
                    else if(pdQueue.Count > 0) { resp = pdQueue.Dequeue(); }
                    if(resp != null)
                    {
                        var ma = cmar[c]; var n = cndtr[c];
                        for(var i = 0; i < resp.Length; i++) { sysbus.WriteByte(ma + (uint)i, resp[i]); }
                        cndtr[c] = (uint)(n > resp.Length ? n - resp.Length : 0);
                        return 1;
                    }
                    return 0;
                }
            }
            return 0;
        }

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
        // opt-in GoodCRC-timeout fault: when true, gale's TX never gets its ACK -> pd_send error path.
        public bool SuppressGoodCrc { get; set; }
        public void ExpectContractMsg() { nextIsContract = true; }

        // Reactive-PD-partner groundwork: gale's last PD TX (the raw CC-line level bytes clocked
        // out over SPI1) captured during the mem->SPI1_DR transfer. DumpTx writes it hex to a file
        // so the harness can decode the message type and (eventually) inject the correct reply.
        public void DumpTx(string path)
        {
            var sb = new System.Text.StringBuilder();
            foreach(var b in lastTx) { sb.Append(b.ToString("x2")); }
            System.IO.File.WriteAllText(path, sb.ToString());
        }

        // ---- REACTIVE PD PARTNER -------------------------------------------------------------
        // Decode gale's PD TX (lastTx level stream, inverse of pd_encode — see pd_decode.py) and,
        // for a request that needs a partner reply (Soft_Reset / DR_Swap / PR_Swap / VCONN_Swap /
        // Get_Sink_Cap), queue a pre-staged encoded reply so the handshake completes and pd_task
        // advances through its swap/reset states. Replies are delivered on the pd_rx_start AFTER
        // the auto-GoodCRC. The harness pre-stages encoded replies via SetReply(slot, hex):
        //   slot 0..7 = Accept with partner msg_id 0..7 ; slot 8 = Sink_Cap.
        public void SetReply(int slot, string hex) { replyBank[slot & 0xF] = Unhex(hex); }
        public bool ReactiveEnabled { get; set; }
        public bool RxPollDeliver { get; set; }   // opt-in: deliver staged RX msg on CNDTR poll (DISCOVERY)
        public int LastTxType { get; private set; } = -1;   // for test/inspection

        private void BuildPdTables()
        {
            if(revBmc != null) { return; }
            revBmc = new System.Collections.Generic.Dictionary<int, int>();
            for(var x = 0; x < 32; x++) { revBmc[Bmc(x)] = x; }
            dec4b5b = new System.Collections.Generic.Dictionary<int, int>();
            int[] enc = { 0x1E, 0x09, 0x14, 0x15, 0x0A, 0x0B, 0x0E, 0x0F,
                          0x12, 0x13, 0x16, 0x17, 0x1A, 0x1B, 0x1C, 0x1D };
            for(var n = 0; n < 16; n++) { dec4b5b[enc[n]] = n; }
        }

        private static int Bmc(int x)
        {
            return ((x & 1)  != 0 ? 0x001 : 0x3FF)
                 ^ ((x & 2)  != 0 ? 0x004 : 0x3FC)
                 ^ ((x & 4)  != 0 ? 0x010 : 0x3F0)
                 ^ ((x & 8)  != 0 ? 0x040 : 0x3C0)
                 ^ ((x & 16) != 0 ? 0x100 : 0x300);
        }

        // Decode the header of the PD message whose SOP starts at half-UI offset `start`; -1 if none.
        private int DecodeHeaderAt(System.Collections.Generic.List<int> levels, int start)
        {
            int off = start, bt = 0x3FF;
            var syms = new int[8];
            for(var s = 0; s < 8; s++)
            {
                if(off + 10 > levels.Count) { return -1; }
                int em = 0;
                for(var k = 0; k < 10; k++) { em |= levels[off + k] << k; }
                if(!revBmc.TryGetValue(em ^ bt, out var sym)) { return -1; }
                syms[s] = sym;
                bt = (em & 0x200) != 0 ? 0x3FF : 0;
                off += 10;
            }
            if(syms[0] != 0x18 || syms[1] != 0x18 || syms[2] != 0x18 || syms[3] != 0x11) { return -1; }
            int hdr = 0;
            for(var j = 0; j < 4; j++)
            {
                if(!dec4b5b.TryGetValue(syms[4 + j], out var nib)) { return -1; }
                hdr |= nib << (4 * j);
            }
            return hdr;
        }

        // Count complete PD messages in lastTx and return the header of the newest one (-1 none).
        private int DecodeNewestTx(out int count)
        {
            BuildPdTables();
            var levels = new System.Collections.Generic.List<int>(lastTx.Count * 8);
            foreach(var b in lastTx) { for(var k = 0; k < 8; k++) { levels.Add((b >> k) & 1); } }
            count = 0;
            int newest = -1, i = 0;
            while(i < levels.Count - 60)
            {
                int hdr = DecodeHeaderAt(levels, i);
                if(hdr >= 0) { newest = hdr; count++; i += 200; } else { i++; }
            }
            return newest;
        }

        private void ReactToTx()
        {
            if(!ReactiveEnabled) { return; }
            int hdr = DecodeNewestTx(out var count);
            if(hdr < 0 || count <= reactedCount) { return; }   // only react to a newly-completed msg
            reactedCount = count;
            int type = hdr & 0x1f, cnt = (hdr >> 12) & 7;
            LastTxType = cnt != 0 ? (0x100 | type) : type;
            byte[] reply = null;
            if(cnt == 0 && (type == 13 || type == 9 || type == 10 || type == 11))
            {
                reply = replyBank[replyMsgId & 7];             // Soft_Reset/DR/PR/VCONN_Swap -> Accept
                replyMsgId++;
            }
            else if(cnt == 0 && type == 8)
            {
                reply = replyBank[8];                          // Get_Sink_Cap -> Sink_Cap
            }
            else if(cnt >= 1 && type == 15)
            {
                // gale sent a VDM (DFP query): deliver staged ACKs from slots 9..12 in sequence so
                // its DFP VDM state machine walks Disc-Identity -> SVIDs -> Modes -> Enter.
                reply = replyBank[9 + (vdmReplyIdx & 3)];
                vdmReplyIdx++;
            }
            if(reply != null) { replyQueue.Enqueue(reply); }
        }

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
            if(offset == ISR)  { return isr | (ForceAllTcif ? ALL_TCIF : 0u); }
            if(offset == IFCR) { return 0; }
            if(!Decode(offset, out var c, out var reg)) { return 0; }
            switch(reg)
            {
                case 0x0: return ccr[c];
                case 0x4:
                    // Opt-in deliver-on-poll: in SNK_DISCOVERY gale arms the RX DMA ONCE (one EN-rising
                    // edge, before the harness stages a msg) then busy-waits polling CNDTR, so the normal
                    // arm-time Transfer never delivers a later-staged Source_Cap. When RxPollDeliver is on,
                    // deliver the next staged msg into the armed TIM1_CCR1 channel the first time gale polls
                    // its CNDTR, so dma_bytes_done becomes >0 and the decode runs. Default off (other
                    // scenarios + equivalence runs unaffected).
                    if(RxPollDeliver && cpar[c] == TIM1_CCR1 && (ccr[c] & CCR_EN) != 0)
                    {
                        byte[] resp = null;
                        if(nextIsContract && pdQueue.Count > 0) { resp = pdQueue.Dequeue(); nextIsContract = false; }
                        else if(replyQueue.Count > 0) { resp = replyQueue.Dequeue(); }
                        else if(pdQueue.Count > 0) { resp = pdQueue.Dequeue(); }
                        if(resp != null)
                        {
                            var ma = cmar[c]; var n = cndtr[c];
                            for(var i = 0; i < resp.Length; i++) { sysbus.WriteByte(ma + (uint)i, resp[i]); }
                            cndtr[c] = (uint)(n > resp.Length ? n - resp.Length : 0);
                        }
                    }
                    return cndtr[c];
                case 0x8: return cpar[c];
                case 0xC: return cmar[c];
            }
            return 0;
        }

        public void WriteDoubleWord(long offset, uint value)
        {
            if(offset == ISR)  { return; }           // ISR is read-only
            if(offset == IFCR) { isr &= ~value; UpdateDmaIrqs(); return; } // write-1-to-clear (+ deassert IRQ)
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
                else if(SuppressGoodCrc && pendingGoodCrc)
                {
                    // Model a GoodCRC TIMEOUT: the partner fails to ACK gale's TX, so deliver NOTHING.
                    // gale's send_validate_message exhausts PD_RETRY_COUNT and pd_send returns error —
                    // the only way to reach the send-failure branches (genuine protocol fault, opt-in).
                    pendingGoodCrc = false;
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
                else if(replyQueue.Count > 0)
                {
                    resp = replyQueue.Dequeue();   // reactive partner reply (Accept/PS_RDY/Sink_Cap)
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
                if(pa == SPI1_DR) { pendingGoodCrc = true; }   // accumulate TX bytes (cleared via ClearTx)
                RxPend rx = pendingRx.ContainsKey(pa) ? pendingRx[pa] : null;
                for(uint i = 0; i < n; i++)
                {
                    var txw = ReadElem(ma, msize);
                    sysbus.WriteDoubleWord(pa, txw);                 // clock out one TX byte
                    if(pa == SPI1_DR)                                // capture gale's PD TX (CC line samples)
                    {
                        for(var k = 0; k < msize; k++) { lastTx.Add((byte)((txw >> (8 * k)) & 0xFF)); }
                    }
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
                if(pa == SPI1_DR) { ReactToTx(); }   // decode gale's PD TX -> queue a reactive reply
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
            UpdateDmaIrqs();                     // assert the NVIC DMA IRQ if this channel has TCIE set
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
        private readonly byte[][] replyBank = new byte[16][];
        private readonly System.Collections.Generic.Queue<byte[]> replyQueue =
            new System.Collections.Generic.Queue<byte[]>();
        private readonly System.Collections.Generic.List<byte> lastTx =
            new System.Collections.Generic.List<byte>();
        private System.Collections.Generic.Dictionary<int, int> revBmc;
        private System.Collections.Generic.Dictionary<int, int> dec4b5b;
        private int reactedCount;
        private int replyMsgId;
        private int vdmReplyIdx;
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
        private const uint CCR_TCIE    = 1u << 1; // transfer-complete interrupt enable
        private const uint CCR_DIR     = 1u << 4;
        private const uint CCR_PINC    = 1u << 6;
        private const uint CCR_MINC    = 1u << 7;
        private const uint CCR_MEM2MEM = 1u << 14;
        private const uint GIF  = 1u << 0; // global flag (per channel, before shift)
        private const uint TCIF = 1u << 1; // transfer-complete flag (per channel)
    }
}
