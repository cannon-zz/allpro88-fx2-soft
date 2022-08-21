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
	(void) ifc;	/* silence unused argument warning */
	/* we only support one inteface, index 0 */
	return alt_ifc == 0;
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
	return cfg == 1;
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
	IOB = addr & 0xff;
	addr >>= 8;
	PD0 = (BYTE) addr & 0x01;
	PD1 = (BYTE) addr & 0x02;
	PD2 = (BYTE) addr & 0x04;
	PD3 = (BYTE) addr & 0x10;
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
	/* set data bus for output */
	ALLPRO88_DATA_DRIVE;
	/* drive address and data bus */
	ALLPRO88_ADDR_SET(addr);
	ALLPRO88_DATA = data;
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
	/* hold /RESET low */
	ALLPRO88_NRESET = 0;
	/* set /RD, /WR high (order doesn't matter) */
	ALLPRO88_NRD = ALLPRO88_NWR = 1;
	/* zero the address bus */
	ALLPRO88_ADDR_SET(0);
	/* set data bus to all zero */
	ALLPRO88_DATA = 0;
	ALLPRO88_DATA_DRIVE;
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


/*
 * set the PCR (power supply control register)
 */


static void allpro88_set_PCR(enum ALLPRO88_PCR_BITS val)
{
	allpro88_write(0x030c, val);
}


/*
 * ============================================================================
 *
 *                                   Setup
 *
 * ============================================================================
 */


void main_init(void)
{
	/* set both IFCLK and CPU CLK to 48 MHz */
	SETCPUFREQ(CLK_48M);
	SETIF48MHZ();

	/* clear bits 0 and 1:  I/O pins are I/O ports */
	IFCONFIG &= ~0x03;

	/* port A all pins for I/O port, disable alternate functions.
	 * not needed for B and D because no altnerate functions. */
	PORTACFG = 0;

	/* zero all ports.  includes /RESET. */
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

	/* disables auto-arming of the endpoints when AUTOOUT transitions
	 * from 0 to 1.  allow CPU to edit/source in and out packets */
	REVCTL = 3;

	/* endpoints 2 and 6 enabled, 1, 4 and 8 disabled */
	EP1OUTCFG = EP1INCFG = EP4CFG = EP8CFG = 0;
	EP2CFG = 0xa0;	/* valid, out, bulk (max packet = 512 bytes) */
	EP6CFG = 0xe0;	/* valid, in, bulk (max packet = 512 bytes) */
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

	blink_busy_1hz();
}
