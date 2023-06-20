/**
 * Copyright (C) 2020-2023 Kipp Cannon
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


inline static BYTE hex_to_val(char digit)
{
	digit -= '0';
	if(digit > 9) {
		if(digit < 'A' - '0')
			goto error;
		digit -= 'A' - '0' - 10;
		if(digit > 0xF)
			goto error;
	}
	return digit;
error:
	errno = TRUE;
	return 0;
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
 * Port A = data bus
 * Port B = address bus low byte
 * Port D[0:3] = address bus bits 8,9,10,11
 * Port D[4] = activity LED / PSEN (depends on board configuration)
 * Port D[5] = /RESET
 * Port D[6] = /WR
 * Port D[7] = /RD
 *
 * the address and control lines are wired into the inputs of SN74LS244N
 * bus driver chips, and the data bus into an SN74LS245N bi-directional bus
 * driver.  those chips are guaranteed to recognize anything over 2 V as a
 * logic high level, so they should provide the required level shifting
 * from the FX2's 3.3 V logic outputs to 5 V logic inside the programmer.
 * the FX2's documentation says it has 5 V tolerant inputs, so the 5 V
 * output of the 245N on the data bus during read operations is
 * acceptable.  no level shifting is required to connect the FX2 directly
 * to the ALLPRO88's interface.  from the ALLPRO88's service manual, the
 * /RD line controls the direction of the 245N, so be careful not to pull
 * /RD low while driving the data bus.
 *
 * NOTE:  I measure 200 Ohm between every I/O line and both +5 V and GND
 * inside the programmer.  I don't understand this.  there are Vishay
 * MDP1605 331/471G resistor arrays on the board beside the ribbon cable
 * pin header which I assume are terminating the cable.  they should have
 * 330 Ohm / 470 Ohm 2% resistors in them, one to +5 V and one to GND.  I'm
 * not sure which resistor goes in which direction, but neither should be
 * only 200 Ohm.  in any case, there are termination resistors to both the
 * positive supply rail and ground, so regardless of what the values are
 * there are a number of consequences:
 *
 * 1.  with the FX2 chip powered down, all I/O lines should be pulled to
 * approximately 2.5 V by these resistors.  I had previously believed that
 * this is a problem for the FX2, because I got the impression from
 * something that its inputs must not be driven when the chip is powered
 * off, i.e., they must not be raised to a potential above the supply
 * voltage.  however, more recently I've rechecked the documentation and I
 * don't see that restriction, and anyway that would make them not 5 V
 * tolerant if it was true (the chip runs on 3.3 V).  the only restriction
 * is that the GPIO lines must not have more than 5 V to ground placed on
 * them, but there is no statement about the chip being powered when this
 * happens.  I now believe it is safe to power the programmer before
 * powering the FX2 chip.
 *
 * 2.  when an FX2 output pin is pulled low, there is only a 200 Ohm
 * resistor between it and a +5 V rail, so 25 mA of current will flow.
 * when pulled high, to about 3 V, it's only between 0.25 V and 0.5 V above
 * the potential of that node in the termination resitor array, with a 200
 * Ohm resistance to ground, so much less current will flow, about 2 mA.
 * the chip can only source or sink a maximum of 4 mA on any GPIO pin, so
 * it should have no trouble pulling the programmer's inputs to logic high
 * levels, but will not be able to pull them to logic low levels.  even if
 * I'm wrong about the resistances, and the resistor package markings give
 * the correct values, the difference is only about a factor of 2, so the
 * chip must still sink about 12 mA and source 1 mA on every GPIO line, so
 * no matter what the correct resistance really is the chip will struggle
 * to pull pins to logic low.  to work with an unmodified ALLPRO88
 * programmer, buffer circuits will be needed.  alternatively, the
 * termination resistors could be removed from the ALLPRO's motherboard
 * altogether, maybe replaced with something comfortably above 1.3 kOhm.
 * the Vishay datasheet says there are resistor arrays in all kinds of
 * values, but neither digikey, nor mouser, nor marutsu sells the MDP1605
 * configuration in higher than a 680 Ohm / 680 Ohm variant, which would
 * still not be high enough.
 *
 * I removed the termination resistors from my unit.  I replaced them with
 * sockets, so they can be re-installed or removed again easily.  they are
 * not needed in my case, anyway, because I have connected the FX2 board
 * directly to the pin header on the ALLPRO's motherboard, inside the unit,
 * so there's no ribbon cable inductance or capacitance, and only a short
 * physical signal path between the FX2's GPIO pins and the ALLPRO's bus
 * interface chips.  this also means I don't have to worry about the order
 * in which I apply power to things.  the 74LS series bus driver chips
 * tolerate normal input voltages even without power supplied to the chips,
 * so the FX2 can be powered on and driving the ALLPRO's inputs without
 * damaging them even when the ALLPRO is powered off.
 *
 * ultimately, I ended up using one of the empty sockets to get +5 V and
 * GND into a custom FX2 based controller board, which gave me even more
 * reason to want the resistor arrays removed.
 */


#define ALLPRO88_DATA_FLOAT do { OEA = 0x00; } while(0)
#define ALLPRO88_DATA_DRIVE do { OEA = 0xff; } while(0)
#define ALLPRO88_DATA IOA
#define ALLPRO88_ADDRCTRL_DRIVE do {OEB = OED = 0xff; } while(0)
inline static void ALLPRO88_ADDR_SET(WORD addr)
{
	/* the low byte of the 12 bit address */
	IOB = LSB(addr);
	/* ACT, /RD, /WR and /RESET are set high, and combined with the
	 * high nibble of the 12 bit address */
	IOD = 0xe0 | MSB(addr);
}

#define ALLPRO88_ACT    PD4
#define ALLPRO88_NRESET PD5
#define ALLPRO88_NWR    PD6
#define ALLPRO88_NRD    PD7


/*
 * read a byte from the ALLPRO 88.  notes on timing:
 *
 * 74HCT251 (pin driver comparator output register).  the comparator
 * outputs are always present on the data inputs so there is no switching
 * time to account for in that regard.  the select lines are driven by the
 * pin driver address bus which is synthesized from the external address
 * bus by TIBPAL16L8-25CN programmable logic devices which have a 25 ns
 * maximum propogation delay.  from select pins settling to output pin
 * being valid is at most about 50 ns, and from output enable pin to output
 * bin being valid is at most about 38 ns, which likely can be assumed to
 * occur concurrently.  the output enable is generated from the /RD line
 * and a board /SELECT line produced by the same programmable logic
 * devices.  these propogate through two 74HCT02 quad nor gate elements
 * before driving the output enable line, which adds an additional 52 ns of
 * delay.  from external address bus being set to 74HCT251 being ready to
 * respond to /RD is a total of about 75 ns;  from /RD being pulled low to
 * the chip's output being valid is about 90 ns.  I see no reason why this
 * can't all be occuring concurrently.  in the worst case scenario the data
 * bus undergoes some rapid switching as the HCT251's output enable goes
 * active before its select logic has settled, but as long as the receiving
 * end waits appropriately long for the dust to settle it should be fine.
 * anyway, at least 1 instruction cycle (83 ns) must elapse between setting
 * the address bus and pulling /RD low, and adding the two stages of nor
 * gate delay to that the output enable signal almost certainly can't go
 * active until after the select logic has had time to settle.
 *
 * the HCT251's output is buffered by a 74LS245 transceiver with an 8 ns
 * propagation time and about 25 ns time to change direction, so from
 * the chip's output settling to it appearing on the programmer's external
 * data bus there is an additional 32 ns.
 */


static BYTE allpro88_read(WORD addr)
{
	BYTE data;

	/* set data bus for input */
	ALLPRO88_DATA_FLOAT;
	/* drive address and pull /RD low.  no delay between the two is
	 * used, the instruction timing is sufficient.  */
	ALLPRO88_ADDR_SET(addr);
	ALLPRO88_NRD = 0;
	/* wait 83.3 ns for gate delays and bus settling */
	NOP;
	/* latch data bus */
	data = ALLPRO88_DATA;
	/* raise /RD */
	ALLPRO88_NRD = 1;

	return data;
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
 * least 320 ns prior to a low-to-high transition of /XFER, etc.
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
 * pin driver modules by a 74HCT244 with a 13 ns propagation time, so from
 * when the data bus is set it takes a worst-case time of about 46 ns
 * before the value appears on the input pins to a device.
 *
 * the /WR lines for the pin driver DAC chips and pin driver HCT273 config
 * latches are synthesized from the pin driver address bus by 74HCT138
 * 3-to-8 line decoders which have a propogation delay of up to 38 ns, and
 * the pin driver address lines are synthesized from the external address
 * by TIBPAL16L8-25CN programmable logic devices which have a 25 ns maximum
 * propogation delay, so from when the address bus is set it takes about
 * 100 ns before the /WR signal will be routed to the correct physical
 * chip.  for the HCT273's, there's an additional 74HCT02 quad nor gate
 * used as an inverter delaying one of the address lines, but because the
 * HCT273 has negligible setup and hold requirements compared to the
 * DAC0832 chips we don't bother adding anything extra for that.
 *
 * at 48 MHz, a clock cycle is about 21 ns.  the fx2's NOP instruction is 1
 * "instruction cycle", which the documentation says is 4 clock cycles =
 * 83.3 ns.  therefore, 6 NOP = 0.5 us.  kevtris' documentation also speaks
 * of inserting a 0.5 us pause in the I/O cycle, but doesn't say in what
 * part of it exactly (read, write, setup, hold?).  the DAC0832 setup time
 * for writes is likely what he means.
 */


static void allpro88_write(WORD addr, BYTE data)
{
	/* drive address.  100 ns must elapse before the internal
	 * electronics can be assumed to have figured out how to respond to
	 * this, which is about 1.5 instruction cycles.  we assume the time
	 * spent configuring the data bus takes at least this much time */
	ALLPRO88_ADDR_SET(addr);
	/* drive data bus.  about 46 ns is required before this can be
	 * assumed to be present on any device (about 0.5 instruction
	 * cycles), plus whatever time is required for it to actually
	 * stabilize.  one NOP used for the AD7226 setup time is 30 ns
	 * longer than needed, and there is the time required to actually
	 * execute the pull-/WR-low instruction, which together should
	 * provide enough total wait time for the data bus to propogate and
	 * settle, but rather than risk it I put a second NOP in (167 ns
	 * total). */
	ALLPRO88_DATA = data;
	ALLPRO88_DATA_DRIVE;
	NOP; NOP;
	/* pull /WR low.  clocks AD7226s */
	ALLPRO88_NWR = 0;
	/* hold data and /WR for 500 ns.  DAC0832 setup time */
	NOP; NOP; NOP; NOP; NOP; NOP;
	/* raise /WR.  clocks HCT273s and DAC0832s */
	ALLPRO88_NWR = 1;
	/* don't worry about final hold time.  firmware not fast enough to
	 * violate it. */
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


static void allpro88_set_PINCON(BYTE channel, enum ALLPRO88_PINCON_BITS val)
{
	/* config register is at offset 0 from the start of the register
	 * group for each channel */
	allpro88_write(allpro88_channel_addr(channel), val);
}


/*
 * set the DAC register for a channel.  the voltage will be
 *
 * VDAC = -0.5 + (0.1 * dac)
 *
 * NOTE:  the change does not take effect until the PINDAC xfer resgister
 * is written to.  see allpro88_xfer_PINDACs().
 */


static void allpro88_set_PINDAC(BYTE channel, BYTE val)
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


static void allpro88_set_PINBYPASS(BYTE channel, BOOL enable)
{
	if(channel < 0x28)
		allpro88_write(0x0280 + channel, enable);
	else if(channel < 0x30)
		allpro88_write(0x02c0 - 0x28 + channel, enable);
}


/*
 * reset the ALLPRO 88 circuitry
 */


static void allpro88_hard_reset(void)
{
	BYTE channel;

	/*
	 * the /RESET line clears all configuration registers (octal latch
	 * chips) back to 0.  we pull it low (active), clear data, address
	 * and control buses to a known safe state, wait a while, then
	 * raise /RESET to take the circuitry out of hardware reset.  we
	 * leave the data bus floating (but internally, within the FX2, set
	 * to 0), the address bus set to 0, and /RD, /WR and /RESET all
	 * high (inactive).
	 */

	/* hold /RESET low */
	ALLPRO88_NRESET = 0;
	/* set /RD, /WR high (order doesn't matter) */
	ALLPRO88_NRD = ALLPRO88_NWR = 1;
	/* set data bus to all zero, but float it */
	ALLPRO88_DATA_FLOAT;
	ALLPRO88_DATA = 0;
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
	 * zero and float the data bus again.  zero the address bus.  leave
	 * /RD, /WR and /RESET high.
	 */

	ALLPRO88_DATA_FLOAT;
	ALLPRO88_DATA = 0;
	ALLPRO88_ADDR_SET(0);
}


/*
 * use a bisection search with VTH to measure the voltage on a channel
 *
 * NOTE:  VTH is, obviously, left modified by this operation
 *
 * the VTH slew rate is about 2.5 V/us.  we need to ensure enough time
 * passes between setting VTH and reading the comparator state.  what's
 * here seems to be OK, but I've made no effort to ensure the timing is
 * good so watch for that if changes to this code are made.
 */


static BYTE allpro88_measure_pin_voltage(BYTE channel)
{
	WORD addr = allpro88_channel_addr(channel);
	BYTE vdac = 0;
	BYTE test_bit;
	for(test_bit = 0x80; test_bit; test_bit >>= 1) {
		allpro88_set_VTH(vdac | test_bit);
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
	EP2BCL = 0x80;
	SYNCDELAY;
}


inline static void arm_in_endpoint(void)
{
	/* arm end-point 6 setting the byte count to the offset of autoptr2
	 * from the start of the buffer.  write byte-count high byte first.
	 * end-point is armed when low byte is written */
	WORD n = MAKEWORD(AUTOPTRH2, AUTOPTRL2) - EP6FIFOBUF;
	EP6BCH = MSB(n);
	SYNCDELAY;
	EP6BCL = LSB(n);
	SYNCDELAY;
}


void main_init(void)
{
	/* set both IFCLK and CPU CLK to 48 MHz */

	SETCPUFREQ(CLK_48M);
	SETIF48MHZ();

	/* configure I/O ports.  clear bits 0 and 1:  ports B and D are I/O
	 * ports, not FIFO data bus.  port A all pins for I/O port, disable
	 * alternate functions. */

	IFCONFIG = 0x80;
	PORTACFG = 0;

	/* ALLPRO88:  zero data bus, address bus, pull /RESET low, and set
	 * /RD and /WR high. */

	IOA = 0x00;
	IOB = 0x00;
	IOD = 0xc0;

	/* float the data bus pins in case the programmer is driving them.
	 * set address and control bus pins for output (if it isn't
	 * already, this now for real pulls /RESET low, putting programmer
	 * into reset state) */

	ALLPRO88_DATA_FLOAT;
	ALLPRO88_ADDRCTRL_DRIVE;

	/* programmer hardware reset */

	allpro88_hard_reset();

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
	 * explicitly re-arm them for each packet.  that's what we want */

	EP1OUTCFG = 0;
	SYNCDELAY;
	EP1INCFG = 0;
	SYNCDELAY;
	EP4CFG = 0;
	SYNCDELAY;
	EP8CFG = 0;
	SYNCDELAY;
	EP2CFG = 0b10100010;	/* valid, out, bulk, 512 bytes, dbl buff'd */
	SYNCDELAY;
	EP6CFG = 0b11100010;	/* valid, in, bulk, 512 bytes, dbl buff'd */
	SYNCDELAY;

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

	/* enable autopointers.  for both, increment on access. */

	AUTOPTRSETUP = 0x07;

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


static BOOL out_buffer_not_empty(void)
{
	return !(EP2468STAT & bmEP2EMPTY);
}


/*
 * return TRUE if the "in" (data to the computer) end-point's buffer is not
 * full, i.e., can accept more data.
 */


static BOOL in_buffer_not_full(void)
{
	return !(EP2468STAT & bmEP6FULL);
}


/*
 * parse commands from "out" end-point
 *
 * command format.  all numbers are in base 16, only upper-case numerals
 * are recognized, and the numbers must be the width indicated (with
 * leading 0's as needed).  all commands are terminated by newline, \n,
 * 0x0a.  commands may not straddle packet boundaries.
 *
 * =XXXXYY	write YY to address XXXX
 * ?XXXX	read address XXXX, report the value
 * BXT<cmd>	bus commands, use bus number X for command.  bus type, T,
 *		is one of 'P' (parallel bus), FIXME add more
 * EXXXX	echo the number XXXX (loop-back test)
 * MXX		run voltage measurement sequence on channel XX, report VTH DAC
 * PXXYYYYAABB	pulse channel XX to state AA for YYYY microseconds,
 *		returning to state BB
 * V  		run VADJ voltage measurement sequence report VADJTH DAC
 *
 * bus commands:
 *
 * P (parallel bus) commands:
 *
 * :ttffzzwwC1..CN	define bus
 *	tt : pin configuration register value for "true" state
 *	ff : pin configuration register value for "false" state
 *	zz : pin configuration register value for "float" state
 *	ww : width of bus in bits, 1 <= width <= 32
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
		BYTE width = bus[bus_number].parallel.width;
		if(errno)
			goto error;
		switch(command[2]) {
		/*
		 * parallel bus
		 */

		case 'P':
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

		/*
		 * unrecognized bus type
		 */

		default:
			break;
		}
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


static void parse_out_buffer(void)
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
 * VCC and port A bit 0 (ALLPRO 88 data bus bit 0) at 1 Hz.  some FX2
 * development boards include such an LED.  it might need to be enabled
 * using a jumper.
 */


static void blink_data0_1hz(void)
{
	ALLPRO88_DATA_DRIVE;
	ALLPRO88_DATA = 0;
	delay(500);
	ALLPRO88_DATA = 1;
	delay(500);
}


/*
 * blinks the ALLRPO 88's green idle LED at 1 Hz.
 */


static void blink_idle_1hz(void)
{
	allpro88_set_PCR(PCR_NIDLE);
	delay(500);
	allpro88_set_PCR(PCR_DISABLE);
	delay(500);
}


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
	 * 88 data bus at 1 Hz */

	/*blink_data0_1hz();*/

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
