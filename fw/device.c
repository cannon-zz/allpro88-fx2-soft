/**
 * Copyright (C) 2020-2022 Kipp Cannon
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
 * convert base 16 strings of various fixed lengths to numerical values
 */


static BYTE hex_to_val(char digit)
{
	digit -= '0';
	if((signed char) digit < 0)
		goto error;
	if(digit > 9) {
		/* map 'a' through 'f' to upper case */
		digit &= ~0x20;
		/* convert to value */
		digit -= 'A' - '0' - 10;
		if((signed char) digit < 10 || digit > 0xf)
			goto error;
	}
	return digit;
error:
	errno = TRUE;
	return 0;
}


static BYTE str_to_byte(const char *str)
{
	return hex_to_val(str[0]) << 4 | hex_to_val(str[1]);
}


static WORD str_to_word(const char *str)
{
	return MAKEWORD(str_to_byte(str), str_to_byte(str + 2));
}


/*
 * write a null-terminated string without the terminator character.
 * assumes AUTOPTR2 is set to the destination.  the length of the string
 * including its null terminator must be less than 256 characters.
 */


static void puts(const char *str)
{
	BYTE i;
	for(i = 0; str[i]; i++)
		XAUTODAT2 = str[i];
}


/*
 * write integers to base 16 strings of various fixed lengths.  assumes
 * AUTOPTR2 is set to the destination.
 */


static void puts_byte(BYTE val)
{
	static const char hex_digit[] = {'0', '1', '2', '3', '4', '5', '6', '7', '8', '9', 'A', 'B', 'C', 'D', 'E', 'F'};
	XAUTODAT2 = hex_digit[val >> 4];
	XAUTODAT2 = hex_digit[val & 0xf];
}


static void puts_word(WORD val)
{
	puts_byte(MSB(val));
	puts_byte(LSB(val));
}


/*
 * write a newline character.  assumes AUTOPTR2 is set to the destination.
 */


static void newline(void)
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
static void ALLPRO88_ADDR_SET(WORD addr)
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


static void allpro88_set_PCR(enum ALLPRO88_PCR_BITS val)
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


static void allpro88_set_VADJ(BYTE vdac)
{
	allpro88_write(0x0302, vdac);
}


/*
 * set the VADJTH voltage DAC.  the voltage will be
 *
 * VADJTH = 0.1 * vdac
 */


static void allpro88_set_VADJTH(BYTE vdac)
{
	allpro88_write(0x0303, vdac);
}


/*
 * set the VTH voltage DAC.  the voltage will be
 *
 * VTH = 0.1 * vdac
 */


static void allpro88_set_VTH(BYTE vdac)
{
	allpro88_write(0x0301, vdac);
}


/*
 * set the VSR voltage DAC.  the voltage will be
 *
 * VSR = 0.1 * vdac
 */


static void allpro88_set_VSR(BYTE vdac)
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


static void allpro88_set_VPUL(BYTE vdac)
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


static void allpro88_set_VTST(BYTE vdac, BYTE idac)
{
	allpro88_write(0x0386, vdac);
	allpro88_write(0x0387, idac);
}


/*
 * start address for the control registers for a pin
 */


static WORD allpro88_pin_addr(BYTE pin)
{
	/* pin 0 starts at 0x0000, 1 at 0x0010, etc., up to pin 0x27 which
	 * starts at 0x0270, then pin 0x28 starts at 0x0400, and they
	 * continue in order from there, upto and including pin 0x57 */
	if(pin > 0x27)
		pin += 0x18;
	return (WORD) pin << 4;
}


/*
 * set the PINCON register for a pin.
 */


static void allpro88_set_PINCON(BYTE pin, enum ALLPRO88_PINCON_BITS val)
{
	/* config register is at offset 0 from the start of the register
	 * group for each pin */
	allpro88_write(allpro88_pin_addr(pin), val);
}


/*
 * set the DAC register for a pin.  the voltage will be
 *
 * VDAC = -0.5 + (0.1 * dac)
 *
 * NOTE:  the change does not take effect until the PINDAC xfer resgister
 * is written to.  see allpro88_xfer_PINDACs().
 */


static void allpro88_set_PINDAC(BYTE pin, BYTE val)
{
	/* DAC register is at offset 3 from the start of the register group
	 * for each pin */
	allpro88_write(allpro88_pin_addr(pin) + 3, val);
}


/*
 * load all pin DACs and VPUL DAC from their registers.  this causes the
 * DAC value set for each pin and for VPUL to take effect.
 */


static void allpro88_xfer_PINDACs(void)
{
	allpro88_write(0x308, 0);
}


/*
 * enable/disable the bypass capacitor for a pin.  only pins < 0x30 have
 * bypass capacitors.
 */


static void allpro88_set_PINBYPASS(BYTE pin, BOOL enable)
{
	if(pin < 0x28)
		allpro88_write(0x0280 + pin, enable);
	else if(pin < 0x30)
		allpro88_write(0x02c0 - 0x28 + pin, enable);
}


/*
 * reset the ALLPRO 88 circuitry
 */


static void allpro88_hard_reset(void)
{
	BYTE pin;

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
	for(pin = 0; pin < 88; pin++)
		allpro88_set_PINDAC(pin, 0);
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
 * use a bisection search with VTH to measure the voltage on a pin
 *
 * NOTE:  VTH is, obviously, left modified by this operation
 *
 * the VTH slew rate is about 2.5 V/us.  we need to ensure enough time
 * passes between setting VTH and reading the comparator state.  what's
 * here seems to be OK, but I've made no effort to ensure the timing is
 * good so watch for that if changes to this code are made.
 */


static BYTE allpro88_measure_pin_voltage(BYTE pin)
{
	WORD addr = allpro88_pin_addr(pin);
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


static void arm_out_endpoint(void)
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


static void arm_in_endpoint(void)
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


static void io_init(void)
{
	/* clear bits 0 and 1:  ports B and D are I/O ports, not FIFO data
	 * bus */
	IFCONFIG &= ~0x03;

	/* port A all pins for I/O port, disable alternate functions. */
	PORTACFG = 0;

	/* ALLPRO88:  zero data bus, address bus, pull /RESET low, and set
	 * /RD and /WR high. */
	IOA = 0x00;
	IOB = 0x00;
	IOD = 0xc0;

	/* float the data bus pins in case the programmer is driving them.
	 * set address and control bus pins for output (pulls /RESET low,
	 * putting programmer into reset state) */
	ALLPRO88_DATA_FLOAT;
	ALLPRO88_ADDRCTRL_DRIVE;
}


void main_init(void)
{
	/* set both IFCLK and CPU CLK to 48 MHz */
	SETCPUFREQ(CLK_48M);
	SETIF48MHZ();

	/* configure I/O ports (leaves programmer in hardware reset) */
	io_init();

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
		/* FIXME: enable this */
		/*parser_state_reset();*/
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
		/* FIXME: enable this */
		/*parser_state_reset();*/
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
 * command parser state.
 */


static struct parser_state {
	char command[8];
	BYTE command_idx;
} parser_state = {
	.command = {0},
	.command_idx = 0,
};


/*
 * reset the command parser's state.
 */


static void parser_state_reset(void)
{
	parser_state.command[0] = 0;
	parser_state.command_idx = 0;
}


/*
 * parse commands from "out" end-point
 *
 * command format.  all numbers are in base 16, and they must be the
 * width indicated.  all commands are terminated by newline, \n, 0x0a.  all
 * other whitespace is ignored.  commands may straddle packet boundaries.
 *
 * =XXXXYY	write YY to address XXXX
 * ?XXXX	read address XXXX, report the value
 * EXXXX	echo the number XXXX (loop-back test)
 * MXX		run voltage measurement sequence on channel XX, report VTH DAC
 * R		reset programmer
 * V  		run VADJ voltage measurement sequence report VADJTH DAC
 *
 * response format.  all numbers are in hexadecimal format.  responses are
 * separated by newline, \n, 0x0a, characters.  each packet of commands
 * produces one packet of responses, which might be empty (zero length).
 * the responses are in the order of the commands that produced them.
 */


static void do_command(void)
{
	errno = FALSE;
	switch(parser_state.command[0]) {
	/*
	 * write byte to address
	 */

	case '=': {
		/* decode address and byte */
		WORD addr = str_to_word(&parser_state.command[1]);
		BYTE val = str_to_byte(&parser_state.command[5]);
		/* check for error and correct end of string */
		if(errno || parser_state.command[7])
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
		WORD addr = str_to_word(&parser_state.command[1]);
		/* check for error and correct end of string */
		if(errno || parser_state.command[5])
			goto error;
		/* read from address, print byte into response */
		puts_byte(allpro88_read(addr));
		newline();
		break;
	}

	/*
	 * loop-back test
	 */

	case 'E': {
		/* decode the 16 bit number to echo */
		WORD addr = str_to_word(&parser_state.command[1]);
		/* check for error and correct end of string */
		if(errno || parser_state.command[5])
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
		BYTE pin = str_to_byte(&parser_state.command[1]);
		/* check for error and correct end of string */
		if(errno || parser_state.command[3])
			goto error;
		/* measure the voltage, report the VTH DAC value */
		puts_byte(allpro88_measure_pin_voltage(pin));
		newline();
		break;
	}

	/*
	 * reset programmer
	 */

	case 'R':
		allpro88_hard_reset();
		break;

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
		if(parser_state.command[1])
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

	for(n = MAKEWORD(EP2BCH, EP2BCL); n; n--) {
		/* retrieve the next character */
		char next = XAUTODAT1;
		if(next == '\n') {
			/* end of command.  null terminate the command
			 * buffer and interpret its contents */
			parser_state.command[parser_state.command_idx] = 0;
			do_command();
			/* reset state for next command */
			parser_state_reset();
		} else if(next < 0x21) {
			/* white space, ignore */
		} else if(parser_state.command_idx > 6) {
			/* if command buffer is full, an error has occured,
			 * reset */
			parser_state_reset();
		} else {
			/* append character to command buffer */
			parser_state.command[parser_state.command_idx++] = next;
		}
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

	/* if command data is available and there is room for output,
	 * process */

	if(out_buffer_not_empty() && in_buffer_not_full())
		parse_out_buffer();
}
