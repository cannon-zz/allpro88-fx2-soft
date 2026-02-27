# Cypress FX2 Based Controller for Logical Devices' ALLPRO88 Software-Driven Device Programmer

## Overview

This repository contains the firmware for a Cypress FX2 based USB controller board for Logical Devices' ALLPRO88 software-driven device programmers, as well as a collection of host-side software for working with the programmer via that controller.

See https://github.com/cannon-zz/allpro88-fx2-hard for information about the hardware side of this project.

## Build and Install

For now, the firmware and the host-side utilities use separate build and install systems.  The firmware's is derived from the upstream Makefiles, while the host-side utilities use an autotools style system.  Until the autotools scripts can also build the firmware, the build and install process will require several manual steps.

### Compile the Firmware

Compiling the firmware requires `sdcc`.  Debian users can install `sdcc` using apt.

Then, in the `fw/` directory:

1.  To generate a new serial number to serve as a unique ID run

		$ rm serial.a51 ; make serial.a51

	NOTE:  each unit requires a unique serial number to allow calibration data to be associated with the correct unit.  If you know the original serial number for your unit and would like to use that instead of a randomly generated UUID, then run, for example,

		$ echo "12345" | python3 gen_serial.py >serial.a51

	using, of course, your actual serial number

	NOTE:  the serial number will be used to generate file names, and displayed in messages to the user, therefore it must be a string compatible with these applications.  Stick to printable ASCII characters only, no whitespace and no slashes.

2.  After the serial number file has been generated, compile the firmware with

		$ make

	The compiled firmware is in `fw/build/firmware.ihx`.

### Install the Firmware

Programming the device requires the `fxload` tool.  Debian users can install the `fxload` package with apt.

For runtime single-use only (firmware gets installed into RAM by the host after the programmer has been powered up), in the `fw/` directory use, for example,

	$ fxload -t fx2lp -D /dev/bus/usb/001/008 -I build/firmware.ihx

but using the correct USB device file.  To write the firmware into the onboard EEPROM, in the `fw/` directory use, for example,

	$ fxload -t fx2lp -D /dev/bus/usb/001/008 -I build/firmware.ihx -c 0x01 -s Vend_Ax.hex

but, again, using the correct USB device file.

NOTE:  the FX2 must detect the presence of the EEPROM at boot or the chip will refuse to write to it.  It doesn't have to have firmware in it but the EEPROM must be enabled, it must see that the chip is at the expected address.  It's not possible to power up the FX2 with the EEPROM disabled, then install the jumper and write firmware to the EEPROM.  That means that because buggy firmware can make the FX2 unresponsive (ask me how I know), if buggy firmware gets into the EEPROM and bricks the board it's very difficult to fix it using only software on the PC.  There are tools for doing this floating around on the internet if it happens to you.  The EEPROM disable jumper doesn't really disable the EEPROM, it just moves it to a different address on the I2C bus where the FX2 isn't looking, so you can boot the FX2 with the EEPROM disabled and upload a custom firmware whose only task is to erase the EEPROM chip at its alternate address.  After that it can be put back to its proper address and reprogrammed as above.

### Build and Install the Utilities

In the top-level directory lives a GNU autotools build and install system.  From a git clone of the repository, initialize the scripts with

	$ ./00init.sh

and press RETURN to run it.  This generates the Makefile.in templates and the configure script.

If you are installing into your home directory as an unprivileged user, run the configure script with a suitable `--prefix` override, for example,

	$ ./configure --prefix=${HOME}/local

If you are installing system-wide as root, run the configure script with suitable overrides, for example

	$ ./configure --prefix=/usr --sysconfdir=/etc

These commands install the utilities into `${pefix}/bin/` and the Python library modules into `${prefix}/lib/`.  Calibration files, when available, get placed in `${prefix}/var/allpro88/`.  The latter, run as root, installs the udev rules file giving access permissions to the programmer to all users into `/etc/udev/rules.d/`.  Otherwise the file gets dumped elsewhere, and something else will need to be done to arrange access for unprivileged users (see below).

### USB Device Permissions

In the `udev/` directory is a file named `99-allpro88.rules`.  On a Debian system, put this file into `/etc/udev/rules.d/` so that when the ALLPRO88 is plugged into a USB port the corresponding USB device file is readable and writable by normal users.

USB device files default to being readable and writable only by root.  The udev rule provided here sets the file's permissions to 666 (readable and writable by all).  However, like the groups dialout and lp, which grant access to hardware whose use can lead to financial consequences, it might make sense to create a group to restrict access to the programmer.  There exist command sequences that will damage the programmer, so in an environment with imprudent or injudicious users (for example if the computer is shared with children), this might be something to consider.

## Test and Calibrate your ALLPRO88

### Loopback Test

Connectivity can be tested using the `ap88_loopback` programme.  With the ALLPRO88 plugged in and powered, running this programme will confirm that communication with the programmer is working.  It does some I/O operations, confirms that they do the right thing, and reports the command processing speed.

Confirm that the calibration state, the installed socket module, and the list of installed channels reported by this tool are all what you expect these things to be.  The loop-back command processing speed should be about 10,000 iterations per second.

### Self Test

The programmer can be tested using the `ap88_self_test` programme.  With the ALLPRO88 plugged in and powered, running this programme will perform a sequence of tests on each pin driver.  It will print a log of test results to the terminal and dump a series of diagnostic plots into the directory in which it's running.  Many of the tests will report FAILURE.  At this time this is still normal for perfectly working units.  I don't have the pass/fail thresholds dialed in properly yet.  You need to look at the numbers yourself, see what values they tend to be, and decide if you think any channels appear to be different from the others or if they don't seem to be doing the right thing.  Look at the diagnostic plots and flip through them looking for a channel whose graphs are different from the others.  If they all seem to be the same, probably it's working.

The pull-up voltage ramp graphs, in particular, are an especially sensitive way to detect faults in the pin driver circuits.  Look for graphs whose slopes are different from the rest, or graphs that plateau at some maximum voltage instead of continuing all the way to the top.

### Calibration

If everything seems to be in order it's time to do a calibration.  There are two steps to this:  (i) calibrating the main power supplies, done by hand using a voltmeter, and (ii) calibrating the pin driver circuits with an automatic self-calibration procedure.

The first part, calibrating the main power supplies, is very time consuming.  Right now the code is set up to semi-automate this for me using a voltmeter for which I have a PC interface.  That almost certainly won't work for you, so assume that you cannot calibrate the main power supplies.  Yet.  Unless something is broken the ALLPRO88 should actually be pretty accurately dialed in from the factory, even after all these years.  I own two and both were basically fine.  The calibration polynomials that would be measured here just squeeze that extra little 0.05 V of precision out of them.

The second part, calibrating the pin driver circuits, is also very time consuming but it is fully automatic.  It works by assuming the main power supplies are calibrated, and then the ALLPRO88's own analogue voltage measurements are used to infer biases, offsets, and non-linearities in the pin driver circuits.

At this time, this entire process is also accomplished using the `ap88_self_test` programme.  Check the command line options for more information.

When completed, the calibration process will write the calibration data to a file keyed to the ALLPRO88 unit (the serial number is in the filename).  Put this file into the `${prefix}/var/allpro88/` directory (where `${prefix}` is the directory selected at install time).  Alternatively, if a different directory is desired, set the `ALLPRO88_CAL_PATH` environment variable to that directory's name.  After, that calibration data should be loaded automatically by any tool using the programmer.

## To Do

- Make it faster.  A minipro can dump 64k words in 0.5 s.
	- Transfer numeric values as raw binary instead of ASCII hex.
	- Move WAKEUP pin VBUS monitoring to interrupt handler.
	- Non-DAC write waveform can omit the 0.5 us pause

## Credit

The ALLPRO88 was reverse engineered by kevtris

http://blog.kevtris.org/blogfiles/allpro88/

Note that the site is http, not https, but the server will respond on the https port with an error page, so if you have the "https everywhere" feature turned on in your browser you will be blocked from accessing his documents.  If you are having trouble, check for that and try temporarily turning it off for this site.

The Cypress FX2 firmware in this project was developed from a firmware template forked from

https://github.com/djmuhlestein/fx2lib.git

and is periodically synchronized with that project.  Relevant patches will be contributed back to that project.

This wouldn't have been possible without the kind generous work of these people!
