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

        // Address-INDEPENDENT source partner: present the SNK_1_5 Rp band on CC1 unconditionally
        // (no cc_pull RAM read), so PD sink-attach works on ANY firmware image (the captured dump
        // has different RAM addresses than the recreation). gale's force-sink board policy keeps
        // it sinking, so a constant CC1 source level drives SNK_DISCONNECTED -> SNK_DISCOVERY.
        public bool ForceSourceCc { get; set; }
        public int ForceRaw { get; set; } = -1;   // -1 = off; else raw 12-bit value for non-CC channels

        // Address-independent DEBUG ACCESSORY: present BOTH CC lines in the Rd band so that when
        // gale sources (DRP toggle) it detects a Type-C debug accessory -> SRC_ACCESSORY ->
        // ccd_set_mode -> usb_init/CCD. Covers the source-accessory + CCD bring-up branches on
        // any image without the per-firmware cc_pull RAM address.
        public bool ForceAccessory { get; set; }

        // Address-independent STABLE SOURCE partner (the correct sink-attach stimulus): present a constant
        // >= PD_SRC_VNC (1600mV) on CC1. While gale SINKS (cc_pull=RD) this reads SNK_3_0 (a 3A source
        // attached) -> SNK_DISCONNECTED_DEBOUNCE -> SNK_DISCOVERY -> contract -> SNK_READY. While gale
        // SOURCES (cc_pull=RP) the same level reads >= VNC = OPEN/NC -> no sink -> gale does NOT
        // source-attach and toggles back to sink. Unlike ForceSourceCc (800mV, which a SOURCE classifies
        // as an Rd debug accessory -> gale latches SRC_ACCESSORY at boot and never sink-contracts), this
        // value is unambiguous in BOTH roles, so set BEFORE boot it makes gale's first detection sink-attach.
        public bool ForcePartnerSrc { get; set; }

        // Address-independent AUDIO ACCESSORY: present BOTH CC lines in the Ra band (both tied to GND
        // through Ra, < 400 mV) so that when gale sources it detects a Type-C analog-audio adapter ->
        // the cc1==RA && cc2==RA arm (usb_pd_protocol.c:1584) + its debounce/cc_state handling. This
        // models a real audio accessory the prior knobs could not present (they only do Rd/open bands).
        public bool ForceAudioAccessory { get; set; }

        // Address-independent POWERED-CABLE termination: Ra on CC1, Rd on CC2. Drives the
        // cc1==RA && cc2!=RA fall-through of the audio-accessory test (usb_pd_protocol.c:1584) that
        // neither both-Ra nor both-Rd can reach. Models a real e-marked cable + sink.
        public bool ForceCableRa { get; set; }

        // Address-independent NORMAL SINK partner attached to gale-as-SOURCE: present ONE CC in the
        // Rd band (sink on CC1) and the other OPEN (>= VNC). When gale is forced to source
        // (`pd dualrole source`), it sees a single Rd -> SRC_DISCONNECTED_DEBOUNCE -> SRC_STARTUP
        // -> SRC_DISCOVERY (sends Source_Caps) -> ... -> SRC_READY. This drives the SOURCE-side
        // contract states (previously mis-classified board-dead): they ARE reachable with a sink
        // partner, not structurally impossible.
        public bool PartnerSink { get; set; }

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
                if(ForceAccessory)  // address-independent: both CC in Rd band (debug accessory)
                {
                    return CC_RD_BAND_RAW;
                }
                if(ForcePartnerSrc)  // address-independent stable SOURCE on CC1 (>= VNC: sink sees SNK_3_0,
                {                    // source sees OPEN) -> gale sink-attaches at boot, never SRC_ACCESSORY.
                    return chselr == (1u << AIN_CC1) ? CC_OPEN_RAW : 0u;
                }
                if(ForceAudioAccessory)  // address-independent: both CC in Ra band (audio accessory)
                {
                    // A real Type-C analog-audio adapter ties both CC lines to GND through Ra.
                    // While gale SOURCES (cc_pull==RP) both lines read < PD_SRC_1_5_RD_THRESH_MV
                    // (400 mV) so cc_voltage_to_status classifies them TYPEC_CC_VOLT_RA on both,
                    // driving pd_task's audio-accessory arm (usb_pd_protocol.c:1584 cc1==RA && cc2==RA).
                    return CC_RA_BAND_RAW;
                }
                if(ForceCableRa)    // powered (e-marked) cable, no sink: Ra on CC1 (cable VCONN), CC2 open
                {
                    // A real e-marked cable with nothing plugged through it presents Ra on one CC line
                    // (its VCONN tap) and leaves the other OPEN. While gale SOURCES this reads cc1==RA,
                    // cc2==OPEN. In the captured classifier that means: cc1!=RD and cc2!=RD (skip debug),
                    // cc1==RA but cc2!=RA -> the FALL-THROUGH of the audio-accessory test
                    // (usb_pd_protocol.c:1584). Asymmetric; unreachable via the both-Ra/both-Rd knobs.
                    return chselr == (1u << AIN_CC1) ? CC_RA_BAND_RAW : CC_OPEN_RAW;
                }
                if(PartnerSink)     // normal sink on CC1, CC2 open -> gale-as-source attaches a sink
                {
                    return chselr == (1u << AIN_CC1) ? CC_RD_BAND_RAW : CC_OPEN_RAW;
                }
                if(ForceSourceCc)   // address-independent: constant source on CC1
                {
                    return chselr == (1u << AIN_CC1) ? CC_RD_BAND_RAW : 0u;
                }
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
            // Non-CC channels (VBUS / CURRENT): normally 0. ForceRaw lets the harness drive extreme
            // analog values to exercise OVP/OCP/vbus-present validation branches (the error edge of
            // checks whose success edge the normal campaign already covers).
            return ForceRaw >= 0 ? (uint)(ForceRaw & 0xFFF) : 0u;
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

        // ~800 mV in the CC channels' 3300/4096 scale: 800*4096/3300 = 993. In the source RD band
        // [400,1600)mV so gale-as-source reads it as a sink (Rd) attached.
        private const uint CC_RD_BAND_RAW = 993;
        // ~1800 mV >= PD_SRC_1_5_VNC_MV (1600) -> CC_NC (open) for a source: the unused CC line.
        private const uint CC_OPEN_RAW = 2234;
        // ~100 mV < PD_SRC_1_5_RD_THRESH_MV (400) -> CC_RA for a source (cc_pull==RP): an Ra-only
        // termination. 100*4096/3300 = 124. Used by ForceAudioAccessory on both CC lines.
        private const uint CC_RA_BAND_RAW = 124;
    }
}
