# Copyright (C) 2022-2025  Kipp Cannon
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation; either version 3 of the License, or (at your
# option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General
# Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.


import operator
import time
import allpro88


#
# =============================================================================
#
#                           Device Power Management
#
# =============================================================================
#


class power(object):
	"""
	Device power management.  Sequences application of voltages to a
	part, provides for selection from among several voltage
	configurations.  Calling the .on() and .off() methods from the
	.__enter__() and .__exit__() methods of a context manager will
	ensure the power to the part is safetly removed in the event of a
	software crash.
	"""
	def __init__(self, programmer, socket, voltage_maps, vadj = "auto", vth = 1.5):
		"""
		programmer:  allpro88 programmer instance

		socket:  the socket instance for the part

		voltage_maps:  a dictionary mapping string names to
		dictionaries of integer pin number-to-voltage mappings,
		with integer pin numbers corresponding to the given socket,
		and (float) voltages in volts.  when the .on() method is
		called, the name of a pin-to-voltage map can be supplied to
		select the pin-to-voltage mapping from among those in
		voltage_maps;  if no name is provided to .on(), the name
		"default" is assumed, which then must be the name of one of
		the pin-to-voltage mappings in voltage_maps.  in each pin
		number-to-voltage mapping, pins whose voltages are 0 will
		be connected to ground, all others will have the given
		voltage (in volts) applied.  all pins given in the voltage
		map, including ground pins, will have bypass capacitors
		connected to them, if the socket module has that feature
		(not all pins in all socket modules provide the bypass
		capacitor feature).  if one of the pins, instead of being
		an integer, is the string "VPUL", then that sets the
		pull-up voltage applied to pull-up resistors in the channel
		drivers.  if VPUL is not given in the voltage map, the
		default of 0 V will be used.

		vadj:  the voltage to set the programmer's main variable
		power supply to.  all other power supply voltages are
		derived from this via linear regulators so this voltage
		needs to be a volt or two higher than the highest required
		voltage.  if set to "auto" (the default) an appropriate
		value will be derived from all required voltages known to
		this instance.  see also the .max() method.  the option of
		setting this voltage manually is provided for applications
		where a higher voltage will be needed but is not initially
		known to this instance.  NOTE:  the main variable power
		supply also powers the pin voltage read-back comparators.
		these are LM393 parts.  to operate, they require a supply
		voltage of at least 2 V, and it is recommended their input
		voltages remain at least 2 V below the supply voltage (but
		never negative), therefore vadj should be at least 2 V
		above the maximum voltage that might appear on any pin,
		even if that voltage is not being supplied by the
		programmer.  this is only a recommendation for the
		comparators to meet their performance specifications;
		failing to keep the comparator supply voltages above their
		input voltages by the minimum recommended amount will not
		damage the parts.  Note, also, that the comparator outputs
		are pulled up to VADJ and applied to the input of an HCT
		series 8-to-1 multiplexer for the read-back circuit, and
		therefore reliable read out of the comparators is only
		guaranteed if VADJ is at least 4 V.

		vth:  the voltage for the comparators used to test the
		boolean state of pins.  the default is 1.5 V, which is a
		compromise voltage usually acceptable for 3.3 V through 5 V
		logic parts.  NOTE:  use of the voltage measurement
		function on any pin will leave this power supply's voltage
		set to the measured pin voltage, and it will need to be
		reset to return to using the comparators as digital inputs.
		see .reset_vth().
		"""
		self.programmer = programmer
		self.socket = socket
		# confirm the voltage maps have valid pins and the voltages
		# are sensible
		valid_pins = set(self.socket) | set(("VPUL",))
		for name, voltage_map in voltage_maps.items():
			if not set(voltage_map) <= valid_pins:
				raise ValueError("invalid pins %s in voltage map \"%s\"" % (set(voltage_map) - valid_pins, name))
			for volt in voltage_map.values():
				# test that this type conversion works
				allpro88.volt(volt)
				# confirm value is valid
				if volt < 0:
					raise ValueError("invalid voltage %g in \"%s\"" % (volt, name))
		self.voltage_maps = voltage_maps
		self.active_voltage_map = None
		self.vth = allpro88.volt(vth) if vth else 0
		if vadj == "auto":
			# whichever is larger:  4 V or the highest
			# requested supply voltage + 2 V.  this ensures
			# proper operation of the comparators and their
			# read-out.
			self.vadj = allpro88.volt(max(4., self.max() + 2.))
		else:
			self.vadj = allpro88.volt(vadj)

	def max(self):
		"""
		Return the highest voltage required for any of the voltage
		configurations, including the pull-up voltage, VPUL, and
		the threshold voltage, VTH.

		The return type is a float, not an allpro88.volt.
		"""
		max_pin_voltage = max(max(voltage_map.values()) for voltage_map in self.voltage_maps.values())
		return float(max(self.vth, max_pin_voltage))

	def reset_vth(self):
		"""
		Reset the programmer's VTH to the configured value.  When a
		pin voltage is measured, VTH is left set to the measured
		voltage.  Use this method to reset it so pin boolean states
		can be interpreted properly again.
		"""
		self.programmer.vth = self.vth

	def set_voltage_map(self, voltage_map):
		"""
		Switch the voltages on the socket's pins to those in
		voltage_map, the name of one of the pin number-to-voltage
		mappings provided at initialization time.

		The pin number-to-voltage mappings are not required to all
		name the same pin numbers, but for safety reasons this
		method will not allow a voltage map to be selected whose
		pin numbers are not a superset of the current mapping:  any
		pin with a voltage configured for it in the currently
		selected mapping must also be listed in the new mapping.
		This restriction might be lifted in the future if a
		sensible behaviour can be identified in those cases, but
		for the time being changing which pins are powered on a
		part requires the part to be power cycled.  See .off() and
		.on().

		The pin voltage DACs and, if included in the voltage map,
		the VPUL power supply DAC, are configured and then clocked
		simultaneously.  Pins that are set to 0 V are connected to
		ground potential, but this configuration is done
		pin-by-pin, before the voltage DACs are changed.
		"""
		# confirm that we are not leaving any already configured
		# pins dangling.  whatever pins we are currently
		# controlling, we must continue to control
		new_voltage_map = self.voltage_maps[voltage_map]
		if self.active_voltage_map is not None:
			current_pins = set(self.active_voltage_map)
			new_pins = set(new_voltage_map)
			if not new_pins >= current_pins:
				raise ValueError("cannot reduce set of configured pins:  %s --> %s" % (str(current_pins), str(new_pins)))

		# switch to new voltage map.  configure pins and the VPUL
		# dac.
		self.active_voltage_map = new_voltage_map
		for pin, voltage in self.active_voltage_map.items():
			if pin == "VPUL":
				self.programmer.vpul = allpro88.volt(voltage) if voltage else 0
			else:
				# retrieve channel driver for this pin.
				# .__init__() has guaranteed this will
				# succeed
				pin = self.socket[pin]
				# configure
				pin.bypass = True
				if voltage:
					pin.config = allpro88.PINCON.VDAC
					pin.vdac = allpro88.volt(voltage)
				else:
					pin.config = allpro88.PINCON.GND
					pin.vdac = 0
		# if VPUL was not explicitly set in the voltage map,
		# default to 0 V.
		if "VPUL" not in self.active_voltage_map:
			self.programmer.vpul = 0
		# clock the VPUL and pin driver dacs
		self.programmer.load_dacs()

	def do_sequence(self, sequence):
		"""
		sequence must be an iterable of (voltage map name, delay)
		pairs.  the voltage maps in sequence are applied in order,
		with each held for the given delay in seconds before the
		next is applied.  NOTE: delays of about 100 us or less
		cannot be relied upon.  if a shorter delay is requested
		than is possible, it will be silently increased to the
		minimum achievable delay.  if that is not acceptable, if
		power must be sequenced onto a part with short, precise,
		time intervals, then custom firmware support will be
		needed for the programmer.
		"""
		# ensure we can iterate over it more than once and it's not
		# empty
		sequence = tuple(sequence)
		if len(sequence) < 1:
			raise ValueError("sequence is empty")
		# before we start, confirm the voltage maps are known, the
		# delays are sensible, and all voltage maps in the sequence
		# configure the same pins.  we don't want to crash during
		# the sequence
		if self.active_voltage_map is not None:
			pins = set(self.active_voltage_map)
		else:
			pins = None
		for voltage_map, delay in sequence:
			if voltage_map not in self.voltage_maps:
				raise KeyError(voltage_map)
			if delay < 0:
				raise ValueError("invalid delay %g" % delay)
			if pins is None:
				pins = set(self.voltage_maps[voltage_map])
			elif pins != set(self.voltage_maps[voltage_map]):
				raise ValueError("inconsistent pins in voltage map \"%s\"" % voltage_map)
		# run the sequence
		for voltage_map, delay in sequence:
			self.set_voltage_map(voltage_map)
			time.sleep(delay)

	def on(self, voltage_map = "default", sequence = None):
		"""
		Turn the power supplies on, applying power to the part.  If
		sequence is None (the default), then use the voltages in
		the voltage map named voltage_map, or in the voltage map
		named "default" if a name is not given.

		If sequence is not None, then voltage_map is ignored, and
		sequence must be an iterable of (voltage map name, delay)
		pairs.  See .do_sequence() for more information.
		"""
		# turn on power supplies.  this is done before clocking the
		# VPUL and pin driver dacs because the VADJ power supply
		# has a slow transient response.  if the dacs are loaded
		# first, then all the voltages ramp up with VADJ as it
		# ramps, but that is longer than the maximum allowed
		# transition time for some parts' power supply pins.
		self.programmer.pcr_enable = True
		# set main dacs
		self.programmer.vadj = self.vadj
		self.reset_vth()
		# configure pins and the VPUL dac, and clock them to apply
		# power to the part
		try:
			if sequence is None:
				self.set_voltage_map(voltage_map)
			else:
				self.do_sequence(sequence)
		except:
			# if a failure occurs, we want to guarantee the
			# power has been turned off, so we trap *anything*
			# and run the following

			# set main dacs to 0
			self.programmer.vadj = 0
			self.programmer.vth = 0
			# cut main power
			self.programmer.pcr_enable = False
			# continue error handling
			raise

	def off(self):
		"""
		Turn power supplies off.
		"""
		# set VPUL and pin dacs to 0
		self.programmer.vpul = 0
		if self.active_voltage_map is not None:
			for pin in self.active_voltage_map:
				if pin != "VPUL":
					self.socket[pin].vdac = 0
		# clock the VPUL and pin driver dacs to remove power from
		# the part, changing all voltages simultaneously.
		self.programmer.load_dacs()
		# now that power has been removed, it is safe to disable
		# pins
		if self.active_voltage_map is not None:
			for pin in self.active_voltage_map:
				if pin != "VPUL":
					pin = self.socket[pin]
					pin.bypass = False
					pin.config = allpro88.PINCON.DISABLE
		# no active voltage map
		self.active_voltage_map = None
		# set main dacs to 0
		self.programmer.vadj = 0
		self.programmer.vth = 0
		# cut main power
		self.programmer.pcr_enable = False


#
# =============================================================================
#
#                 Class descriptors to make I/O more readable
#
# =============================================================================
#


class read_write_proxy(object):
	"""
	Descriptor to map the get and set operations of an attribute to the
	.read() and .write() methods, respectively, of some object.

	Example:

	class thing(object):
		def __init__(self):
			# instance attribute with .read() and .write()
			# methods
			self.f = open("/dev/null")

		# assigning to and retrieving the value of .nul wraps the
		# .write() and .read() methods, respectively, of .f
		nul = read_write_proxy("f")

	x = thing()
	x.nul = "this is written to /dev/null"
	"""
	def __init__(self, attr_name):
		"""
		attr_name:  name of the attribute whose .read() and
		.write() methods will be called by this descriptor's
		.__get__() and .__set__() methods, respectively.
		"""
		self.getter = operator.attrgetter(attr_name)

	def __get__(self, obj, objtype = None):
		"""
		Call getattr(obj, attr_name).read() and return the result.
		"""
		return self.getter(obj).read()

	def __set__(self, obj, val):
		"""
		Call getattr(obj, attr_name).write(val).
		"""
		self.getter(obj).write(val)


#
# =============================================================================
#
#                                    Buses
#
# =============================================================================
#


#
# These are additional bus types for which there is no specific firmware
# support.  They are implemented purely in software.
#


#
# IIC aka I2C bus
#


class bus_iic(object):
	"""
	IIC (aka I2C) bus.  NOTE:  must set VPUL = VCC for the chip and VTH
	to the minimum bus "high" state voltage.

	The methods must be called as follows:  first .start(), then any
	number of .write_byte(), .start(), and .read_byte() in any order,
	finally .stop().  The bit manipulations performed by each method
	follow correctly from the state the bus has been left in by the
	preceding method;  different orders will not work.

	NOTE:  the controller in the USB interface has its own, native, IIC
	interface with which it communicates with its EEPROM and which is
	available on a pin header for future expansion.  This is *not* an
	interface to that bus.  This is a software emulation of an IIC bus
	implemented by bit-banging socket pins.
	"""
	lo = allpro88.PINCON.PULLUP | allpro88.PINCON.LOGICL
	hi = allpro88.PINCON.PULLUP
	flt = allpro88.PINCON.PULLUP

	def __init__(self, socket, sda, scl, strict_arbitration = False):
		"""
		socket:  the socket object containing the part
		sda:  the pin number for SDA
		scl:  the pin number for SCL

		if strict_arbitration is True then the bit banging
		algorithm will insert checks to ensure the target device
		has released the SDA and/or SCL lines at times when it
		would be allowed to hold them low to extend I/O cycles, for
		example if the part needs extra time to write data into
		flash memory.  since the bit banging algorithm is sooo
		slooow, it is almost certainly already going slowly enough
		to provide the time delays any part might require and
		adding the extra checking only slows it down even more.
		for this reason the default is to disable the checks (set
		strict_arbitration to False).  if you encounter a part that
		seems to not be working reliably, try setting
		strict_arbitration to True and see if that helps.
		"""
		# the socket object containing the part
		self.socket = socket
		# whether to do additional bus timing and arbitration error
		# checking.  slows the interface down significantly, but
		# some parts might require it.  haven't encountered one
		# yet, though
		self.strict_arbitration = strict_arbitration
		# SDA and SCL pins
		self.sda = socket[sda]
		self.scl = socket[scl]
		# start in idle state
		self.sda.config = self.hi
		self.scl.config = self.hi
		self.started = False

	#
	# helpers
	#

	def wait_sda(self, timeout = 0.5):
		"""
		Wait for SDA line to be high.  No-op if strict_arbitration
		is False.
		"""
		if not self.strict_arbitration:
			return
		timeout += time.time()
		while not bool(self.sda):
			if time.time() > timeout:
				raise IOError("bus sda is being held low")

	def wait_scl(self, timeout = 0.5):
		"""
		Wait for SCL line to be high.  No-op if strict_arbitration
		is False.
		"""
		if not self.strict_arbitration:
			return
		timeout += time.time()
		while not bool(self.scl):
			if time.time() > timeout:
				raise IOError("bus scl is being held low")

	#
	# bit-banging bus interface
	#

	def start(self):
		"""
		Transmit start sequence.  If a start sequence has already
		been transmitted without an intervening stop sequence
		having been transmitted then a "restart" sequence is
		transmitted instead.
		"""
		if self.started:
			# restart sequence
			self.scl.config = self.lo
			self.sda.config = self.hi
			self.scl.config = self.hi
		# do start sequence.
		self.wait_scl()
		self.wait_sda()
		self.sda.config = self.lo
		self.started = True

	def stop(self):
		"""
		Transmit stop sequence.
		"""
		assert self.started
		# do stop sequence.  but have just read or written a byte
		# so first pull clock low, pull data low, raise clock, then
		# raise data.  bus is left in idle state
		self.scl.config = self.lo
		self.sda.config = self.lo
		self.scl.config = self.hi
		self.wait_scl()
		self.sda.config = self.hi
		self.wait_sda()
		self.started = False

	def write_bit(self, boolean):
		"""
		Write one bit.  This is unlikely to be needed by calling
		code.  See .write_byte() and .read_byte() for the normal
		I/O interface functions.
		"""
		assert self.started
		# pull clock low, put bit onto data, raise clock
		self.scl.config = self.lo
		self.sda.config = self.hi if boolean else self.lo
		self.scl.config = self.hi
		# a 4 us pause is required here.  we assume the USB I/O
		# overhead is more than that, and the pause will take care
		# of itself
		self.wait_scl()
		# NOTE:  finally, clock must be pulled low again to
		# complete the bit.  the calling code will need to ensure
		# this.  following this with a call to any of .write_bit(),
		# .read_bit() or .stop() will do the correct thing.

	def read_bit(self):
		"""
		Read one bit.  This is unlikely to be needed by calling
		code.  See .write_byte() and .read_byte() for the normal
		I/O interface functions.
		"""
		assert self.started
		# pull clock low to complete last operation, float data
		# line to allow target to drive it, raise clock, read data
		# state
		# NOTE:  finally, clock must be pulled low again to
		# complete the bit.  the calling code will need to ensure
		# this.  following this with a call to any of .write_bit(),
		# .read_bit() or .stop() will do the correct thing.
		self.scl.config = self.lo
		self.sda.config = self.hi
		self.scl.config = self.hi
		self.wait_scl()
		return bool(self.sda)

	def write_byte(self, byte):
		"""
		Write an 8 bit byte, read the ACK bit, and return the ACK
		bit value.
		"""
		assert 0 <= byte <= 255
		for bit in (0x80, 0x40, 0x20, 0x10, 0x08, 0x04, 0x02, 0x01):
			self.write_bit(byte & bit)
		# read the ack state
		return not self.read_bit()

	def read_byte(self, ack = True):
		"""
		Read an 8 bit byte, and respond with the given ACK bit
		value.
		"""
		data = 0
		for bit in (0x80, 0x40, 0x20, 0x10, 0x08, 0x04, 0x02, 0x01):
			if self.read_bit():
				data |= bit
		# write the ack state
		self.write_bit(not ack)
		return data

	def scan(self):
		"""
		Scan the IIC bus and report the addresses that generate an
		ACK for a read operation.  Returns a list of the addresses.
		"""
		found = []
		for address in range(128):
			self.start()
			# combine address with R/!W, which we set to 1 so
			# we don't initiate a write operation
			if self.write_byte(address << 1 | 1):
				found.append(address)
			self.stop()
		return found

	#
	# emulate enough of the smbus2 API to allow luma.oled to control an
	# I2C OLED display through the programmer.
	# FIXME:  expand the emulated API for even more fun.
	#

	def write_i2c_block_data(self, i2c_addr, register, data, force = None):
		self.start()
		# combine address with R/!W bit = 0
		self.write_byte(i2c_addr << 1 | 0)
		self.write_byte(register)
		for val in data:
			self.write_byte(val)
		self.stop()


#
# SPI bus
#


class bus_spi(object):
	"""
	SPI bus.  Calling code must set VTH for the device to VCC - 1 V.

	An SPI bus clocks one byte in each direction simultaneously,
	master->slave and slave->master, using the MOSI and MISO data
	lines, respectively.
	"""
	hi = allpro88.PINCON.VDAC
	lo = allpro88.PINCON.LOGICL

	def __init__(self, socket, sclk, mosi, miso, vdac):
		"""
		socket = the socket instance for the socket in which the
		part is installed.

		sclk, mosi, miso = the socket pin numbers corresponding to
		these SPI signals.

		vdac = the voltage for the "high" state on the pins (in
		volts, not dac count).
		"""
		# retrieve channel proxy objects for the pins
		self.sclk = socket[sclk]	# clock
		self.mosi = socket[mosi]	# master --> slave
		self.miso = socket[miso]	# master <-- slave

		# set the VDAC voltage on the sclk and mosi pins
		if vdac <= 0:
			raise ValueError(vdac)
		vdac = allpro88.volt(vdac)
		self.sclk.vdac = vdac
		self.mosi.vdac = vdac

		# set both pins low = idle state, and make sure miso is
		# floating.
		self.sclk.config = self.lo
		self.mosi.config = self.lo
		self.miso.config = allpro88.PINCON.DISABLE

	def transfer_byte(self, out_byte):
		"""
		Clocks out_byte out to the part, while clocking a byte in
		from the part.  The return value is the byte clocked in.
		"""
		in_byte = 0
		for bit in (0x80, 0x40, 0x20, 0x10, 0x08, 0x04, 0x02, 0x01):
			self.mosi.config = self.hi if (out_byte & bit) else self.lo
			self.sclk.config = self.hi
			self.sclk.config = self.lo
			if self.miso:
				in_byte |= bit
		# we don't reset mosi.  FIXME:  do we need to?
		#self.mosi.config = self.lo
		return in_byte
