//
// gale EC Renode equivalence harness — W25Q64FV SPI flash on the AP-flash bridge.
//
// gale's EC bridges the AP's external SPI NOR flash (Winbond W25Q64FV, 8 MiB) on
// SPI2 (PB12 NSS / PB13 SCK / PB14 MISO / PB15 MOSI); the EC drives chip-select as
// a GPIO (SPI_FLASH_NSS = PB12, active low), bit-banged by the firmware around each
// spi_transaction(). This minimal model answers the commands the EC's `spixfer`
// console path and the raiden bridge use, END-TO-END: `spixfer rlen 0 0x1f 3`
// returns `ef4017` to the EC on both images (battery test passes). This works
// because GaleDma now interleaves the full-duplex SPI2 TX/RX DMA channels (clocks
// each TX byte, captures the slave response into the RX buffer). Commands:
//   * 0x9F JEDEC RDID  -> 0xEF 0x40 0x17 (Winbond, 64 Mbit) — the value the
//     HARDWARE-TEST-PLAN raiden test expects (flashrom RDID "ef4017").
//   * 0x03 / 0x0B READ -> bytes from a 0xFF-filled backing image (deterministic).
//   * 0x05 RDSR        -> 0x00 (not busy, not write-enabled).
// Chip-select framing is driven by the PB12 GPIO (OnGPIO): CS low starts a
// transaction, CS high ends it. All responses are deterministic — both firmware
// images read the identical model, so their SPI traces match.
//
namespace Antmicro.Renode.Peripherals.Miscellaneous
{
    using Antmicro.Renode.Core;
    using Antmicro.Renode.Logging;
    using Antmicro.Renode.Peripherals.SPI;

    public class GaleSpiFlash : ISPIPeripheral, IGPIOReceiver
    {
        public GaleSpiFlash(IMachine machine)
        {
            Reset();
        }

        public void Reset()
        {
            csAsserted = false;
            ResetTransaction();
        }

        // Chip-select: PB12 is active-low. GPIO low => CS asserted (transaction start).
        public void OnGPIO(int number, bool value)
        {
            var asserted = !value; // active low
            if(asserted && !csAsserted)
            {
                ResetTransaction();
            }
            else if(!asserted && csAsserted)
            {
                FinishTransmission();
            }
            csAsserted = asserted;
        }

        public byte Transmit(byte data)
        {
            byte resp = 0xFF;
            if(!gotCommand)
            {
                command = data;
                gotCommand = true;
                phase = 0;
                return 0xFF; // response to the command byte itself
            }
            switch(command)
            {
                case CMD_RDID:
                    resp = phase < 3 ? JEDEC_ID[phase] : (byte)0x00;
                    break;
                case CMD_RDSR:
                    resp = 0x00; // not busy, WEL clear
                    break;
                case CMD_READ:
                case CMD_FAST_READ:
                    if(phase < addrBytes)
                    {
                        address = (address << 8) | data;
                        resp = 0xFF;
                    }
                    else
                    {
                        // 0xFF backing image (deterministic); fast-read has 1 dummy byte
                        resp = 0xFF;
                        address++;
                    }
                    break;
                default:
                    resp = 0xFF;
                    break;
            }
            phase++;
            return resp;
        }

        public void FinishTransmission()
        {
            // Framing is driven by the real chip-select GPIO (PB12), NOT by the SPI
            // controller — the STM32SPI model calls FinishTransmission mid-transaction
            // (it has no GPIO-CS awareness), which would wrongly reset the command.
            // Transaction state is reset only on CS deassert in OnGPIO().
        }

        private void ResetTransaction()
        {
            gotCommand = false;
            command = 0;
            phase = 0;
            address = 0;
            addrBytes = 3;
        }

        private bool csAsserted;
        private bool gotCommand;
        private byte command;
        private int phase;
        private uint address;
        private int addrBytes;

        private const byte CMD_RDID = 0x9F;
        private const byte CMD_RDSR = 0x05;
        private const byte CMD_READ = 0x03;
        private const byte CMD_FAST_READ = 0x0B;
        private static readonly byte[] JEDEC_ID = { 0xEF, 0x40, 0x17 }; // Winbond W25Q64
    }
}
