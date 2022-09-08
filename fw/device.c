/**
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


#ifdef DEBUG_FIRMWARE
#include <stdio.h>
#else
#define printf(...)
#endif


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
		digit -= 'A' - '0';
		if((signed char) digit < 0)
			goto error;
		digit += 10;
		if(digit > 0xf)
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
 * assumes AUTOPTR2 is set to the destination.
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
 * Port D[7] = /RD
 * Port D[6] = /WR
 * Port D[5] = /RESET
 *
 * the address and control lines are wired into the inputs of SN74LS244N
 * bus driver chips, and the data bus into an SN74LS245N bi-directional bus
 * driver.  those chips are gauranteed to recognize anything over 2 V as a
 * logic high level, so they should provide the required level shifting
 * from the FX2's 3.3 V logic outputs to 5 V logic inside the programmer,
 * and for the 5 V output of the 245N on the data bus when reading, the
 * FX2's documentation claims it has 5 V tolerant inputs.  the /RD line
 * controls the direction of the 245N, so be careful not to pull /RD low
 * while driving the data bus.
 *
 * NOTE:  I measure 200 Ohm between every I/O line and both +5 V and GND
 * inside the programmer.  I don't understand this.  there are Vishay
 * MDP1605 331/471G resistor arrays on the board beside the ribbon cable
 * pin header which I assume are terminating the cable.  they should have
 * 330 Ohm / 470 Ohm 2% resistors in them, one to +5 V and one to GND.  I'm
 * not sure which is which, but neither should be only 200 Ohm.  in any
 * case, there are termination resistors to both the positive supply rail
 * and ground, so regardless of what the values are there are a number of
 * consequences:
 *
 * 1.  with the FX2 chip powered down, all I/O lines should be pulled to
 * approximately 2.5 V by these resistors.  that is a problem for the FX2,
 * whose inputs must not be driven when the chip is powered off.
 * Therefore: ALWAYS APPLY POWER TO THE FX2 BOARD BEFORE APPLYING POWER TO
 * THE PROGRAMMER, AND ALWAYS REMOVE POWER FROM THE PROGRAMMER BEFORE
 * REMOVING POWER FROM THE FX2 BOARD.
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
 * chip must still sink about 12 mA and source 1 mA, so no matter what it
 * will struggle to pull pins to logic low.  to work with an unmodified
 * ALLPRO88 programmer, buffer circuits will be needed.  alternatively, the
 * termination resistors could be removed from the ALLPRO's motherboard
 * altogether, maybe replaced with something comfortably above 1.3 kOhm.
 * although the Vishay datasheet says there are resistor arrays in all
 * kinds of values, neither digikey, nor mouser, nor marutsu sells the
 * MDP1605 configuration in higher than a 680 Ohm / 680 Ohm variant.
 */


#define ALLPRO88_DATA_FLOAT do { OEA = 0x00; } while(0)
#define ALLPRO88_DATA_DRIVE do { OEA = 0xff; } while(0)
#define ALLPRO88_DATA IOA
#define ALLPRO88_ADDRCTRL_DRIVE do {OEB = OED = 0xff; } while(0)
static void ALLPRO88_ADDR_SET(WORD addr)
{
	BYTE msb;
	IOB = LSB(addr);
	msb = MSB(addr);
	PD0 = msb & 0x01;
	PD1 = msb & 0x02;
	PD2 = msb & 0x04;
	PD3 = msb & 0x08;
}

#define ALLPRO88_NRD    PD7
#define ALLPRO88_NWR    PD6
#define ALLPRO88_NRESET PD5

/* kevtris' FPGA based controller inserts, I believe, a 0.5 us delay into
 * ALLPRO port accesses.  at 48 MHz, a clock cycle is about 21 ns.  the
 * fx2's NOP instruction is 1 "instruction cycle", which the documentation
 * says is 4 clock cycles = 83.3 ns.  therefore, 6 NOP = 0.5 us.  I don't
 * know where in the read/write cycle to insert them.  see the read/write
 * functions below for explanations of the delays that get inserted. */

#define ALLPRO88_SYNC	SYNCDELAY6	/* 0.5 us @ 48 MHz CPU clock */


/*
 * read a byte from the ALLPRO 88
 */


BYTE allpro88_read(WORD addr)
{
	BYTE data;

	/* set data bus for input */
	ALLPRO88_DATA_FLOAT;
	/* drive address bus */
	ALLPRO88_ADDR_SET(addr);
	ALLPRO88_SYNC;	/* allow the bus to settle */
	/* pull /RD low */
	ALLPRO88_NRD = 0;
	ALLPRO88_SYNC;	/* allow the bus to settle */
	/* latch data bus */
	data = ALLPRO88_DATA;
	/* raise /RD */
	ALLPRO88_NRD = 1;

	return data;
}


/*
 * write a byte to the ALLPRO 88
 */


void allpro88_write(WORD addr, BYTE data)
{
	/* drive address and data bus */
	ALLPRO88_ADDR_SET(addr);
	ALLPRO88_DATA = data;
	ALLPRO88_DATA_DRIVE;
	ALLPRO88_SYNC;	/* allow the buses to settle */
	/* pull /WR low */
	ALLPRO88_NWR = 0;
	ALLPRO88_SYNC;	/* hold it to make sure it takes */
	/* raise /WR */
	ALLPRO88_NWR = 1;
}


/*
 * reset the ALLPRO 88 device
 */


void allpro88_reset(void)
{
	WORD addr;

	/* hold /RESET low */
	ALLPRO88_NRESET = 0;
	/* set /RD, /WR high (order doesn't matter) */
	ALLPRO88_NRD = ALLPRO88_NWR = 1;
	/* zero the address bus */
	ALLPRO88_ADDR_SET(0);
	/* set data bus to all zero, but float it */
	ALLPRO88_DATA = 0;
	ALLPRO88_DATA_FLOAT;
	/* wait a while (10 ms) */
	delay(10);	/* FIXME:  what delay is required?  */
	/* raise /RESET */
	ALLPRO88_NRESET = 1;

	/* FIXME:  kevtris recommends 0'ing all pin-driver DACs *before*
	 * reset.  really?  maybe after ...?  in any case this code doesn't
	 * do that (yet?), maybe it should.  his documentation says the
	 * reset line resets all the latches but doesn't modify the pin
	 * driver DACs.  they should be put into a known state before doing
	 * other configuration */
	/* FIXME: I don't know if this is needed, but this will ensure all
	 * the DACs are 0 and everything is "disabled" */
	for(addr = 0; addr < 0x0800; addr++)
		allpro88_write(addr, 0);
	for(addr = 0; addr < 0x0800; addr++)
		allpro88_write(addr, 0);
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
	PCR_ENABLE = 0x01,
	PCR_AUX = 0x02	/* unused open collector output to socket board */
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
 * in bit-bang mode, the polarity bit sets the state of the timer output.
 * otherwise, according to kevtris the polarity bit sets the state of timer
 * output when it is not toggling (don't know what that means).  FIXME:
 * figure out what that means.
 */


enum ALLPRO88_TIMER_MODE {
	TIMER_MODE_DISABLE = 0x00,
	TIMER_MODE_BITBANG = 0x01,
	TIMER_MODE_4MHZ = 0x02,
	TIMER_MODE_2MHZ = 0x03,
	TIMER_MODE_1MHZ = 0x04,
	TIMER_MODE_500KHZ = 0x05,
	TIMER_MODE_250KHZ = 0x06,
	/* NOTE:  setting mode 0x07 enables both high and low output
	 * drivers and will damage the circuit */
	TIMER_MODE_POLARITY = 0x80
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
 * the pin DAC voltages, VPUL, VTST and VPIN because is supplies all of
 * these.
 */


static void allpro88_set_VADJ(BYTE vdac)
{
	allpro88_write(0x0302, vdac);
}


/*
 * set the VPIN voltage DAC.  the voltage will be
 *
 * VPIN = 0.1 * vdac
 */


static void allpro88_set_VPIN(BYTE vdac)
{
	allpro88_write(0x0301, vdac);
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
	 * continue in order from there */
	if(pin > 0x27)
		pin += 0x18;
	return (WORD) pin << 4;
}


/*
 * set the PINCON register for a pin.
 */


static void allpro88_set_PINCON(BYTE pin, enum ALLPRO88_PINCON_BITS val)
{
	/* FIXME add safety check for valid values to avoid damage */

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
 * read pin state
 */


static BOOL allpro88_get_PINSTATE(BYTE pin)
{
	/* the pin state (above/below VPIN threshold) is read at offset 0
	 * from the start of the register group for each pin */
	return allpro88_read(allpro88_pin_addr(pin));
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


void main_init(void)
{
	/* set both IFCLK and CPU CLK to 48 MHz */
	SETCPUFREQ(CLK_48M);
	SETIF48MHZ();

	/* clear bits 0 and 1:  ports B and D are I/O ports, not FIFO data
	 * bus */
	IFCONFIG &= ~0x03;

	/* port A all pins for I/O port, disable alternate functions. */
	PORTACFG = 0;

	/* zero all ports.  asserts ALLPRO88 /RESET. */
	IOA = IOB = IOD = 0;
	/* set /RD, /WR high (order doesn't matter) */
	ALLPRO88_NRD = ALLPRO88_NWR = 1;

	/* float the data bus pins in case the programmer is driving them.
	 * set address and control bus pins for output (pulls /RESET low,
	 * putting programmer into reset state) */
	ALLPRO88_DATA_FLOAT;
	ALLPRO88_ADDRCTRL_DRIVE;

	/* programmer reset sequence (finalizes port initialization) */
	allpro88_reset();

	/* I can't figure out what to set this to.  the documentation says
	 * over and over that for basically every configuration you can
	 * imagine this must be set to 3.  it says the only affect of
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
	/*EP1OUTCFG = EP1INCFG = EP4CFG = EP8CFG = 0;*/
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
	 * show this being done twice at start-up. */

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
		RESETFIFO(0x02);
		arm_out_endpoint();
		arm_out_endpoint();
		RESETFIFO(0x86);
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
		RESETFIFO(0x02);
		arm_out_endpoint();
		arm_out_endpoint();
		RESETFIFO(0x86);
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
 * command parser state.  global variable (lazy).
 */


static struct parse_state {
	char command[8];
	BYTE command_idx;
} parse_state = {
	.command = {0},
	.command_idx = 0,
};


/*
 * parse commands from "out" end-point
 *
 * command format.  all numbers are in hexadecimal, and they must be the
 * width indicated.  all commands are terminated by newline, \n, 0x0a.
 * CTRL-C resets the parser (aborts partial command).  all other whitespace
 * is ignored.  commands may straddle packet boundaries.
 *
 * EXXXX	echo the number XXXX (loop-back test)
 * =XXXXYY	write YY to address XXXX
 * ?XXXX	read address XXXX, display value
 * DXX=YY	set pin XX's VDAC to YY
 * PXX=Y	set pin XX's config to Y
 *
 * response format.  all numbers are in hexadecimal format.  responses are
 * separated by newline, \n, 0x0a, characters.  each packet of commands
 * produces one packet of responses, which might be empty (zero length).
 * the responses are in the order of the commands that produced them.
 */


static void do_command(void)
{
	errno = FALSE;
	switch(parse_state.command[0]) {
	/*
	 * loop-back test
	 */

	case 'E':
	case 'e': {
		/* decode the 16 bit number to echo */
		WORD addr = str_to_word(&parse_state.command[1]);
		/* check for error and correct end of string */
		if(errno || parse_state.command[5])
			goto error;
		/* echo the number */
		puts_word(addr);
		break;
	}

	/*
	 * write byte to address
	 */

	case '=': {
		/* decode address and byte */
		WORD addr = str_to_word(&parse_state.command[1]);
		BYTE val = str_to_byte(&parse_state.command[5]);
		/* check for error and correct end of string */
		if(errno || parse_state.command[7])
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
		WORD addr = str_to_word(&parse_state.command[1]);
		/* check for error and correct end of string */
		if(errno || parse_state.command[5])
			goto error;
		/* read from address, print byte into response */
		puts_byte(allpro88_read(addr));
		break;
	}

	/* FIXME: add extra commands */

	default:
		/* unrecognized command */
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
	 * command's output is shorter than the shortest command, therefore
	 * we assume the output of all commands in a single packet will fit
	 * into a single packet and don't bother including any logic to
	 * handle otherwise */

	for(n = MAKEWORD(EP2BCH, EP2BCL); n; n--) {
		/* retrieve the next character */
		char next = XAUTODAT1;
		if(next == '\n') {
			/* end of command.  null terminate the command
			 * buffer and interpret its contents */
			parse_state.command[parse_state.command_idx] = 0;
			do_command();
			/* reset state for next command */
			parse_state.command[0] = 0;
			parse_state.command_idx = 0;
		} else if(next == 0x03) {
			/* CTRL-C */
			/* reset state for next command */
			parse_state.command[0] = 0;
			parse_state.command_idx = 0;
		} else if(next < 0x21) {
			/* other white space, ignore */
		} else if(parse_state.command_idx > 6) {
			/* if command buffer is full, an error has occured,
			 * reset */
			parse_state.command[0] = 0;
			parse_state.command_idx = 0;
		} else {
			/* append character to command buffer */
			parse_state.command[parse_state.command_idx++] = next;
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
 * the !RESET line and GND at 1 Hz.
 */


static void blink_nreset_1hz(void)
{
	ALLPRO88_NRESET = 0;
	delay(500);
	ALLPRO88_NRESET = 1;
	delay(500);
}


/*
 * blinks the busy LED at 1 Hz.  the busy LED is tied to the "power
 * supplies enable" bit.  turning the power supplies on and off blinks the
 * LED.
 */


static void blink_busy_1hz(void)
{
	allpro88_set_PCR(PCR_ENABLE);
	delay(500);
	allpro88_set_PCR(PCR_DISABLE);
	delay(500);
}


/*
 * sets the test voltage to 3 V, current limit 5 mA.  sets all pins of the
 * ALLPRO88 to "logic low" = 50 Ohm resistor to GND, except pin 1 which is
 * toggled between the test voltage and "logic low" at 1 Hz.  this should
 * blink an LED inserted into pins 1 and 2 of the ZIF socket at 1 Hz.
 */


static void blink_pin1_1hz(void)
{
	unsigned char pin;

	/* set VADJ to 5 V.  this is the supply voltage to the DAC outputs.
	 * it needs to be something about 2 V above what VTST will be set
	 * to.  as long as it's not too high the value doesn't matter (the
	 * higher it gets the more heat needs to be dissipated by the
	 * linear pin driver power supplies) */

	/*allpro88_set_VADJ(35);*/
	allpro88_set_VADJ(255);

	/* configure VTST.  see the function's documentation for the
	 * formulae.  we want Eout = 3 V.  26 is rounded up, so the voltage
	 * will be a bit more than 3 V. */

	/*allpro88_set_VTST(26, 5);*/
	allpro88_set_VTST(128, 255);

	/* enable all power supplies */

	allpro88_set_PCR(PCR_ENABLE);

	/* configure the pins.  first set all to logic low, wait 500 ms,
	 * then set pin 1 to (current-limited) VTST, and wait 500 ms.
	 * NOTE: pin 1 of the ZIF socket is pin driver channel 60 (ALLPRO's
	 * service manual numbers channels from 1, so in their
	 * documentation this is channel 61) */

#if 0
	for(pin = 0; pin < 88; pin++)
		allpro88_set_PINCON(pin, PINCON_LOGICL);
	allpro88_write(0x0308, 0);
	delay(500);
	allpro88_set_PINCON(60, PINCON_VTST);
	allpro88_write(0x0308, 0);
	delay(500);
#endif

	for(pin = 0; pin < 88; pin++)
		allpro88_set_PINCON(pin, PINCON_VTST);
	delay(1000);
	for(pin = 0; pin < 88; pin++)
		allpro88_set_PINCON(pin, PINCON_LOGICL);
	delay(1000);
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
	/* uncomment this to blink an LED connected to the !RESET line at
	 * 1 Hz */

	/*blink_nreset_1hz();*/

	/* uncomment to blink the busy LED at 1 Hz */

	/*blink_busy_1hz();*/

	/* uncomment this to blink an LED connected to pins 1 and 2 of the
	 * ZIF socket at 1 Hz */

	/*blink_pin1_1hz();*/

	/* if command data is available and there is room for output,
	 * process */

	if(out_buffer_not_empty() && in_buffer_not_full())
		parse_out_buffer();
}
