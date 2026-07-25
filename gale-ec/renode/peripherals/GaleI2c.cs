//
// gale EC Renode equivalence harness — STM32F0 I2C1 slave with an AP host-command injector.
//
// The device firmware (v1.1.5337) talks to the AP over the I2C slave for HOST COMMANDS:
// it programs STM32_I2C_OAR1 = 0x803C (own-address 0x3C enabled) + CR1 = 0xBD (PE + slave
// interrupts). The reconstruction had dropped CONFIG_HOSTCMD_I2C_SLAVE_ADDR, so the transport
// was GC'd; it is now restored to match the device. This model emulates the AP master writing
// a host-command packet (then reading the response) so the firmware's i2c_event_handler ->
// i2c_process_command -> host_packet_receive -> host_command_process -> hc_* handlers run.
//
// HostCmd(hex) scripts the STM32F0 slave-receive interrupt sequence (RM0091 "I2C"): ADDR(write)
// -> RXNE per command byte -> ADDR(read, repeated start) -> TXIS (read turnaround, where the
// firmware processes the command), driving the real ISR via IRQ -> nvic@23. The model only
// presents register state + the IRQ; the firmware does all the work. Default-idle: with no
// HostCmd in flight it behaves as a plain register store (so firmware init / equivalence runs
// are unaffected; this peripheral isn't otherwise exercised).
//
namespace Antmicro.Renode.Peripherals.Miscellaneous
{
    using System.Collections.Generic;
    using Antmicro.Renode.Core;
    using Antmicro.Renode.Logging;
    using Antmicro.Renode.Peripherals.Bus;

    public class GaleI2c : IDoubleWordPeripheral, IKnownSize
    {
        public GaleI2c(IMachine machine, long size = 0x400)
        {
            this.size = size;
            IRQ = new GPIO();
            Reset();
        }

        public long Size => size;
        public GPIO IRQ { get; }

        public void Reset()
        {
            cr1 = oar1 = oar2 = cr2 = timingr = 0;
            script.Clear();
            step = -1;
            rxByte = 0;
            IRQ.Unset();
        }

        // Emulate the AP sending a host-command packet (then reading the response). `hex` is the
        // raw I2C write payload: [EC_COMMAND_PROTOCOL_3=0xda][struct ec_host_request][params...].
        public void HostCmd(string hex)
        {
            var data = new byte[hex.Length / 2];
            for(var i = 0; i < data.Length; i++)
            {
                data[i] = System.Convert.ToByte(hex.Substring(i * 2, 2), 16);
            }
            script.Clear();
            // opt-in bus-error step (ARLO/BERR handler arm, i2c-stm32f0.c:287) before the transaction
            if(InjectBusErr) { script.Add(new Step { Isr = ARLO | BERR }); }
            script.Add(new Step { Isr = ADDR | ADDR_CODE });               // addressed for write
            foreach(var b in data) { script.Add(new Step { Isr = RXNE, Data = b }); }
            script.Add(new Step { Isr = ADDR | ADDR_CODE | DIR });         // repeated start, read
            // several TXIS steps so the response-TX loop (tx_index < tx_end) iterates, not just one byte
            for(var t = 0; t < 6; t++) { script.Add(new Step { Isr = TXIS }); }
            // opt-in master-NACK of a response byte (NACK handler arm, i2c-stm32f0.c:350)
            if(InjectNack) { script.Add(new Step { Isr = NACKF }); }
            script.Add(new Step { Isr = STOP });                          // stop condition
            step = 0;
            IRQ.Set(true);                                                // level-held: ISR re-runs per step
        }

        // The AP addressing gale AS A TCPC (CONFIG_USB_PD_TCPC: OAR2 = 0x9c). ADDCODE = 0x9c so the ISR's
        // ADDR_IS_TCPC(addr) arms run: a WRITE (set register offset) then STOP while rx_pending is the
        // "write-only to set offset" path (i2c-stm32f0.c:329); a WRITE+repeated-READ is a register read
        // (:389). `read`=false -> offset-write+STOP; true -> offset-write then read-back.
        public void TcpcCmd(string hex, bool read)
        {
            var data = new byte[hex.Length / 2];
            for(var i = 0; i < data.Length; i++)
            {
                data[i] = System.Convert.ToByte(hex.Substring(i * 2, 2), 16);
            }
            script.Clear();
            script.Add(new Step { Isr = ADDR | TCPC_CODE });               // addressed (write) as TCPC
            foreach(var b in data) { script.Add(new Step { Isr = RXNE, Data = b }); }
            if(read)
            {
                script.Add(new Step { Isr = ADDR | TCPC_CODE | DIR });      // repeated start, read register
                for(var t = 0; t < 4; t++) { script.Add(new Step { Isr = TXIS }); }
            }
            script.Add(new Step { Isr = STOP });                           // STOP (rx_pending + TCPC addr -> :329)
            step = 0;
            IRQ.Set(true);
        }

        // opt-in I2C-slave fault injection (default off): bus error (ARLO|BERR) / master NACK steps.
        public bool InjectBusErr { get; set; }
        public bool InjectNack { get; set; }

        public uint ReadDoubleWord(long offset)
        {
            switch(offset)
            {
                case CR1:   return cr1;
                case CR2:   return cr2;
                case OAR1:  return oar1;
                case OAR2:  return oar2;
                case TIMINGR: return timingr;
                case ISR:   return CurIsr() | ISR_TXE;   // TXE idle-high
                case RXDR:
                    // Firmware's RXNE handler read this byte into host_buffer -> advance.
                    var b = rxByte;
                    if(InScript() && (script[step].Isr & RXNE) != 0) { Advance(); }
                    return b;
                default:    return 0;
            }
        }

        public void WriteDoubleWord(long offset, uint value)
        {
            switch(offset)
            {
                case CR1:   cr1 = value; break;
                case CR2:   cr2 = value; break;
                case OAR1:  oar1 = value; break;
                case OAR2:  oar2 = value; break;
                case TIMINGR: timingr = value; break;
                case ICR:
                    // Clearing ADDRCF acknowledges an ADDR step -> advance.
                    if((value & ICR_ADDRCF) != 0 && InScript() && (script[step].Isr & ADDR) != 0)
                    {
                        Advance();
                    }
                    // Clearing STOPCF ends the STOP step.
                    if((value & ICR_STOPCF) != 0 && InScript() && (script[step].Isr & STOP) != 0)
                    {
                        Advance();
                    }
                    // Clearing the error/NACK flags acknowledges an injected error/NACK step -> advance.
                    if((value & (ICR_BERRCF | ICR_ARLOCF)) != 0 && InScript() && (script[step].Isr & (BERR | ARLO)) != 0)
                    {
                        Advance();
                    }
                    if((value & ICR_NACKCF) != 0 && InScript() && (script[step].Isr & NACKF) != 0)
                    {
                        Advance();
                    }
                    break;
                case TXDR:
                    // Firmware wrote a response byte during/after TXIS -> turnaround handled, advance.
                    if(InScript() && (script[step].Isr & TXIS) != 0) { Advance(); }
                    break;
            }
        }

        private uint CurIsr()
        {
            if(!InScript()) { return 0; }
            var s = script[step];
            if((s.Isr & RXNE) != 0) { rxByte = s.Data; }   // present the byte for the RXNE read
            return s.Isr;
        }

        // The firmware's RXNE handler reads RXDR; that read consumes the byte -> advance.
        private uint rxByte;

        private void Advance()
        {
            step++;
            if(!InScript())
            {
                step = -1;
                IRQ.Unset();   // script complete
            }
        }

        private bool InScript() { return step >= 0 && step < script.Count; }

        private class Step { public uint Isr; public byte Data; }

        private readonly List<Step> script = new List<Step>();
        private int step;
        private uint cr1, oar1, oar2, cr2, timingr;
        private readonly long size;

        private const long CR1 = 0x00, CR2 = 0x04, OAR1 = 0x08, OAR2 = 0x0C, TIMINGR = 0x10;
        private const long ISR = 0x18, ICR = 0x1C, RXDR = 0x24, TXDR = 0x28;

        private const uint ISR_TXE = 1u << 0, TXIS = 1u << 1, RXNE = 1u << 2, ADDR = 1u << 3;
        private const uint NACKF = 1u << 4, STOP = 1u << 5, BERR = 1u << 8, ARLO = 1u << 9, DIR = 1u << 16;
        private const uint ADDR_CODE = 0x3Cu << 16;   // ADDCODE=(isr>>16)&0xfe -> 0x3C (host addr)
        private const uint TCPC_CODE = 0x9Cu << 16;   // ADDCODE 0x9c -> gale-as-TCPC (OAR2, ADDR_IS_TCPC)
        private const uint ICR_ADDRCF = 1u << 3, ICR_NACKCF = 1u << 4, ICR_STOPCF = 1u << 5,
                           ICR_BERRCF = 1u << 8, ICR_ARLOCF = 1u << 9;
    }
}
