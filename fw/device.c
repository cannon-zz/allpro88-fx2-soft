/**
 * Copyright (C) 2020-2024 Kipp Cannon
 *
 * This program is free software: you can redistribute it and/or modify it
 * under the terms of the GNU General Public License as published by the
 * Free Software Foundation, either version 3 of the License, or (at your
 * option) any later version.
 *
 * This program is distributed in the hope that it will be useful, but
 * WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General
 * Public License for more details.
 *
 * You should have received a copy of the GNU General Public License along
 * with this program. If not, see <https://www.gnu.org/licenses/>.
 *
 * Portions of this program carried the following copyright notice:
 *
 * Copyright (C) 2009 Ubixum, Inc. 
 *
 * This library is free software; you can redistribute it and/or modify it
 * under the terms of the GNU Lesser General Public License as published by
 * the Free Software Foundation; either version 2.1 of the License, or (at
 * your option) any later version.
 *
 * This library is distributed in the hope that it will be useful, but
 * WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Lesser
 * General Public License for more details.
 *
 * You should have received a copy of the GNU Lesser General Public License
 * along with this library; if not, write to the Free Software Foundation,
 * Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301  USA
 **/


#include <delay.h>
#include <fx2macros.h>
#include <eputils.h>
#include <gpif.h>


/*
 * the SYNCDELAY must be inserted between certain register accesses.  the
 * precise rules are in the Technical Reference Manual Section 15.15, but I
 * think the general reason for it is because the GPIF subsystem is
 * independent of the CPU, and the CPU has to wait for the GPIF subsystem
 * to do a full clock cycle between configuration changes.  the number of
 * clock cycles is 1.5 * (CPU freq / IF freq + 1), rounded up.  the minimum
 * is 2, which occurs when the CPU freq is so slow compared to the IF
 * frequency it's effectively halted.  the manual says the "most typical"
 * configuration is for both to be set to 48 MHz, in which case 3 CPU
 * cycles are required.
 */


#define SYNCDELAY SYNCDELAY3


/*
 * ============================================================================
 *
 *                               C-ish Library
 *
 * ============================================================================
 */


/*
 * TRUE = an error occured in a function call
 */


static BOOL errno = FALSE;


/*
 * convert upper-case base 16 strings of various fixed lengths to numerical
 * values
 */


inline static BYTE hex_to_val(unsigned char digit)
{
	digit -= '0';
	if(digit > 9) {
		digit -= 'A' - '0';
		if(digit > 0xF - 0xA) {
			errno = TRUE;
			return 0;
		}
		digit += 0xA;
	}
	return digit;
}


inline static BYTE str_to_byte(const char *str)
{
	return hex_to_val(str[0]) << 4 | hex_to_val(str[1]);
}


static WORD str_to_word(const char *str)
{
	return MAKEWORD(str_to_byte(str), str_to_byte(str + 2));
}


static DWORD str_to_dword(const char *str)
{
	return MAKEDWORD(str_to_word(str), str_to_word(str + 4));
}


/*
 * write a null-terminated string without the terminator character.
 * assumes AUTOPTR2 is set to the destination.
 */


static void puts(const char *str)
{
	while(*str)
		XAUTODAT2 = *str++;
}


/*
 * write integers to base 16 strings of various fixed lengths.  assumes
 * AUTOPTR2 is set to the destination.
 */


inline static void puts_byte(BYTE val)
{
	static const char hex_digit[] = {'0', '1', '2', '3', '4', '5', '6', '7', '8', '9', 'A', 'B', 'C', 'D', 'E', 'F'};
	XAUTODAT2 = hex_digit[val >> 4];
	XAUTODAT2 = hex_digit[val & 0xf];
}


inline static void puts_word(WORD val)
{
	puts_byte(MSB(val));
	puts_byte(LSB(val));
}


static void puts_dword(DWORD val)
{
	puts_word(MSW(val));
	puts_word(LSW(val));
}


/*
 * write a newline character.  assumes AUTOPTR2 is set to the destination.
 */


inline static void newline(void)
{
	XAUTODAT2 = '\n';
}


/*
 * ============================================================================
 *
 *                           AllPro88 I/O Sequences
 *
 * ============================================================================
 */


/*
 * Port A = address bus low byte
 * Port B = data bus
 * Port D[0:3] = address bus bits 8,9,10,11
 * Port D[4] = /RESET
 * Port D[5:7] = GPIO connector pins 2,3,4
 * CTL0 = /WR
 * CTL1 = /ACT activity LED control, 0 = on, 1 = off
 * CTL2 = /RD
 */


inline static void ALLPRO88_ADDR_SET(WORD addr)
{
	/* the low byte of the 12 bit address */
	IOA = LSB(addr);
	/* /RESET is set high, and combined with the high nibble of the 12
	 * bit address */
	IOD = 0x10 | MSB(addr);
}

#define ALLPRO88_NRESET PD4


/*
 * read a byte from the ALLPRO 88.  notes on timing:
 *
 * 74HCT251 (8-to-1 multiplexer used as pin driver comparator register).
 * the comparator outputs are always present on the muxer's inputs so there
 * is no switching time to account for in that regard.  the muxer's select
 * lines are driven by the pin driver address bus which is synthesized from
 * the external address bus by TIBPAL16L8-25CN programmable logic devices
 * which have a 25 ns maximum propogation delay.  from the muxer's select
 * pins settling to output pin being valid is at most about 50 ns, and from
 * output enable pin to output pin being valid is at most about 38 ns,
 * but these two processes likely can occur concurrently (if the select
 * pins and output enable are all activated simultaneously, it will take 50
 * ns for the output to be valid, not 88 ns).  the output enable is
 * generated from the /RD line and a board /SELECT line produced by the
 * same programmable logic devices.  these propogate through two 74HCT02
 * quad nor gate elements before driving the output enable line, which adds
 * an additional 52 ns of delay.  from external address bus being set to
 * 74HCT251 being ready to respond to /RD is a total of about 75 ns;  from
 * /RD being pulled low to the chip's output being valid is about 90 ns.  I
 * see no reason why this can't all be occuring concurrently.  in the worst
 * case scenario the data bus undergoes some rapid switching as the
 * HCT251's output enable goes active before its select logic has settled,
 * but as long as the receiving end waits appropriately long for the dust
 * to settle it should be fine.  anyway, at least 1 instruction cycle (83
 * ns) must elapse between setting the address bus and pulling /RD low, and
 * adding the two stages of nor gate delay to that the output enable signal
 * almost certainly can't go active until after the select logic has had
 * time to settle.
 *
 * the HCT251's output is buffered by a 74LS245 transceiver with an 8 ns
 * propagation time and about 25 ns time to change direction, which occurs
 * when /RD is pulled low, so from the 8-to-1 muxer chip's output settling
 * to it appearing on the programmer's external data bus there is an
 * additional 32 ns.
 *
 * address bus -to- HCT251's select pins valid = 25 ns
 * address bus -to- board /SELECT valid = 25 ns
 * /RD, /SELECT -to- HCT251 output enable valid = 52 ns
 * /RD -to- LS245 direction change complete = 25 ns
 * HCT251 output enable, select pins -to- output valid = 50 ns
 * HCT251 output valid -to- FX2 input valid = 8 ns
 *
 * altogether (not to scale):
 *
 *            | >=25 ns |
 * ADDR ------<========================>-------
 *  /RD -----------------______________--------
 *                      |
 * DATA ---------------------------<======>----
 *                      | >=110 ns |
 *
 * set address bus, wait 25 ns, pull /RD low, wait 110 ns, latch data bus,
 * release /RD and address bus
 *
 * at 48 MHz:
 *	110 ns = 5.3 periods (round up to 6 = 125 ns)
 *
 * one fx2 instruction cycle is 4 clock cycles, or about 83.3 ns, so the
 * time between setting the address bus ports and triggering the GPIF
 * waveform (several instruction cycles) is already much longer than the
 * minimum 25 ns address bus setup time, so no explicit delay for the
 * address bus setup time is included anywhere.
 *
 * default single-byte read waveform is in descriptor 2
 *
 * S0 = don't sample data bus, pull /RD and /ACT low, hold for 6 cycles
 * S1 = sample data bus, pull /RD and /ACT low, uncond. branch to S7
 * S2 = not used
 * S3 = not used
 * S4 = not used
 * S5 = not used
 * S6 = not used
 * S7 = reserved (go to idle state)
 *
 * NOTE:  normally the waveform microcode is generated by a
 * Cypress-supplied windows program.  I don't have access to that program,
 * nor to a windows system on which to run it, so I have to construct the
 * microcode by hand.  the microcode format is adequately documented, but I
 * have found *ZERO* documentation on what the contents of the S7 state
 * should be.  all reference manuals I have found simply say "reserved".
 * in my first attempts I left it all zeros and things didn't work right.
 * apart from not knowing what the S7 vector should be set to, I had other
 * bugs in my microcode, and altogether the result was enough to damage my
 * ALLPRO88.  in fixing the GPIF microcode, to find clues about what the S7
 * vector should be set to, I looked for, and found, example waveform
 * microcode in various FX2 projects sprinkled around online here and
 * there.  I fixed my other microcode bugs, and tweaked the S7 state code
 * based on what I had found online, all at the same time.  the microcode
 * now works well.  I'm afraid to experiment with the S7 state vector to
 * see what of it is necessary, so I've left it as is.  in all examples I
 * found, the "length" was 7, the "opcode" was 0, the "logic" was 0x3f, and
 * the "output" was set to whatever state the control lines should be in in
 * the idle state.
 */


static const BYTE gpif_read_waveform[] = {
/*            S0    S1    S2    S3    S4    S5    S6    S7 */
/* length */ 0x06, 0x3f, 0x00, 0x00, 0x00, 0x00, 0x00, 0x07,
/* opcode */ 0x00, 0x03, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
/* output */ 0x01, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x07,
/* logic  */ 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x3f
};


static BYTE allpro88_read(WORD addr)
{
	/* wait until GPIF "done" bit is set */
	while(!GPIFDONE);
	/* drive address */
	ALLPRO88_ADDR_SET(addr);
	/* immediately trigger GPIF single byte read using a dummy read
	 * operation.  no delay is required, instruction cycle time is
	 * sufficient delay. */
	/* FIXME:  does the compiler turn this into a read operation?
	 * 2024-07-23 w/ SDCC 4.4.0 the answer is yes. */
	(void) XGPIFSGLDATLX;
	/* wait until GPIF "done" bit is set */
	while(!GPIFDONE);
	/* retrieve the data */
	return XGPIFSGLDATLNOX;
}


/*
 * write a byte to the ALLPRO 88.  notes on timing:
 *
 * DAC0832 (pin driver and VPUL DACs).  the DAC0832 chips are said to have
 * "active low" write lines, but latch the data present on their inputs
 * upon a low-to-high transition of the /WR control line.  the DAC chips's
 * positive supply is 12 V, and the documentation says with that supply
 * voltage /WR must be held low for at least 320 ns before being raised
 * high again, the data bits must be held stable for at least 320 ns prior
 * to the low-to-high transition of /WR, and must remain stable for about
 * 30 ns after /WR is raised.  the /XFER timings are essentially identical,
 * except the data bits in question are the outputs of the input latch not
 * the external data bus, so the latch must have had latched the data at
 * least 320 ns (3.84 instruction cycles) prior to a low-to-high transition
 * of /XFER, etc.
 *
 * 74HCT273 octal latches (pin driver config registers).  data is latched
 * on low-to-high transition of clock (/WR line).  /WR must be held low for
 * at least 16 ns before a low-to-high transition, and cannot be pulled low
 * again for at least 16 ns.  data must be valid for at least 12 ns prior
 * to a low-to-high transition of /WR and stay valid for at least 3 ns
 * after.
 *
 * AD7226 (power supply control DACs).  data is clocked in by a high-to-low
 * transition of /WR.  /WR must be held low for at least 50 ns, and the
 * data lines must be stable for at least 50 ns prior to the high-to-low
 * transition.
 *
 * the data bus is buffered by a 74LS245 transceiver with an 8 ns
 * propagation time and about 25 ns time to change direction, and on the
 * pin driver modules by a 74HCT244 with a 13 ns propagation time.  the
 * direction of the 74LS245 is controlled by the /RD line and so there is
 * no change-of-direction delay when only a write is occuring.  so from
 * when the data bus is set it takes about 46 ns before the value appears
 * on the input pins to a device.
 *
 * the /WR lines for the pin driver DAC chips and pin driver HCT273 config
 * latches are synthesized from the pin driver address bus by 74HCT138
 * 3-to-8 line decoders which have a propogation delay of up to 38 ns, and
 * the pin driver address lines are synthesized from the external address
 * by TIBPAL16L8-25CN programmable logic devices which have a 25 ns maximum
 * propogation delay, so from when the address bus is set it takes about
 * 65 ns before the /WR signal will be routed to the correct physical chip.
 * for the HCT273's, there's an additional 74HCT02 quad nor gate used as an
 * inverter delaying one of the address lines by about 26 ns, but because
 * the HCT273 has negligible setup and hold requirements compared to the
 * DAC0832 chips we don't bother adding anything extra for that.
 *
 * altogether (not to scale):
 *
 *            | >=65 ns    |
 * ADDR ------<==================================>-------
 *  /WR --------------------__________-------------------
 *                         | >=500 ns |
 * DATA ---------<===============================>-------
 *               | >=75 ns |          | >= 30 ns |
 *
 * set address bus, set data bus, wait 75 ns, pull /WR low, wait 500 ns,
 * raise /WR, wait 30 ns, release buses.
 *
 * at 48 MHz:
 *	500 ns = 24.0 periods
 *	75 ns = 3.6 periods
 *	65 ns = 3.2 periods
 *	30 ns = 1.4 periods
 *
 * one fx2 instruction cycle is 4 clock cycles, or about 83.3 ns, so the
 * time between setting the address bus ports and triggering the GPIF
 * waveform (a minimum of 1 instruction) is already longer than the minimum
 * 65 ns address bus setup time, but then the data bus setup delay included
 * in the waveform model provides another 75 ns on top of that, so there's
 * more than enough altogether.
 *
 * default single-byte write waveform is in descriptor 3
 *
 * S0 = drive data bus, ctl lines high, hold for 1 clock cycle
 * S1 = drive data bus, ctl lines high, hold for 1 clock cycle
 * S2 = drive data bus, ctl lines high, hold for 1 clock cycle
 * S3 = drive data bus, ctl lines high, hold for 1 clock cycle
 * S4 = drive data bus, pull /WR and /ACT low, hold for 24 clock cycles
 * S5 = drive data bus, ctl lines high, hold for 1 clock cycle
 * S6 = drive data bus, ctl lines high, hold for 1 clock cycle
 * S7 = reserved (go to idle state)
 */


static const BYTE gpif_write_waveform[] = {
/*            S0    S1    S2    S3    S4    S5    S6    S7 */
/* length */ 0x01, 0x01, 0x01, 0x01, 0x18, 0x01, 0x01, 0x07,
/* opcode */ 0x02, 0x02, 0x02, 0x02, 0x02, 0x02, 0x02, 0x00,
/* output */ 0x07, 0x07, 0x07, 0x07, 0x04, 0x07, 0x07, 0x07,
/* logic  */ 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x3f
};


static void allpro88_write(WORD addr, BYTE data)
{
	/* wait until GPIF "done" bit is set */
	while(!GPIFDONE);
	/* drive address.  the waveform starts with a 75 ns hold time after
	 * setting the data bus, and the additional instruction cycle delay
	 * to trigger the GPIF waveform provides more than enough total
	 * hold time for the address bus */
	ALLPRO88_ADDR_SET(addr);
	/* trigger GPIF single byte write */
	XGPIFSGLDATLX = data;
}


/*
 * ============================================================================
 *
 *                        AllPro88 Programmer Control
 *
 * ============================================================================
 */


enum ALLPRO88_PCR_BITS {
	PCR_DISABLE = 0x00,
	/* enables power supplies, and lights red "busy" LED on socket
	 * board */
	PCR_ENABLE = 0x01,
	/* turns off green "idle" LED on socket board.  no other effect */
	PCR_NIDLE = 0x02
};


enum ALLPRO88_PINCON_BITS {
	PINCON_DISABLE = 0x00,
	PINCON_GND = 0x01,
	PINCON_VDAC = 0x02,
	PINCON_VTST = 0x04,
	PINCON_LOGICH = 0x08,
	PINCON_PULLUP = 0x10,
	PINCON_LOGICL = 0x20,
	PINCON_POSCLK = 0x40,
	PINCON_NEGCLK = 0x60,
	PINCON_PULLDN = 0x80
};


/*
 * set the PCR (power supply control register)
 */


inline static void allpro88_set_PCR(enum ALLPRO88_PCR_BITS val)
{
	allpro88_write(0x030c, val);
}


/*
 * set the VADJ voltage DAC.  the output voltage will be
 *
 * VADJ =  0.8598 + (dac * 0.119036) + (dac**2. * -0.0000115199973)
 *
 * NOTE:  VADJ must be at least 1 or 2 volts above the highest of all of
 * the pin DAC voltages, VPUL, VTST and VTH because it supplies all of
 * these.
 */


inline static void allpro88_set_VADJ(BYTE vdac)
{
	allpro88_write(0x0302, vdac);
}


/*
 * set the VADJTH voltage DAC.  the voltage will be
 *
 * VADJTH = 0.1 * vdac
 */


inline static void allpro88_set_VADJTH(BYTE vdac)
{
	allpro88_write(0x0303, vdac);
}


/*
 * set the VTH voltage DAC.  the voltage will be
 *
 * VTH = 0.1 * vdac
 */


inline static void allpro88_set_VTH(BYTE vdac)
{
	allpro88_write(0x0301, vdac);
}


/*
 * set the VSR voltage DAC.  the voltage will be
 *
 * VSR = 0.1 * vdac
 */


inline static void allpro88_set_VSR(BYTE vdac)
{
	allpro88_write(0x0300, vdac);
}


/*
 * set the VPUL voltage DAC.  the output voltage will be
 *
 * VPUL = -0.54392 + (dac * 0.100723) + (dac ^ 2 * 0.000000000497)
 *
 * NOTE:  the change does not take effect until the PINDAC xfer resgister
 * is written to.  see allpro88_xfer_PINDACs().
 */


inline static void allpro88_set_VPUL(BYTE vdac)
{
	allpro88_write(0x0305, vdac);
}


/*
 * set the VTST current and voltage DACs.
 *
 * IDAC = Iout in millamperes,
 *
 * EDAC = (Eout - 0.408 - (0.003855 * IDAC)) / 0.10151
 */


inline static void allpro88_set_VTST(BYTE vdac, BYTE idac)
{
	allpro88_write(0x0386, vdac);
	allpro88_write(0x0387, idac);
}


/*
 * start address for the control registers for a channel
 */


static WORD allpro88_channel_addr(BYTE channel)
{
	/* channel 0 starts at 0x0000, 1 at 0x0010, etc., up to channel
	 * 0x27 which starts at 0x0270, then channel 0x28 starts at 0x0400,
	 * and they continue in order from there, upto and including
	 * channel 0x57 */
	if(channel > 0x27)
		channel += 0x18;
	return (WORD) channel << 4;
}


/*
 * set the PINCON register for a channel
 */


#if 0	/* not used */
inline static void allpro88_set_PINCON(BYTE channel, enum ALLPRO88_PINCON_BITS val)
{
	/* config register is at offset 0 from the start of the register
	 * group for each channel */
	allpro88_write(allpro88_channel_addr(channel), val);
}
#endif


/*
 * set the DAC register for a channel.  the voltage will be
 *
 * VDAC = -0.5 + (0.1 * dac)
 *
 * NOTE:  the change does not take effect until the PINDAC xfer resgister
 * is written to.  see allpro88_xfer_PINDACs().
 */


inline static void allpro88_set_PINDAC(BYTE channel, BYTE val)
{
	/* DAC register is at offset 3 from the start of the register group
	 * for each channel */
	allpro88_write(allpro88_channel_addr(channel) + 3, val);
}


/*
 * load all channel DACs and VPUL DAC from their registers.  this causes
 * the DAC value set for each channel and for VPUL to take effect.
 */


inline static void allpro88_xfer_PINDACs(void)
{
	allpro88_write(0x308, 0);
}


/*
 * enable/disable the bypass capacitor for a channel.  only channels < 0x30
 * have bypass capacitors.
 */


#if 0	/* not used */
inline static void allpro88_set_PINBYPASS(BYTE channel, BOOL enable)
{
	if(channel < 0x28)
		allpro88_write(0x0280 + channel, enable);
	else if(channel < 0x30)
		allpro88_write(0x02c0 - 0x28 + channel, enable);
}
#endif


/*
 * reset the ALLPRO 88 circuitry
 */


static void allpro88_hard_reset(void)
{
	BYTE channel;

	/*
	 * the /RESET line clears all configuration registers (octal latch
	 * chips) back to 0.  that disables all channel outputs, and turns
	 * off all power supplies.  we pull it low (active), ensure the /RD
	 * and /WR control lines (and /ACT) are high (inactive), wait a
	 * while.  the data bus is floating during all of this.  finally,
	 * the address bus set to 0, and /RESET set high (inactive) taking
	 * the harware out of reset.
	 */

	/* set /RESET low */
	ALLPRO88_NRESET = 0;
	/* abort any pending waveforms, set /ACT, /RD, /WR high */
	GPIFABORT = 0xFF;
	GPIFIDLECTL = 0x07;
	/* wait a while (1 ms) */
	delay(1);
	/* zero the address bus (raises /RESET) */
	ALLPRO88_ADDR_SET(0);

	/*
	 * it should now be safe to use our canned routines to manipulate
	 * the programmer's interface bus via the FX2 GPIO lines.  use our
	 * new-found powers to reset all the DAC control registers.  these
	 * are not cleared by a hardware reset, they need to be cleared
	 * manually.
	 */

	/* zero the DACs that can be written to directly */
	allpro88_set_VADJ(0);
	allpro88_set_VADJTH(0);
	allpro88_set_VSR(0);
	allpro88_set_VTH(0);
	allpro88_set_VTST(0, 0);

	/* zero the DACs that require a separate update step, then do it */
	for(channel = 0; channel < 88; channel++)
		allpro88_set_PINDAC(channel, 0);
	allpro88_set_VPUL(0);
	allpro88_xfer_PINDACs();

	/*
	 * zero the address bus (leave /RESET high).
	 */

	ALLPRO88_ADDR_SET(0);
}


/*
 * test for installed pin drivers, and record a bit map.  because this test
 * requires the main power supplies to be enabled and pin drivers
 * configured for ground potential this is done only at power-on when there
 * should not be a part installed in a socket.  it is not repeated as part
 * of the hardware reset sequence, because that is typically repeated each
 * time the host software connects to the device.
 *
 * installed_channel_drivers is a bit mask, with each bit indicating the
 * presence of an 8-channel channel driver plug-in board, or "channel
 * group".  the lowest-order bit is for channel group 0 (channels 0 through
 * 7 inclusively);  1 = channel group is installed.
 */


__xdata static WORD installed_channel_drivers;

static void scan_installed_channel_drivers(void)
{
	BYTE channel;
	BYTE bit;

	/* turn on main power supply, set VTH to about 1 V */
	allpro88_set_PCR(PCR_ENABLE | PCR_NIDLE);
	allpro88_set_VADJ(10);
	allpro88_set_VTH(10);
	delay(10 /* ms */);	/* let power supplies slew */

	/* scan the channels.  the channel drivers are implemented as
	 * plug-in boards, each with 8 channels, so we just check for one
	 * of the 8 channels for each board to test if that board is
	 * present.  installed_channel_drivers is a bit mask indicating
	 * which of the 11 boards are installed.  to test a channel for its
	 * presence, we set each to pull-down (0 V), and compare the
	 * voltage to VTH.  missing channels will not respond to the read,
	 * so the pull-up resistors on the data-bus will set the bus to
	 * 0xff, making it seem as if the voltage on the pin is above
	 * threhsold. */

	installed_channel_drivers = 0;
	for(channel = 0, bit = 1; channel < 88; channel += 8, bit <<= 1) {
		const WORD addr = allpro88_channel_addr(channel);
		allpro88_write(addr, PINCON_PULLDN);
		/* let bus relax.  for channels that aren't installed,
		 * we're relying on the data bus' pull-up resistors to set
		 * the bits high.  experiments show that we seem to be able
		 * to read back the bus too quickly for the pull-up
		 * resistor time constant:  if we immediately do the port
		 * read, we still still see the value of PINCON_PULLDN on
		 * the data bus.  adding a small delay fixes */
		delay(1 /* ms */);
		if(!(allpro88_read(addr) & 1))
			installed_channel_drivers |= bit;
		allpro88_write(addr, PINCON_DISABLE);
	}

	/* zero dacs and turn off power supply */
	allpro88_set_VTH(0);
	allpro88_set_VADJ(0);
	allpro88_set_PCR(PCR_DISABLE);
}


/*
 * use a bisection search with VTH to measure the voltage on a channel.
 * returns the VTH DAC count value that sets VTH to within 1 LSB of the
 * voltage on the given channel.
 *
 * NOTE:  VTH is left modified by this operation, it is left set to its
 * approximation of the measured voltage.
 *
 * the VTH slew rate is about 2.5 V/us.  we need to ensure enough time
 * passes between setting VTH and reading the comparator state.  what's
 * here seems to be OK, but I've not carefully tested it, nor am I certain
 * I measured the slew rate correctly (it seems quite slow).  experiments
 * seem to prove that the 60 NOPs are not required at all, but I've left
 * them in just to be safe.  obviously only the first iteration would need
 * them anyway, the second shouldn't need more than 30, the third not more
 * than 15, and so on.  FIXME:  re-check the slew rate, and get rid of the
 * NOPs if it's true they aren't needed.
 */


static BYTE allpro88_measure_pin_voltage(BYTE channel)
{
	WORD addr = allpro88_channel_addr(channel);
	BYTE vdac = 0;
	BYTE test_bit;
	for(test_bit = 0x80; test_bit; test_bit >>= 1) {
		allpro88_set_VTH(vdac | test_bit);
		/* 60 NOPs = 5 us pause = 12.5 V slew delay */
		NOP; NOP; NOP; NOP; NOP; NOP; NOP; NOP; NOP; NOP;
		NOP; NOP; NOP; NOP; NOP; NOP; NOP; NOP; NOP; NOP;
		NOP; NOP; NOP; NOP; NOP; NOP; NOP; NOP; NOP; NOP;
		NOP; NOP; NOP; NOP; NOP; NOP; NOP; NOP; NOP; NOP;
		NOP; NOP; NOP; NOP; NOP; NOP; NOP; NOP; NOP; NOP;
		NOP; NOP; NOP; NOP; NOP; NOP; NOP; NOP; NOP; NOP;
		if(allpro88_read(addr) & 1)
			vdac |= test_bit;
	}
	return vdac;
}


/*
 * use a bisection search with VADJTH to measure the VADJ voltage
 *
 * NOTE:  VADJTH is, obviously, left modified by this operation
 */


static BYTE allpro88_measure_vadj_voltage(void)
{
	BYTE vdac = 0;
	BYTE test_bit;
	for(test_bit = 0x80; test_bit; test_bit >>= 1) {
		allpro88_set_VADJTH(vdac | test_bit);
		if(allpro88_read(0x0300) & 0x10)
			vdac |= test_bit;
	}
	return vdac;
}


/*
 * ============================================================================
 *
 *                                   Setup
 *
 * ============================================================================
 */


inline static void arm_out_endpoint(void)
{
	/* arm endpoint 2.  an out end-point is armed by writing any value
	 * to the byte-count low byte.  with AUTOOUT=0, the high bit is the
	 * "SKIP" bit, indicating whether the FIFO system should skip the
	 * last received packet or send it to the outside world via the
	 * FIFO interface.  we aren't using the FIFO interface, we're using
	 * the pins for GPIO, so we must always set this bit to 1 when
	 * re-arming. */
	SYNCDELAY;
	EP2BCL = 0x80;
	SYNCDELAY;
}


inline static void arm_in_endpoint(void)
{
	/* arm end-point 6 setting the byte count to the offset of autoptr2
	 * from the start of the buffer.  write byte-count high byte first.
	 * end-point is armed when low byte is written */
	WORD n = MAKEWORD(AUTOPTRH2, AUTOPTRL2) - EP6FIFOBUF;
	SYNCDELAY;
	EP6BCH = MSB(n);
	SYNCDELAY;
	EP6BCL = LSB(n);
	SYNCDELAY;
}


void main_init(void)
{
	/* set both IFCLK and CPU CLK to 48 MHz */

	SETCPUFREQ(CLK_48M);
	/*SETIF48MHZ();*/	/* done below when IFCONFIG is set */

	/* set 3 LSBs of CKCON register to 0 to reduce read/write strobe
	 * duration for MOVX instruction to minimum to increase data memory
	 * access speed */

	CKCON &= 0xf8;

	/* enable autopointers.  for both, increment on access. */

	AUTOPTRSETUP = 0x07;

	/* configure endpoints */

	/* I can't figure out what to set this to.  the documentation says
	 * over and over that for basically every configuration you can
	 * imagine this must be set to 3.  it says the only effect of
	 * setting bit 0 to 1 is to enable some additional features related
	 * to packet handling, while setting bit 1 to 1 only affects the
	 * behaviour when AUTOOUT is switched states, but this code doesn't
	 * ever change the AUTOOUT state.  it seems neither bit should have
	 * any affect for the purposes of this code, and yet only a value
	 * 0 allows this code to work.  also the bulkloop example provided
	 * with the original code sets it to 0 (which is where I got the
	 * idea to try this to figure out WTF is going on).  so I have no
	 * idea.  all I know is 0 works, 1 doesn't, 2 works, 3 doesn't. */

	SYNCDELAY;
	REVCTL = 0;
	SYNCDELAY;

	/* endpoints 2 and 6 enabled, 1, 4 and 8 disabled.  at power-on all
	 * FIFO's default to AUTOIN=0 / AUTOOUT=0 meaning the CPU must
	 * explicitly re-arm them for each packet.  that's what we want.
	 * endpoints 2, 4, 6, 8 have a WORDWIDE bit that must be cleared to
	 * 0 (see below). */

	EP1OUTCFG = 0;
	EP1INCFG = 0;
	EP2CFG = 0b10100010;	/* valid, out, bulk, 512 bytes, dbl buff'd */
	EP4CFG = 0;
	EP6CFG = 0b11100010;	/* valid, in, bulk, 512 bytes, dbl buff'd */
	EP8CFG = 0;
	SYNCDELAY;
	EP2FIFOCFG &= ~bmWORDWIDE;
	SYNCDELAY;
	EP4FIFOCFG &= ~bmWORDWIDE;
	SYNCDELAY;
	EP6FIFOCFG &= ~bmWORDWIDE;
	SYNCDELAY;
	EP8FIFOCFG &= ~bmWORDWIDE;
	SYNCDELAY;

	/* configure GPIF
	 * IFCONFIG bits:
	 *	7:	1 = GPIF clock source is internal
	 *	6:	1 = GPIF clock is 48 MHz
	 *	5:	0 = disable clock output
	 *	4:	0 = clock polarity is default
	 *	3:	1 = GPIF in async mode (CTL are R/W strobes)
	 *	2:	0 = default (not used for this chip version)
	 *	1, 0:	1,0 = GPIF master, port B is data bus low byte
	 * NOTE: to *not* use port D as the data bus high byte (to use it
	 * as a GPIO port), all WORDWIDE config bits must be set to 0.
	 * they default to 1, so they had to be cleared above.
	 *
	 * set CTL[0:2] (/WR, /ACT, /RD) to open-drain mode, and set their
	 * idle states high.  by default, the data bus is tri-stated when
	 * idle.
	 *
	 * NOTE:  GPIF waveforms cannot be loaded until the part is in GPIF
	 * mode.
	 */

	IFCONFIG = 0xCA;	/* 0b11001010 */
	GPIFABORT = 0xFF;	/* abort any pending waveforms */
	GPIFCTLCFG = 0x07;	/* /WR, /ACT, /RD non-tristate, open-drain */
	GPIFIDLECTL = 0x07;	/* /WR, /ACT, /RD high when idle */

	/*
	 * install waveform data.  default single read waveform at offset
	 * 2, single write waveform at offset 3.
	 */

	{
	BYTE i;
	for(i = 0; i < 32; i++) {
		(&GPIF_WAVE_DATA)[64 + i] = gpif_read_waveform[i];
		(&GPIF_WAVE_DATA)[96 + i] = gpif_write_waveform[i];
	}
	}

	/*
	 * configure I/O ports.  port A (address bus low byte) all pins for
	 * I/O port, disable alternate functions.  zero ALLPRO88 address
	 * bus, pull /RESET low.  NOTE:  the power-on default state for the
	 * ports is input mode, so at this stage the pins are tri-stated.
	 * we are not actually setting their states, we are setting what
	 * state they will be driven to when we switch them to output mode
	 * in the next step.  finally, configure address bus and /RESET
	 * GPIO pins for output set address and control bus pins for output
	 * (if it isn't already, this now for real pulls /RESET low,
	 * putting programmer into reset state)
	 */

	PORTACFG = 0;
	IOA = 0x00;	/* address bus low byte = 0 */
	IOD = 0x00;	/* address bus high nibble = 0, set /RESET = 0 */
	OEA = 0xff;	/* address bus low byte output enable */
	OED = 0x1f;	/* address bus high nibble, /RESET output enable */

	/* now we can control the programmer through its interface bus.  it
	 * is currently held in the reset state.  perform a full hardware
	 * reset */

	allpro88_hard_reset();

	/* scan for installed channel drivers */

	scan_installed_channel_drivers();

	/* arm end-point 2.  I don't know why this has to be done twice.  I
	 * think it's because the chip boots up believing the buffers are
	 * already full of received data and we have to, in effect, clock
	 * both of the buffers through the system before it believes it can
	 * receive new data.  doing it once doesn't work, and the examples
	 * show this being done twice at start-up.  if my belief is
	 * correct, the correct number of times to do this is not
	 * necessarily 2, but however many -uple's worth of buffering you
	 * have configured the chip for (double, quadruple, etc.). */

	arm_out_endpoint();
	arm_out_endpoint();

	/* set up WAKEUP pin handling.  WAKEUP pin is used to monitor USB
	 * VBUS:  high = USB VBUS is present, low = USB VBUS has been lost,
	 * which could mean the cable is disconnected or that the host has
	 * been turned off.  in the latter case, we must turn off the
	 * pull-up resistor on the D+ line to prevent us from attempting to
	 * back-power the host through the USB bus.
	 *
	 * if the pin is ever in the active, or true, state, that gets
	 * latched and stored in the WU bit.  the meaning of "active" is
	 * selected by the WUPOL bit:  0 = active low; 1 = active high.
	 * the WU bit is cleared to 0 by writing a 1 to it.  if the WAKEUP
	 * pin is still active the bit is immediately latched back into the
	 * 1 state.
	 *
	 * changing the pin's polarity latches a state change into the WU
	 * bit, so when configuring the pin we need to clear the state
	 * twice to ensure the WU bit is indicating the actual state of the
	 * pin.
	 *
	 * see example code in "Guide to a Successful EZ-USB FX2LP Hardware
	 * Design"
	 *
	 * so that we only have to run code when the state changes, rather
	 * than whenever the pin is active, we switch the polarity so that
	 * "active" is whatever state the pin is currently not in.  this
	 * leads to a race condition where if the pin toggles state during
	 * the time the handler code is running the state change could be
	 * missed.  a timing capacitor is on the pin, and we assume the RC
	 * time constant is long enough that the pin cannot change state in
	 * the time required to execute the handler code.  that's not
	 * guaranteed to be true:  if a "pulse" command is executed with a
	 * very long time delay, it could block the main loop from cycling
	 * for longer than the time constant on the WAKEUP pin, but that
	 * would require a remarkable set of coincidences to occur so we
	 * pretend it's impossible.  the initial polarity choice is
	 * irrelevant, if we guess wrong the first iteration through the
	 * main loop will set it properly.
	 *
	 * FIXME:  should be able to do all of this with interrupts, but it
	 * took so much screwing around to get just this much to work that
	 * I don't want to tempt fate
	 */

	WAKEUPCS = bmWU | bmDPEN | bmWUEN;
	WAKEUPCS = bmWU | bmDPEN | bmWUEN;
	ERESI = 1;	/* enable WAKEUP interrupts */
}


/*
 * ============================================================================
 *
 *                            USB Event Callbacks
 *
 * ============================================================================
 */


static void reset_fifos(void)
{
#if 0
	/* NOTE:  the technical reference manual has inconsistent
	 * information in it about the FIFORESET register.  the RESETFIFO()
	 * macro that's part of this firmware library does the sequence of
	 * writes described in the technical reference manual in its
	 * description of the register, but the macro fails to reset the
	 * fifo.  section 9.3.13 explains how to abort packets in the fifo
	 * when in autoin mode, and it explains you first switch out of
	 * autoin mode, then do a sequence of writes to FIFORESET.  that
	 * sequence of writes is not what the register documentation shows
	 * but in my experiments it *does* reset the fifo.  this firmware
	 * never puts the chip into autoin mode, so switching out and back
	 * into that mode is not done here, but still the reset sequence
	 * works (it's the only thing I've found that works). */
	RESETFIFO(0x02);
	RESETFIFO(0x06);
#else
	SYNCDELAY;
	FIFORESET = 0x80;
	SYNCDELAY;
	FIFORESET = 0x06;
	SYNCDELAY;
	FIFORESET = 0x02;
	SYNCDELAY;
	FIFORESET = 0x00;
	SYNCDELAY;
#endif
}


/*
 * handle "get descriptor" requests.  return FALSE to fall back to the
 * default handler, which returns the contents of the dscr.a51 file.
 */


BOOL handle_get_descriptor(void)
{
	return FALSE;
}


/*
 * handle "get interface" requests.  set *alt_ifc to the index of the
 * current alternate setting for interface ifc.  return TRUE to report
 * that *alt_ifc has been set.
 */


BOOL handle_get_interface(BYTE ifc, BYTE *alt_ifc)
{
	(void) ifc;	/* silence unused argument warning */
	/* we only support one setting, index 0 */
	*alt_ifc = 0;
	return TRUE;
}


/*
 * handle "set interface" requests.  selects from among several alternate
 * settings for an interface.  must reconfigure and reset the endpoints to
 * match the interface descriptor for this interface entry in the
 * descriptor that was provided, even if nothing changes.  return TRUE to
 * report that it was done.
 */


BOOL handle_set_interface(BYTE ifc, BYTE alt_ifc)
{
	/* we only support one interface, index 0, and one alternate
	 * setting, setting 0  */
	if(ifc == 0 && alt_ifc == 0) {
		/* reset toggles */
		RESETTOGGLE(0x02);
		RESETTOGGLE(0x86);
		/* reset and re-arm the end-point fifos */
		reset_fifos();
		arm_out_endpoint();
		arm_out_endpoint();
		/* reset the programmer and command processor */
		allpro88_hard_reset();
		return TRUE;
	}

	return FALSE;
}


/*
 * handle "get configuration" requests.  return the current configuration.
 */


BYTE handle_get_configuration(void)
{
	/* we only support one configuration, number 1 */
	return 1;
}


/*
 * handle "set configuration" requests.  return TRUE if it was successful.
 * NOTE that all endpoints must be reset when the configuration changes.
 */


BOOL handle_set_configuration(BYTE cfg)
{
	/* we only support one configuration, number 1 */
	if(cfg == 1) {
		/* reset toggles */
		RESETTOGGLE(0x02);
		RESETTOGGLE(0x86);
		/* reset and re-arm the end-point fifos */
		reset_fifos();
		arm_out_endpoint();
		arm_out_endpoint();
		/* reset the programmer and command processor */
		allpro88_hard_reset();
		return TRUE;
	}
	return FALSE;
}


/*
 * handle "vendor command".
 */


BOOL handle_vendorcommand(BYTE cmd)
{
	(void) cmd;	/* silence unused argument warning */
	/* no vendor commands supported */
	return FALSE;
}


/*
 * ============================================================================
 *
 *                               Bus Operations
 *
 * ============================================================================
 */


/*
 * bus definitions
 */


/*
 * parallel bus.  from 1 to 32 channels, three states, "true", "false" and
 * "float".  the host must, itself, configure VTH for read-back of the bus
 * pin states.  if pin DACs are required for any of the states, it must
 * also configure those.
 */


struct bus_parallel {
	/* pin config for "true" state */
	enum ALLPRO88_PINCON_BITS state_true;
	/* pin config for "false" state */
	enum ALLPRO88_PINCON_BITS state_false;
	/* pin config for "float" state */
	enum ALLPRO88_PINCON_BITS state_float;
	/* size of bus in bits */
	BYTE width;
	/* channel addresses for bits from least significant to most
	 * significant. */
	WORD bit_addr[32];
};


/*
 * preallocated array of bus definitions.  each entry in the array is a
 * union of bus structures.  host code must remember what buses it has
 * defined, and what type each is or nonsense will ensue.
 */


__xdata static union {
	struct bus_parallel parallel;
} bus[8];


/*
 * ====
 * parallel bus operations
 * ====
 */


/*
 * parse the bus definition command string
 */


static void bus_parallel_define(BYTE bus_number, const char *s)
{
	BYTE i;
	BYTE width;
	/* parse pin config register values and bus width */
	bus[bus_number].parallel.state_true = str_to_byte(s);
	s += 2;
	bus[bus_number].parallel.state_false = str_to_byte(s);
	s += 2;
	bus[bus_number].parallel.state_float = str_to_byte(s);
	s += 2;
	bus[bus_number].parallel.width = width = str_to_byte(s);
	s += 2;
	/* check for error */
	if(errno || width < 1 || width > 32)
		goto error;
	/* parse channel numbers */
	for(i = 0; i < width; i++) {
		BYTE channel = str_to_byte(s);
		s += 2;
		/* check for error */
		if(errno || channel > 87)
			goto error;
		bus[bus_number].parallel.bit_addr[i] = allpro88_channel_addr(channel);
	}
	/* check for correct end of string */
	if(*s)
		goto error;
	/* fill unused addresses with a safe value, just in case */
	for(; i < 32; i++)
		bus[bus_number].parallel.bit_addr[i] = bus[bus_number].parallel.bit_addr[0];
	/* done */
	return;

error:
	/* disable the use of this bus as a parallel bus */
	bus[bus_number].parallel.state_true = PINCON_DISABLE;
	bus[bus_number].parallel.state_false = PINCON_DISABLE;
	bus[bus_number].parallel.state_float = PINCON_DISABLE;
	bus[bus_number].parallel.width = 0;
	return;
}


/*
 * set all pins to "float" state
 */


static void bus_parallel_float(BYTE bus_number)
{
	enum ALLPRO88_PINCON_BITS state_float = bus[bus_number].parallel.state_float;
	BYTE width = bus[bus_number].parallel.width;
	WORD *bit_addr = bus[bus_number].parallel.bit_addr;

	do
		allpro88_write(*(bit_addr++), state_float);
	while(--width);
}


/*
 * read a byte, word, dword from the bus (which function is called depends
 * on the bus width).  NOTE:  these functions do bad things if width < 1,
 * which is what the bus definition command leaves it set to if that fails,
 * so the calling code needs to check for that before calling these
 */


static BYTE bus_parallel_read_byte(BYTE bus_number)
{
	BYTE width = bus[bus_number].parallel.width;
	WORD *bit_addr = bus[bus_number].parallel.bit_addr;
	BYTE value = 0;
	BYTE test_bit = 1;

	do {
		if(allpro88_read(*(bit_addr++)) & 1)
			value |= test_bit;
		test_bit <<= 1;
	} while(--width);

	return value;
}


static WORD bus_parallel_read_word(BYTE bus_number)
{
	BYTE width = bus[bus_number].parallel.width;
	WORD *bit_addr = bus[bus_number].parallel.bit_addr;
	WORD value = 0;
	WORD test_bit = 1;

	do {
		if(allpro88_read(*(bit_addr++)) & 1)
			value |= test_bit;
		test_bit <<= 1;
	} while(--width);

	return value;
}


static DWORD bus_parallel_read_dword(BYTE bus_number)
{
	BYTE width = bus[bus_number].parallel.width;
	WORD *bit_addr = bus[bus_number].parallel.bit_addr;
	DWORD value = 0;
	DWORD test_bit = 1;

	do {
		if(allpro88_read(*(bit_addr++)) & 1)
			value |= test_bit;
		test_bit <<= 1;
	} while(--width);

	return value;
}


/*
 * write a byte, word, dword to the bus (which function is called depends
 * on the bus width).  NOTE:  these functions do bad things if width < 1,
 * which is what the bus definition command leaves it set to if that fails,
 * so the calling code needs to check for that before calling these
 */


static void bus_parallel_write_byte(BYTE bus_number, BYTE value)
{
	enum ALLPRO88_PINCON_BITS state_true = bus[bus_number].parallel.state_true;
	enum ALLPRO88_PINCON_BITS state_false = bus[bus_number].parallel.state_false;
	BYTE width = bus[bus_number].parallel.width;
	WORD *bit_addr = bus[bus_number].parallel.bit_addr;

	do {
		allpro88_write(*(bit_addr++), (value & 1) ? state_true : state_false);
		value >>= 1;
	} while(--width);
}


static void bus_parallel_write_word(BYTE bus_number, WORD value)
{
	enum ALLPRO88_PINCON_BITS state_true = bus[bus_number].parallel.state_true;
	enum ALLPRO88_PINCON_BITS state_false = bus[bus_number].parallel.state_false;
	BYTE width = bus[bus_number].parallel.width;
	WORD *bit_addr = bus[bus_number].parallel.bit_addr;

	do {
		allpro88_write(*(bit_addr++), (value & 1) ? state_true : state_false);
		value >>= 1;
	} while(--width);
}


static void bus_parallel_write_dword(BYTE bus_number, DWORD value)
{
	enum ALLPRO88_PINCON_BITS state_true = bus[bus_number].parallel.state_true;
	enum ALLPRO88_PINCON_BITS state_false = bus[bus_number].parallel.state_false;
	BYTE width = bus[bus_number].parallel.width;
	WORD *bit_addr = bus[bus_number].parallel.bit_addr;

	do {
		allpro88_write(*(bit_addr++), (value & 1) ? state_true : state_false);
		value >>= 1;
	} while(--width);
}


/*
 * ============================================================================
 *
 *                              Pulse A Channel
 *
 * ============================================================================
 */


/*
 * Set channel's configuration to config;  hold it for some number of
 * microseconds;  then set the configuration to final_config.
 */


static void pulse(BYTE channel, WORD microseconds, BYTE config, BYTE final_config)
{
	WORD addr = allpro88_channel_addr(channel);
	(microseconds);	/* silence unreference parameter warning */
	/* measured shortest pulse duration is bout 4 us, so subtract that
	 * much off the count.  need to do this in assembly, because the
	 * SDCC optimizer thinks microseconds is unused and removes all the
	 * code.  the loop, below, needs microseconds to be >= 1 or it will
	 * do bad things, so that's why the math looks a bit weird.  what
	 * follows is
	 *
	 * if(microseconds <= 5)
	 *	microseconds = 1;
	 * else
	 *	microseconds -= 4;
	 */
__asm
	clr	c
	mov	a, #0x05
	subb	a, _pulse_PARM_2
	clr	a
	subb	a, (_pulse_PARM_2 + 1)
	jc	00002$
	mov	_pulse_PARM_2, #0x01
	mov	(_pulse_PARM_2 + 1), #0x00
	sjmp	00003$
00002$:
	mov	a, _pulse_PARM_2
	add	a, #0xfc
	mov	_pulse_PARM_2, a
	mov	a, (_pulse_PARM_2 + 1)
	addc	a, #0xff
	mov	(_pulse_PARM_2 + 1), a
00003$:
	clr	c
__endasm;

	allpro88_write(addr, config);

	/* this is
	 *
	 * while(--microseconds);
	 *
	 * SDCC actually compiles that loop to a much more efficient form,
	 * but it has two problems:  (i) it's too fast, but that's easily
	 * fixed with some NOP's, and (ii) it's not a constant number of
	 * instructions cycles, it takes different lengths of time
	 * depending on how the carries work out in the decrement.  this
	 * code below is a fixed 12 instruction cycles.  1 instruction
	 * cycle = 4 clock cycles.  at 48 MHz, 12 instruction cycles = 1
	 * us.
	 *
	 * the two move operations are 4 extra cycles = 333 ns, which is
	 * approximately exactly the amount by which the pulse generated by
	 * this code exceeds the requested duration.  if they could be
	 * moved to before the allpro88_write() call above, if we could
	 * guarantee the registers being used won't get screwed up by the
	 * function call, then the pulse length could be made very
	 * precisely the requested number of microseconds.  alternatively,
	 * a bunch of nop's could be added to round the total overhead up
	 * to 5 us, and then subtract that much above as the minimum pulse
	 * length
	 */
__asm
	mov	r4, _pulse_PARM_2
	mov	r5, (_pulse_PARM_2 + 1)
00001$:
	mov	a, r4		; 1 cycle
	subb	a, #1		; 2 cycles
	mov	r4, a		; 1 cycle
	mov	a, r5		; 1 cycle
	subb	a, #0		; 2 cycles.  clears carry flag
	mov	r5, a		; 1 cycle
	orl	a, r4		; 1 cycle
	jnz	00001$		; 3 cycles
__endasm;

	allpro88_write(addr, final_config);
}


/*
 * ============================================================================
 *
 *                             Command Processor
 *
 * ============================================================================
 */


/*
 * return TRUE if the "out" (data from the computer) end-point's buffer is
 * not empty (one or more commands are waiting to be processed)
 */


inline static BOOL out_buffer_not_empty(void)
{
	return !(EP2468STAT & bmEP2EMPTY);
}


/*
 * return TRUE if the "in" (data to the computer) end-point's buffer is not
 * full, i.e., can accept more data.
 */


inline static BOOL in_buffer_not_full(void)
{
	return !(EP2468STAT & bmEP6FULL);
}


/*
 * parse commands from "out" end-point
 *
 * command format.  all numbers are in base 16, only upper-case numerals
 * are recognized, and the numbers must be the width indicated (with
 * leading 0's as needed).  all commands are terminated by newline, \n,
 * 0x0a.  a packet may contain multiple commands, their outputs will be
 * concatenated into a single response packet.  commands may not straddle
 * packet boundaries.
 *
 * =XXXXYY	write YY to address XXXX
 * ?XXXX	read address XXXX, report the value as YY
 * BXT<cmd>	bus commands, use bus number X for command.  bus type, T,
 *		is one of 'P' (parallel bus), FIXME add more
 * C		report 16-bit installed-channel-group bit map as XXXX
 * EXXXX	echo the number XXXX (loop-back test)
 * MXX		run voltage measurement sequence on channel XX, report VTH
 *		DAC as YY
 * PXXYYYYAABB	pulse channel XX to state AA for YYYY microseconds,
 *		returning to state BB
 * V  		run VADJ voltage measurement sequence report VADJTH DAC as
 *		YY
 *
 * bus commands:
 *
 * P (parallel bus) commands:
 *
 * :ttffzzwwC1..CN	define bus
 *	tt : pin configuration register value for "true" state
 *	ff : pin configuration register value for "false" state
 *	zz : pin configuration register value for "float" state
 *	ww : width of bus in bits, 0x01 <= width <= 0x20
 *	C1..CN : channel number for bit n (least significant to most
 *		significant).  must supply exactly as many as the bus width
 *		(no more, no less).
 *
 * =XX..XX	set the bus to XX..XX.  the bits to use are determined by
 *		the bus width, using the least significant portion of the
 *		supplied number.  for bus widths <= 8 a two-digit number is
 *		required;  otherwise for bus widths <= 16 a four-digit
 *		number is required;  otherwise an eight-digit number is
 *		required.
 *
 * ?		read the bus, report the value.  the number of digits in
 *		the number reported depends on the width of the bus.  for
 *		bus widths <= 8 a two-digit number is reported;  otherwise
 *		for bus widths <= 16 a four-digit number is reported;
 *		otherwise an eight-digit number is reported.  in all cases,
 *		unused high bits are set to 0.
 *
 * -		set all bus pins to "float" state
 *
 * response format.  all numbers are in hexadecimal format.  responses are
 * separated by newline, \n, 0x0a, characters.  each packet of commands
 * produces one packet of responses, which might be empty (zero length).
 * the responses are in the order of the commands that produced them.
 */


static void do_command(const char *command)
{
	errno = FALSE;
	switch(command[0]) {
	/*
	 * write byte to address
	 */

	case '=': {
		/* decode address and byte */
		WORD addr = str_to_word(&command[1]);
		BYTE val = str_to_byte(&command[5]);
		/* check for error and correct end of string */
		if(errno || command[7])
			goto error;
		/* write byte to address */
		allpro88_write(addr, val);
		break;
	}

	/*
	 * read byte from address
	 */

	case '?': {
		/* decode address */
		WORD addr = str_to_word(&command[1]);
		/* check for error and correct end of string */
		if(errno || command[5])
			goto error;
		/* read from address, print byte into response */
		puts_byte(allpro88_read(addr));
		newline();
		break;
	}

	/*
	 * bus commands
	 */

	case 'B': {
		BYTE bus_number = hex_to_val(command[1]);
		if(errno)
			goto error;
		switch(command[2]) {
		/*
		 * parallel bus
		 */

		case 'P': {
			BYTE width = bus[bus_number].parallel.width;
			switch(command[3]) {
			/*
			 * define bus
			 */

			case ':':
				bus_parallel_define(bus_number, &command[4]);
				break;

			/*
			 * read from bus
			 */

			case '?':
				/* check for correct end of string */
				if(command[4])
					goto error;
				/* report the value on the bus */
				if(!width)
					goto error;
				else if(width <= 8)
					puts_byte(bus_parallel_read_byte(bus_number));
				else if(width <= 16)
					puts_word(bus_parallel_read_word(bus_number));
				else
					puts_dword(bus_parallel_read_dword(bus_number));
				newline();
				break;

			/*
			 * write to bus
			 */

			case '=':
				if(!width)
					goto error;
				else if(width <= 8) {
					/* decode the number to write */
					BYTE value = str_to_byte(&command[4]);
					/* check for error and correct end of string */
					if(errno || command[6])
						goto error;
					/* set the bus state */
					bus_parallel_write_byte(bus_number, value);
				} else if(width <= 16) {
					/* decode the number to write */
					WORD value = str_to_word(&command[4]);
					/* check for error and correct end of string */
					if(errno || command[8])
						goto error;
					/* set the bus state */
					bus_parallel_write_word(bus_number, value);
				} else {
					/* decode the number to write */
					DWORD value = str_to_dword(&command[4]);
					/* check for error and correct end of string */
					if(errno || command[12])
						goto error;
					/* set the bus state */
					bus_parallel_write_dword(bus_number, value);
				}
				break;

			/*
			 * float the bus
			 */

			case '-':
				if(!width || command[4])
					goto error;
				bus_parallel_float(bus_number);
				break;

			/*
			 * unrecognized parallel bus command
			 */

			default:
				break;
			}
			break;
		}

		/*
		 * unrecognized bus type
		 */

		default:
			break;
		}
		break;
	}

	/*
	 * report installed channel-driver bit map
	 */

	case 'C': {
		/* check for correct end of string */
		if(command[1])
			goto error;
		puts_word(installed_channel_drivers);
		newline();
		break;
	}

	/*
	 * loop-back test
	 */

	case 'E': {
		/* decode the 16 bit number to echo */
		WORD addr = str_to_word(&command[1]);
		/* check for error and correct end of string */
		if(errno || command[5])
			goto error;
		/* echo the number */
		puts_word(addr);
		newline();
		break;
	}

	/*
	 * pin voltage measurement
	 */

	case 'M': {
		/* decode the 8 bit channel number */
		BYTE channel = str_to_byte(&command[1]);
		/* check for error and correct end of string */
		if(errno || command[3])
			goto error;
		/* measure the voltage, report the VTH DAC value */
		puts_byte(allpro88_measure_pin_voltage(channel));
		newline();
		break;
	}

	/*
	 * pulse
	 */

	case 'P': {
		BYTE channel = str_to_byte(&command[1]);
		WORD microseconds = str_to_word(&command[3]);
		BYTE config = str_to_byte(&command[7]);
		BYTE final_config = str_to_byte(&command[9]);
		if(errno || command[11])
			goto error;
		pulse(channel, microseconds, config, final_config);
		break;
	}

	/*
	 * VADJ voltage measurement
	 */

	case 'V':
		/* FIXME:  this command produces more characters of output
		 * than characters of input, so it violates the assumption
		 * that the results of the commands contained in any single
		 * input buffer can all fit into a single response buffer.
		 * there's no motivation to queue a bunch of these
		 * operations up and push them as a single command buffer,
		 * it's a once-off measurement, so it's unlikely to lead to
		 * problems, but at the moment there are no safety checks
		 * in place to guarantee it doesn't lead to problems */
		/* check for correct end of string */
		if(command[1])
			goto error;
		/* measure the voltage, report the VADJTH DAC value */
		puts_byte(allpro88_measure_vadj_voltage());
		newline();
		break;

	/*
	 * unrecognized command
	 */

	default:
		break;
	}

error:
	return;
}


inline static void parse_out_buffer(void)
{
	char *command = EP2FIFOBUF;
	WORD n;

	/* initialize autopointer 1 to the start address of end-point 2's
	 * ("out") buffer and autopointer 2 to the start address of
	 * end-point 6's ("in") * buffer */

	AUTOPTRH1 = MSB(EP2FIFOBUF);
	AUTOPTRL1 = LSB(EP2FIFOBUF);
	AUTOPTRH2 = MSB(EP6FIFOBUF);
	AUTOPTRL2 = LSB(EP6FIFOBUF);

	/* loop over contents of out buffer.  some commands produce output
	 * that is put into the in buffer.  the maximum length of any
	 * command's output is shorter than the shortest output-generating
	 * command, therefore we assume the output of all commands in a
	 * single packet will fit into a single packet and don't bother
	 * including any logic to handle otherwise */

	for(n = MAKEWORD(EP2BCH, EP2BCL); n; n--)
		/* search for end of command character */
		if(XAUTODAT1 == '\n') {
			/* null terminate the command and interpret */
			char __xdata *next_cmd = (char __xdata *) MAKEWORD(AUTOPTRH1, AUTOPTRL1);
			*(next_cmd - 1) = 0;
			do_command(command);
			/* reset state for next command */
			command = next_cmd;
		}

	/* arm the in end-point to send it to the host.  we do this even if
	 * it's empty (byte count = 0) so that code running on the host
	 * always gets a response for every packet it sends. */

	arm_in_endpoint();

	/* re-arm the "out" end-point so we can receive another buffer */

	arm_out_endpoint();
}


/*
 * ============================================================================
 *
 *                               Debug Helpers
 *
 * ============================================================================
 */


/*
 * blinks an LED connected in series with a current limit resistor between
 * VCC and port A bit 0 (ALLPRO 88 address bus bit 0) at 1 Hz.  some FX2
 * development boards include such an LED.  it might need to be enabled
 * using a jumper.
 */


#if 0	/* not used */
static void blink_A0_1hz(void)
{
	ALLPRO88_ADDR_SET(0);
	delay(500);
	ALLPRO88_ADDR_SET(1);
	delay(500);
}
#endif


/*
 * blinks the ALLRPO 88's green idle LED at 1 Hz.
 */


#if 0	/* not used */
static void blink_idle_1hz(void)
{
	allpro88_set_PCR(PCR_NIDLE);
	delay(500);
	allpro88_set_PCR(PCR_DISABLE);
	delay(500);
}
#endif


/*
 * ============================================================================
 *
 *                                 Main Loop
 *
 * ============================================================================
 */


void main_loop(void)
{
	/* uncomment this to blink an LED connected to bit 0 of the ALLPRO
	 * 88 address bus (FX2 chip's port A bit 0) at 1 Hz */

	/*blink_A0_1hz();*/

	/* uncomment to blink the green idle LED at 1 Hz */

	/*blink_idle_1hz();*/

	/* check state of WAKEUP pin (monitors USB VBUS). */

	if(WAKEUPCS & bmWU) {
		/* WAKEUP pin state has changed */

		if(WAKEUPCS & bmWUPOL) {
			/* low-->high transition occured */
			/* USB cable is connected and host is powered;
			 * ensure pull-up resistor is connected to D+ */

			USBCS &= ~bmDISCON;

			/* clear latched WAKEUP pin state flag, and change
			 * polarity to active low */
			WAKEUPCS = bmWU | bmDPEN | bmWUEN;
			WAKEUPCS = bmWU | bmDPEN | bmWUEN;
		} else {
			/* high-->low transition occured */
			/* USB cable is disconnected or host not powered.
			 * disconnect pull-up resistor from D+ to avoid
			 * back-powering host through the USB cable. */

			USBCS |= bmDISCON;
			/* FIXME:  should we do a hardware reset on the
			 * programmer?  if it gets left with power applied
			 * to pins in the socket when someone turns off
			 * their computer for the night, maybe it would be
			 * a good idea to kill power to the socket.  I
			 * don't know if that's more or less likely to
			 * damage a part that might be in the socket, and
			 * what if the disconnect is just a momentary bad
			 * connection on the cable, if it might damage a
			 * part to do a hardware reset that would suck. */

			/* clear latched WAKEUP pin state flag, and change
			 * polarity to active high */
			WAKEUPCS = bmWU | bmWUPOL | bmDPEN | bmWUEN;
			WAKEUPCS = bmWU | bmWUPOL | bmDPEN | bmWUEN;
		}
	}

	/* if command data is available and there is room for output,
	 * process */

	if(out_buffer_not_empty() && in_buffer_not_full())
		parse_out_buffer();
}
