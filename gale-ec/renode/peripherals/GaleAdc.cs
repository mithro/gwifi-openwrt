//
// gale EC Renode equivalence harness — STM32F0 12-bit ADC (RM0091 "ADC" chapter).
//
// Renode's stock Analog.STM32F0_ADC is a generic SAR model whose channel values
// are set with SetDefaultValue. That is unusable for the USB-PD debug-accessory
// scenario: the CC voltage the EC senses is NOT a constant — it is the divider
// result between the EC's OWN role-switched termination and the accessory's fixed
// 2xRd. When gale sinks (cc_pull = TYPEC_CC_RD) there is no pull-up, so CC reads
// ~open (0 mV); when gale sources (cc_pull = TYPEC_CC_RP) the accessory's Rd pulls
// CC into the Rd band (~800 mV). A single static value makes gale either never
// leave SNK_DISCONNECTED (reads non-open while sinking -> DEBOUNCE, no toggle) or
// never reach SRC_ACCESSORY (reads open while sourcing -> no connection). And a
// before-write SetDefaultValue hook perturbs the in-flight conversion and stalls
// gale's DRP toggle entirely.
//
// This model presents the real STM32F0 ADC register interface and the faithful
// DYNAMIC CC. board/gale wires CC1 = PA1 = AIN1 and CC2 = PA3 = AIN3 (gpio.inc),
// with pd_set_host_mode a no-op ("Rp/Rd are set in hardware") — so the EC's actual
// termination is mirrored only by the internal TCPC cc_pull byte in RAM. The model
// reads that byte (address is image-specific; set via `sysbus.adc CcPullAddress`)
// and, at conversion START (ADSTART), latches the divider result into DR:
//   cc_pull == TYPEC_CC_RP (1, sourcing) -> ~800 mV  (raw 993 = 800*4096/3300)
//   else (sinking / open)                -> 0 mV     (raw 0)
// All other channels read 0. Sampling at ADSTART (not at the DR read) matches the
// silicon sample-and-hold and keeps the conversion deterministic — required for
// trace-equivalence. The enable/calibrate/convert handshake matches adc_init and
// adc_read_channel in chip/stm32/adc-stm32f0.c exactly.
//
namespace Antmicro.Renode.Peripherals.Miscellaneous
{
    using Antmicro.Renode.Core;
    using Antmicro.Renode.Logging;
    using Antmicro.Renode.Peripherals.Bus;

    public class GaleAdc : IDoubleWordPeripheral, IKnownSize
    {
        public GaleAdc(IMachine machine, long size = 0x400)
        {
            this.size = size;
            this.sysbus = machine.GetSystemBus(this);
            Reset();
        }

        public long Size => size;

        // Image-specific RAM address of the TCPC port-0 cc_pull byte
        // (pd[0].cc_pull). Set from the harness per image; 0 disables dynamic CC.
        public uint CcPullAddress { get; set; }

        // PD CC-partner mode. The default (false) presents the debug-ACCESSORY: CC reads
        // the Rd band only while the EC SOURCES (cc_pull==RP), matching a 2xRd accessory.
        // When PartnerSource is true, the model presents a SOURCE attached to the sink:
        // CC1 reads the Rp-divider band (~800 mV, SNK_1_5) while the EC SINKS (cc_pull==RD),
        // so gale (force-sink DRP) attaches as a sink and advances to SNK_DISCOVERY — the
        // state in which it waits for the partner's Source_Capabilities (PD-PHY injection).
        // VBUS need not be modeled: gale's pd_snk_is_vbus_provided() is hardwired to 1.
        public bool PartnerSource { get; set; }

        public void Reset()
        {
            isr = 0; ier = 0; cr = 0; cfgr1 = 0; cfgr2 = 0;
            smpr = 0; tr = 0; chselr = 0; ccr = 0; dr = 0;
        }

        public uint ReadDoubleWord(long offset)
        {
            switch(offset)
            {
                case ISR:    return isr;
                case IER:    return ier;
                case CR:     return cr;
                case CFGR1:  return cfgr1;
                case CFGR2:  return cfgr2;
                case SMPR:   return smpr;
                case TR:     return tr;
                case CHSELR: return chselr;
                case CCR:    return ccr;
                case DR:
                    // Per RM0091, reading the data register clears EOC.
                    isr &= ~ISR_EOC;
                    return dr;
                default:     return 0;
            }
        }

        public void WriteDoubleWord(long offset, uint value)
        {
            switch(offset)
            {
                case ISR:
                    // ADRDY/EOSMP/EOC/EOSEQ/OVR/AWD are write-1-to-clear.
                    isr &= ~(value & ISR_W1C);
                    break;
                case IER:    ier = value; break;
                case CR:
                    // Calibration completes instantly (ADCAL self-clears).
                    if((value & CR_ADCAL) != 0)
                    {
                        cr = value & ~CR_ADCAL;   // ADCAL reads back 0 -> calib done
                        break;
                    }
                    // Enabling the ADC asserts ADRDY (adc_init spins on it).
                    if((value & CR_ADEN) != 0)
                    {
                        cr = value;
                        isr |= ISR_ADRDY;
                    }
                    // Disable clears ADEN/ADRDY.
                    if((value & CR_ADDIS) != 0)
                    {
                        cr &= ~CR_ADEN;
                        isr &= ~ISR_ADRDY;
                    }
                    // Starting a conversion samples-and-holds NOW, then completes
                    // instantly: latch the channel value into DR and assert EOC
                    // (+ EOSEQ, end of the 1-channel sequence). ADSTART self-clears.
                    if((value & CR_ADSTART) != 0)
                    {
                        dr = Convert();
                        isr |= ISR_EOC | ISR_EOSEQ;
                    }
                    // ADSTP self-clears immediately (no in-flight conversion).
                    cr &= ~(CR_ADSTART | CR_ADSTP);
                    break;
                case CFGR1:  cfgr1 = value; break;
                case CFGR2:  cfgr2 = value; break;
                case SMPR:   smpr = value; break;
                case TR:     tr = value; break;
                case CHSELR: chselr = value; break;
                case CCR:    ccr = value; break;
            }
        }

        // Sample-and-hold: produce the raw 12-bit count for the selected channel.
        // adc_read_channel selects exactly one channel (CHSELR = 1 << ain_id); the
        // CC channels follow the EC's live termination, every other channel reads 0.
        private uint Convert()
        {
            if(chselr == (1u << AIN_CC1) || chselr == (1u << AIN_CC2))
            {
                byte ccPull = CcPullAddress != 0 ? sysbus.ReadByte(CcPullAddress) : (byte)0;
                if(PartnerSource)
                {
                    // SOURCE attached to our sink: the source holds Rp, so while we SINK
                    // (cc_pull==RD) the active CC line (CC1) sits in the SNK_1_5 band; CC2
                    // stays open. When we momentarily source, both Rp's read ~open.
                    if(chselr == (1u << AIN_CC1) && ccPull == TYPEC_CC_RD)
                        return CC_RD_BAND_RAW;
                    return 0;
                }
                // Debug ACCESSORY (default): Rd band only while we SOURCE (cc_pull==RP).
                if(CcPullAddress != 0 && ccPull == TYPEC_CC_RP)
                    return CC_RD_BAND_RAW;
                return 0;                    // sinking / open: no pull-up
            }
            return 0;
        }

        private uint isr, ier, cr, cfgr1, cfgr2, smpr, tr, chselr, ccr, dr;
        private readonly IBusController sysbus;
        private readonly long size;

        // Register offsets (RM0091, ADC base 0x40012400)
        private const long ISR    = 0x00;
        private const long IER    = 0x04;
        private const long CR     = 0x08;
        private const long CFGR1  = 0x0C;
        private const long CFGR2  = 0x10;
        private const long SMPR   = 0x14;
        private const long TR     = 0x20;
        private const long CHSELR = 0x28;
        private const long DR     = 0x40;
        private const long CCR    = 0x308;

        // ISR bits
        private const uint ISR_ADRDY = 1u << 0;
        private const uint ISR_EOC   = 1u << 2;
        private const uint ISR_EOSEQ = 1u << 3;
        private const uint ISR_W1C   = 0x9f; // ADRDY|EOSMP|EOC|EOSEQ|OVR|AWD

        // CR bits
        private const uint CR_ADEN    = 1u << 0;
        private const uint CR_ADDIS   = 1u << 1;
        private const uint CR_ADSTART = 1u << 2;
        private const uint CR_ADSTP   = 1u << 4;
        private const uint CR_ADCAL   = 1u << 31;

        // gale channel assignment (board/gale/gpio.inc + board.c)
        private const int AIN_CC1 = 1; // USB_CC1_PD = PA1 = AIN1
        private const int AIN_CC2 = 3; // USB_CC2_PD = PA3 = AIN3

        // TCPC cc_pull enum (common/usb_pd_tcpc.c): RA=0, RP=1, RD=2, OPEN=3
        private const byte TYPEC_CC_RP = 1;
        private const byte TYPEC_CC_RD = 2;

        // ~800 mV in the CC channels' 3300/4096 scale: 800*4096/3300 = 993.
        private const uint CC_RD_BAND_RAW = 993;
    }
}
