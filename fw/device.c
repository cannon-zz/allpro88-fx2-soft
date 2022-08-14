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

BOOL handle_get_descriptor(void) {
 // your custom descriptor handler code here..
 return FALSE; // FALSE = fall back to default handler
}

//************************** Configuration Handlers *****************************

// change to support as many interfaces as you need
//volatile xdata BYTE interface=0;
//volatile xdata BYTE alt=0; // alt interface

// set *alt_ifc to the current alt interface for ifc
BOOL handle_get_interface(BYTE ifc, BYTE* alt_ifc) {
// *alt_ifc=alt;
 return TRUE;
}
// return TRUE if you set the interface requested
// NOTE this function should reconfigure and reset the endpoints
// according to the interface descriptors you provided.
BOOL handle_set_interface(BYTE ifc,BYTE alt_ifc) {  
 printf ( "Set Interface.\n" );
 //interface=ifc;
 //alt=alt_ifc;
 return TRUE;
}

// handle getting and setting the configuration
// 1 is the default.  If you support more than one config
// keep track of the config number and return the correct number
// config numbers are set int the dscr file.
//volatile BYTE config=1;
BYTE handle_get_configuration(void) { 
 return 1;
}

// NOTE changing config requires the device to reset all the endpoints
BOOL handle_set_configuration(BYTE cfg) {
 printf ( "Set Configuration.\n" );
 //config=cfg;
 return TRUE;
}


//******************* VENDOR COMMAND HANDLERS **************************


BOOL handle_vendorcommand(BYTE cmd) {
 // your custom vendor handler code here..
 return FALSE; // not handled by handlers
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
 *                                 Main Loop
 *
 * ============================================================================
 */


void main_loop(void)
{
	ALLPRO88_NRESET = 0;
	delay(500);
	ALLPRO88_NRESET = 1;
	delay(500);
}
