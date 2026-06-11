//
// gale EC Renode equivalence harness — STM32F0 EXTI (RM0091 "Extended interrupts and
// events controller") with a USB-PD COMP-edge injector.
//
// The firmware's USB-PD receiver decodes BMC edges captured by the internal comparators
// (COMP1/COMP2), which are routed to EXTI lines 21/22 and raise the ADC_COMP IRQ (NVIC 12).
// The ISR chip/stm32/usb_pd_phy.c:pd_rx_handler() reads EXTI_PR, timestamps each edge, and
// once it sees PD_RX_TRANSITION_COUNT(3) edges within PD_RX_TRANSITION_WINDOW(20us) it calls
// pd_rx_start() (arms the TIM1-capture RX DMA) + pd_rx_event() (wakes pd_task to decode).
//
// Renode's stock EXTI doesn't model the COMP lines, and there is no analog comparator, so a
// CC partner cannot wake the PD task. This model stores the EXTI registers faithfully
// (so the firmware's EXTI config reads/writes behave) and adds a FireComp(line) method that
// sets EXTI_PR[line] and pulses the COMP IRQ — i.e. it plays the comparator seeing a CC edge.
// Calling FireComp three times within 20us of virtual time (with RX DMA samples pre-staged,
// see GaleDma.TimRxSampleCount) drives the real pd_rx_handler -> pd_rx_start -> pd_rx_event
// path, so the injected PD message (pd_encode.py) is decoded by the genuine firmware decoder.
//
// PR is write-1-to-clear (RM0091); pd_rx_handler clears it on non-trigger edges.
//
namespace Antmicro.Renode.Peripherals.Miscellaneous
{
    using Antmicro.Renode.Core;
    using Antmicro.Renode.Logging;
    using Antmicro.Renode.Peripherals.Bus;

    public class GaleExti : IDoubleWordPeripheral, IKnownSize
    {
        public GaleExti(IMachine machine, long size = 0x400)
        {
            this.size = size;
            IRQ = new GPIO();
            GpioIrq01 = new GPIO();    // EXTI lines 0-1   -> NVIC IRQ 5
            GpioIrq23 = new GPIO();    // EXTI lines 2-3   -> NVIC IRQ 6
            GpioIrq415 = new GPIO();   // EXTI lines 4-15  -> NVIC IRQ 7
            Reset();
        }

        public long Size => size;
        public GPIO IRQ { get; }
        // GPIO-pin EXTI interrupt lines (RM0091): a configured GPIO edge raises EXTI0_1/2_3/4_15. The
        // original model only played the COMP lines (21/22 -> ADC_COMP IRQ12); these model the GPIO-pin
        // EXTI path so the firmware's gpio_interrupt() (switch/WP/power-button GPIOs) runs.
        public GPIO GpioIrq01 { get; }
        public GPIO GpioIrq23 { get; }
        public GPIO GpioIrq415 { get; }

        public void Reset()
        {
            imr = emr = rtsr = ftsr = swier = pr = 0;
            IRQ.Unset();
            GpioIrq01.Unset(); GpioIrq23.Unset(); GpioIrq415.Unset();
        }

        // Play the COMP comparator: register a CC edge on EXTI `line` (21=COMP1, 22=COMP2)
        // and pulse the ADC_COMP IRQ so the firmware's pd_rx_handler runs.
        public void FireComp(int line)
        {
            pr |= (1u << line);
            IRQ.Set(true);
            IRQ.Set(false);
        }

        // Play a GPIO-pin EXTI edge on `line` (0-15): set PR and pulse the matching GPIO EXTI NVIC line,
        // so the firmware's gpio_interrupt() reads PR and dispatches the registered GPIO IRQ handler.
        public void FireGpio(int line)
        {
            pr |= (1u << (line & 31));
            var g = line <= 1 ? GpioIrq01 : (line <= 3 ? GpioIrq23 : GpioIrq415);
            g.Set(true);
            g.Set(false);
        }

        public uint ReadDoubleWord(long offset)
        {
            switch(offset)
            {
                case IMR:   return imr;
                case EMR:   return emr;
                case RTSR:  return rtsr;
                case FTSR:  return ftsr;
                case SWIER: return swier;
                case PR:    return pr;
                default:    return 0;
            }
        }

        public void WriteDoubleWord(long offset, uint value)
        {
            switch(offset)
            {
                case IMR:   imr = value; break;
                case EMR:   emr = value; break;
                case RTSR:  rtsr = value; break;
                case FTSR:  ftsr = value; break;
                case SWIER: swier = value; break;
                case PR:    pr &= ~value; break;   // write-1-to-clear
            }
        }

        private uint imr, emr, rtsr, ftsr, swier, pr;
        private readonly long size;

        private const long IMR   = 0x00;
        private const long EMR   = 0x04;
        private const long RTSR  = 0x08;
        private const long FTSR  = 0x0C;
        private const long SWIER = 0x10;
        private const long PR    = 0x14;
    }
}
