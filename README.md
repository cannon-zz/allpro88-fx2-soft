# Cypress FX2 Based Controller for Logical Devices' ALLPRO88 Software-Driven Device Programmer

## Overview

This repository contains the firmware for a Cypress FX2 based USB controller board for Logical Devices' ALLPRO88 software-driven device programmers, as well as a collection of host-side software for working with the programmer via that controller.

See https://github.com/cannon-zz/allpro88-fx2-hard for information about the hardware side of this project.

## Compile the Firmware

Compiling the firmware requires `sdcc`.  Debian users can install `sdcc` using apt.

Then, in the `fw/` directory,

1.  To generate a new serial number to serve as a unique ID run

		$ rm serial.a51 ; make serial.a51

	NOTE:  each unit requires a unique serial number to allow calibration data to be associated with the correct unit.  If you know the original serial number for your unit and would like to use that instead of a randomly generated UUID, then isntead run, for example,

		$ echo "12345" | python3 gen_serial.py >serial.a51

	using, of course, your actual serial number

	NOTE:  the serial number will be used to generate file names, and displayed in messages to the user, therefore it must be a string compatible with these applications.  Stick to printable ascii characters only, no whitespace and no slashes.

2.  After the serial number file has been generated, compile the firmware with

		$ make

	The compiled firmware is in `fw/build/firmware.ihx`.

## Install the Firmware

Programming the device requires the `fxload` tool.  Debian users can install the `fxload` package with apt.

For runtime single-use only (firmware gets installed into RAM by the host after the programmer has been powered up), use, for example,

	$ fxload -t fx2lp -D /dev/bus/usb/001/008 -I build/firmware.ihx

To write the firmware into the onboard EEPROM, use, for example,

	$ fxload -t fx2lp -D /dev/bus/usb/001/008 -I build/firmware.ihx -c 0x01 -s Vend_Ax.hex

In both cases, of course, choose the appropriate USB device file.

The `Vend_Ax.hex` file can be found in the `fw/` directory.

NOTE:  the FX2 must detect the presence of the EEPROM at boot or the chip will refuse to write to it.  It doesn't have to have firmware in it but the EEPROM must be enabled, it must see that the chip is at the expected address.  It's not possible to power up the FX2 with the EEPROM disabled, then install the jumper and write firmware to the EEPROM.  That means that because buggy firmware can make the FX2 unresponsive (ask me how I know), if buggy firmware gets into the EEPROM and bricks the board there is no way to fix it using only software on the PC --- it really is bricked.  You're forced to power up the board with the EEPROM active if you want to write new firmware to it, but you can't if it contains buggy firmware.  If that happens, you'll need to remove the EEPROM, use the command above to boot the FX2 with firmware in RAM then reprogram or erase the EEPROM using the ALLPRO88.  It might be possible to boot the FX2 with the EEPROM disabled, with firmware loaded by the PC into RAM as above, and then use the ALLPRO88 to program the EEPROM in circuit.  DO NOT use the I2C EEPROM programming script in this project, as is, to do that as that will try to apply power to the part.  Think very carefully about what you're doing if you try this.

## USB Device Permissions

In the `fw/` directory is a file named `99-allpro88.rules`.  On a Debian system, put this file into `/etc/udev/rules.d/` so that when the ALLPRO88 is plugged into a USB port the corresponding USB device file is readable and writable by normal users.

## Test and Calibrate your ALLPRO88

The `utils/` directory is a mess, it's a work in progress.

### Loopback Test

In `utils/` there is a `loopback.py` script.  With the ALLPRO88 plugged in and powered, running this script will confirm that communication with the system is working.  It does some I/O operations, confirms that they do the right thing, and reports the speed.

Confirm that the socket module and the list of installed channels reported by this script is what you expect these things to be.

### Self Test

In `utils/` there is a `self_test.py` script.  With the ALLPRO88 plugged in and powered, running this script will perform a sequence of tests on each pin driver.  It will print a log of test results to the terminal and dump a series of diagnostic plots into the directory in which it's running.  Many of the tests will report FAILURE.  At this time this is still normal for perfectly working units.  I don't have the pass/fail thresholds dialed in properly yet.  You need to look at the numbers yourself, see what values they tend to be, and decide if you think any channels appear to be different from the others or if they don't seem to be doing the right thing.  Look at the diagnostic plots and flip through them looking for a channel whose graphs are different from the others.  If they all seem to be the same, probably it's working.

The pull-up voltage ramp graphs, in particular, are an especially sensitive way to detect faults in the pin driver circuits.  Look for graphs whose slopes are different from the rest, or graphs that plateau at some maximum voltage instead of continuing all the way to the top.

### Calibration

If everything seems to be in order it's time to do a calibration.  There are two steps to this:  (i) calibrating the main power supplies, done by hand using a voltmeter, and (ii) calibrating the pin driver circuits with an automatic self-calibration procedure.

The first part, calibrating the main power supplies, is very time consuming.  Right now the code is set up to semi-automate this for me using a voltmeter for which I have a PC interface.  That almost certainly won't work for you, so assume that you cannot calibrate the main power supplies.  Yet.  Unless something is broken the ALLPRO88 should actually be pretty accurately dialed in from the factory, even after all these years.  I own two and both were basically fine.  The calibration polynomials that would be measured here just squeeze that extra little 0.05 V of precision out them.

The second part, calibrating the pin driver circuits, is also very time consuming but it is fully automatic.  It works by assuming the main power supplies are calibrated, and then the ALLPRO88's own analogue voltage measurements are used to infer biases, offsets, and non-linearities in the pin driver circuits.

This entire process is also accomplished using the `self_test.py` script.  Check the command line options for more information.

When completed, the calibration process will write the calibration data to a file keyed to the ALLPRO88 unit (the serial number is in the filename).  Put this file into some directory and set the `ALLPRO88_CAL_PATH` environment variable to that directory's name.  After, that calibration data should be loaded automatically by any tool using the programmer.

## Credit

The Cypress FX2 firmware in this project was developed from a firmware template forked from

https://github.com/djmuhlestein/fx2lib.git

and is periodically synchronized with that project.  Relevant patches will be contributed back to that project.

This wouldn't have been possible without the kind generous work of that project's developers!
