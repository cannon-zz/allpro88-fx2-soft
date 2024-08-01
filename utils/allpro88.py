from enum import IntEnum
import numpy
import time
import usb.core
import yaml
from socket_module import socket_modules


#
# NOTE NOTE NOTE:  in all of what follows, "channel number" means a pin
# driver channel number according to my numbering convention, NOT any of
# the channel numbering conventions shown in the ALLPRO88 technical
# documentation (I've identified at least two).  by my convention channels
# are numbered sequentially from 0 in the order of their control register
# addresses.
#


#
# =============================================================================
#
#                           Register Bit Definitions
#
# =============================================================================
#


class PCR(IntEnum):
	"""
	PCR (power supply control register) configuration bits.
	"""
	# power supplies off, red busy LED off, green idle LED on
	DISABLE = 0x00
	# enables power supplies, and lights red busy LED
	ENABLE = 0x01
	# turns off green idle LED
	NIDLE = 0x02


class PINCON(IntEnum):
	"""
	Pin driver configuration register bits.
	"""
	DISABLE = 0x00	# disable ("float") pin
	GND = 0x01	# turn on FET pulling pin to ground
	VDAC = 0x02	# turn on DAC output power transistor
	VTST = 0x04	# turn on current- and voltage-limited source driver
	LOGICH = 0x08	# turn on +5 V ("TTL high") driver
	PULLUP = 0x10	# turn on pull-up driver (2.7 kOhm to VPUL source)
	LOGICL = 0x20	# turn on 0 V ("TTL low") driver (50 Ohm to ground)
	POSCLK = 0x40	# turn on +5 V <--> 0 V ("TTL") clock
	NEGCLK = 0x60	# turn on 0 V <--> +5 V ("TTL") clock (reversed phase)
	PULLDN = 0x80	# turn on pull-down driver (5.4 kOhm to ground)


class TIMER_MODE(IntEnum):
	# in bit-bang mode, the polarity bit sets the state of the timer
	# output.  otherwise, according to kevtris the polarity bit sets
	# the state of timer output when it is not toggling (don't know
	# what that means).  FIXME:  figure out what that means.
	DISABLE = 0x00
	BITBANG = 0x01
	CLK_4MHZ = 0x02
	CLK_2MHZ = 0x03
	CLK_1MHZ = 0x04
	CLK_500KHZ = 0x05
	CLK_250KHZ = 0x06
	# NOTE:  setting mode 0x07 enables both high and low output drivers
	# and will damage the circuit
	POLARITY = 0x80


#
# =============================================================================
#
#                          Firmware Command Interface
#
# =============================================================================
#


class command(object):
	"""
	Device for constructing a command string from a verb and optional
	address and value.  This also provides a place for the command
	queue machinery to place a response from the programmer, allowing
	each response to be associated with the command that produced it.
	"""
	def __init__(self, verb, addr = None, val = None, label = None):
		self.verb = verb
		self.addr = addr
		self.val = val
		self.label = label
		if verb == "=":
			# write arbitrary value to arbitrary register
			# NOTE NOTE NOTE:  physical damage will occur if
			# the wrong value is written to the wrong address.
			# by writing an unfortunate value to a pin
			# configuration register, a pin might be connected
			# to both a supply voltage and ground
			# simultaneously, destroying the pin driver
			# electronics.  for testing purposes, writing 0 to
			# any address is safe.  this always corresponds to
			# the "disabled" or "turned off" setting for any
			# register.  other values should only be written
			# after carefully consulting the documentation.
			self.cmd = "=%04X%02X\n" % (addr, val)
			self.need_response = False
		elif verb == "?":
			# read value from register
			assert val is None
			self.cmd = "?%04X\n" % addr
			self.need_response = True
		elif verb == "E":
			# echo 4 digit number (USB loop-back test)
			assert val is None
			self.cmd = "E%04X\n" % addr
			self.need_response = True
		elif verb == "M":
			# measure voltage using VTH
			assert val is None
			self.cmd = "M%02X\n" % addr
			self.need_response = True
		elif verb == "V":
			# measure voltage using VADJTH
			assert addr is None and val is None
			self.cmd = "V\n"
			self.need_response = True
		else:
			raise ValueError("invalid command verb \"%s\"" % verb)
		self.response = None

	def __str__(self):
		return self.cmd


#
# =============================================================================
#
#                           Channel Driver Interface
#
# =============================================================================
#


class volt(float):
	"""
	Sub-class of float used to indicate to a DAC proxy that the value
	should be interpreted as a voltage, not a DAC count.
	"""
	pass


class dacregister(object):
	"""
	Write a value to a DAC register.  Provides type conversion and
	range checking to ensure the value written is allowed, and will
	optionally apply a volts-to-DAC count calibration function.
	"""
	def __init__(self, address = None, transient = 0., cal_key = None):
		# fixed register address, if known.  if not known, or None,
		# the .address() method must be overridden.

		self._address = address

		# transient response time in seconds.  for convenience,
		# this code can enforce a pause after changing a DAC, to
		# give the respective voltage time to slew.  this removes
		# the need to include those pauses in calling code
		# everywhere they are required.
		#
		# NOTE:  it is possible, and often convenient, to set
		# various DACs before turning on the power supplies that
		# drive the DACs, so that when power is applied the pins of
		# a part ramp up in voltage together.  obviously when that
		# is done the pause that should be included to allow for
		# voltage slews needs to be inserted when the power
		# supplies are turned on, not when the DAC register is set.
		# with that example in mind, the inclusion of the transient
		# pause feature here does not guarantee that all voltage
		# slew pauses associated with a given DAC are necessarily
		# accounted for.  thought should always be put into where a
		# delay might still be needed.

		self.transient = transient

		# calibration function look-up key.  you might think it
		# would make more sense to simply set the calibration
		# function here directly instead of this nonsense of a key
		# that we use to look up in a dictionary elsewhere.  the
		# problem is that a descriptor (used to implement an
		# attribute of a class) is only a single instance:  there
		# is one instance of the descriptor class for the class
		# definition to which it is attached, there is not a new
		# instance of the descriptor for each instance of the
		# class.  that means that data stored in the descriptor
		# instance is shared across all instances of the class
		# whose attribute it is being used to implement.  we cannot
		# store any data here that we might want to configure
		# differently for different programmers.  therefore we
		# cannot put the calibration curve itself here, only a
		# shared key used to look up the programmer-specific
		# calibration function in a table stored elsewhere.

		self.cal_key = cal_key

	def address(self, obj):
		# subclasses override this if they need something other
		# than a single, known, fixed, address.
		assert self._address is not None
		return self._address

	def cal(self, dac, obj):
		"""
		Convert DAC count to voltage.  If this descriptor was
		initialized with cal_key set to None (the default) then a
		default generic calibration function is used.  Otherwise,
		obj.cal[self.cal_key] is retrieved, and the result of
		passing the DAC value to that function is used as the
		return value.
		"""
		if self.cal_key is None:
			# default calibration
			return dac * 25.5 / 256.
		return obj.cal[self.cal_key](dac)

	def __set__(self, obj, val):
		"""
		Set the DAC register.  If the value is a volt object, the
		calibration function is applied to convert the voltage to
		an integer count, which is then written to the DAC
		register.  Otherwise, the value supplied is converted to an
		integer, and then written to the DAC register.  In both
		cases, before writing the integer DAC count to the register
		it is confirmed to be in [0, 255].  If any of the
		conversion steps or safety checks fail, an exception will
		be raised, typically ValueError, but OverflowError and
		others are possible depending on the nature of the failure.
		"""
		# if the calling code has given us a volt value, convert to
		# DAC count
		if type(val) is volt:
			dac = self.invcal(val, obj)
		else:
			# verify int compatibility
			dac = int(val)
		# verify range
		if not 0 <= dac <= 255:
			raise ValueError("0 <= dac <= 255:  %d" % dac)
		# OK
		obj.write_command("=", self.address(obj), dac)
		time.sleep(self.transient)

	def invcal(self, v):
		# most calibration mappings are linear or quadratic
		# polynomials and are easily inverted, but that would
		# require it be done for each case.  since the number of
		# possible values is so small, this loop completes in only
		# a few iterations, and doing it this way has the advantage
		# of always working without having to remember to invert an
		# algebraic expression.
		lo, hi = 0., 255.
		while hi > lo + 0.5:
			dac = (hi + lo) / 2.
			cal = self.cal(dac)
			if cal == v:
				break
			elif cal < v:
				lo = dac
			else:	# cal > v:
				hi = dac
		dac = round(dac)
		assert type(dac) is int
		# some calibration mappings predict a constant output below
		# some threshold.  if we've chosen a DAC setting in such an
		# interval, choose the lowest such DAC setting (typically
		# 0, but check).
		while dac > 0 and self.cal(dac - 1, obj) == self.cal(dac, obj):
			dac -= 1
		return dac


class vdacregister(dacregister):
	# version of dacregister that gets the address dynamically from the
	# object to which it is attached.
	def address(self, obj):
		return obj.address + 3


class channel_proxy(object):
	def __init__(self, programmer, channel, cal_data = {"min": 0.1892, "poly": (4.479e-06, 0.09901, -0.6891)}):
		self.programmer = programmer
		# integer channel number
		self.channel = channel
		# start of group of addresses for this channel
		self.address = programmer.channel_addr(channel)
		# bypass capacitor control register
		# FIXME:  the bypass capacitor feature including its
		# associated control logic and address decode circuitry
		# lives on the socket module.  it's not part of the
		# programmer.  if a different socket module gets installed
		# who knows what these addresses would control.  this
		# address range is probably meant to be a generic expansion
		# port feature, and it would probably be better being
		# handled by the socket_module class somehow so that the
		# correct code is attached to the electronics.  the
		# subclass for the DIP/PLCC module that I have would then
		# provide this bypass capacitor feature, specifically.
		if channel <= 0x27:
			self.bypass_address = 0x280 + channel
		elif channel <= 0x2f:
			self.bypass_address = 0x2c0 + (channel - 0x28)
		else:
			# only first 48 channels have bypass capacitors
			self.bypass_address = None
		# set the calibration
		self.set_cal(cal_data)

	vdac = vdacregister(cal_key = "VDAC")

	def write_command(self, *args, **kwargs):
		# plumbing for the vdac descriptor
		return self.programmer.write_command(*args, **kwargs)

	def set_cal(self, cal_data):
		poly2, poly1, poly0 = cal_data["poly"]
		self.cal = {
			"VDAC": (lambda dac: max(cal_data["min"], (poly2 * dac + poly1) * dac + poly0))
		}

	def __bool__(self):
		"""
		Boolean state = state of comparator.  Set VTH to threshold
		voltage.
		"""
		state, = self.programmer.write_command("?", self.address)
		return bool(state & 1)

	def measure_v(self, n = 1):
		"""
		Use bisection search with VTH to measure the voltage on
		this channel's pin.  Repeat the measurement n times
		(default = 1) and report the median of the measurements.
		NOTE:  VTH is left set to (an approximation of) the
		measured voltage.
		"""
		n = int(n)
		assert n > 0
		measurements = []
		for i in range(n):
			vdac, = self.programmer.write_command("M", self.channel)
			measurements.append(self.programmer.vth.cal(vdac, self.programmer))
		return numpy.median(measurements)

	def pulse(self, microseconds, config, final_config):
		"""
		Switch this channel's configuration to config, hold it for
		the given number of microseconds, then switch the
		configuration to final_config.

		It is common for programmable devices to require a short
		pulse on a single pin to affect the programming operation.
		Usually there are strict requirements for the duration of
		the pulse.  This method is provided to meet the needs of
		such parts.

		NOTE:  the firmware generates pulse durations that are
		quite accurately timed to the integer microsecond, however
		the shortest pulse the firmware can generate is
		approximately 5 us.  It is not an error to request a
		shorter pulse, but a 5 us pulse will be generated in those
		cases.
		"""
		microseconds = int(microseconds)
		if microseconds < 0:
			raise ValueError("pulse duration < 0")
		if microseconds > 0xffff:
			# FIXME:  if such a long pulse, longer than ~65 ms,
			# is desired then probably also the duration does
			# not need to be controled to microsecond
			# precision.  if the tolerance can be relaxed
			# enough, the pulse could be implemented in
			# software, here, on the host side.
			raise ValueError("pulse duration too long:  %d us" % microseconds)
		command = "P%02X%04X%02X%02X\n" % (self.channel, microseconds, config, final_config)
		self.programmer.device.write(self.programmer.ep_addr_out, command.encode("ascii"))
		# clear response buffer
		self.programmer.read_responses()

	config = property(fset = lambda self, config: self.programmer.write_command("=", self.address, config))

	@property
	def bypass(self):
		"""
		Boolean controlling the state of this channels' bypass
		capacitor.
		"""
		raise NotImplementedError

	@bypass.setter
	def bypass(self, boolean):
		# bypass capacitor is turned on and off with bit 0.
		# silently ignore requests to turn on or off bypass
		# capacitors on channels that don't have them.
		if self.bypass_address is not None:
			self.programmer.write_command("=", self.bypass_address, 1 if boolean else 0)

	@property
	def physical(self):
		"""
		Physical location of this channel within the programmer.
		Value is a tuple:  (pin driver group #, DAC chip identifier
		#, hybrid identifier #, channel # on hybrid).
		"""
		return (
			# group # printed on motherboard PCB
			self.channel // 8,
			# DAC chip ident., U# printed on channel driver PCB
			self.channel % 8 + 1,
			# hybrid ident., H# printed on channel driver PCB
			(self.channel % 8) // 2 + 1,
			# hybrid channel number (as numbered by me for my
			# hybrid tester jig)
			(self.channel % 8) % 2
		)


#
# =============================================================================
#
#                           Channel Driver Wrappers
#
# =============================================================================
#


class flag(object):
	"""
	A tri-state logic interface on one of a socket's pins, with default
	initial value.  The pin can be used for output or input.  To set
	the state of the pin, i.e., to use the pin for output, write a
	boolean value.  To use the pin for input, set it to None to float
	the pin.  To read the state of the pin, read a value.

	The pin is initialized to the value set by the keyword argument
	default.

	NOTE:  by default, the pin will be set to output, and initialized
	to the inactive (False) state.  If that requires a voltage to be
	applied to the pin, it will not take effect until power is applied
	to the socket.
	"""
	def __init__(self, socket, pin_number, active, inactive, flt = PINCON.DISABLE, default = False):
		self.socket = socket
		self.pin_number =  pin_number
		self.active = active
		self.inactive = inactive
		self.flt = flt
		self.default = default
		# set initial state
		if PINCON.VDAC not in (active, inactive, flt):
			self.socket[self.pin_number].vdac = 0
		self.channel.bypass = False
		self.write(self.default)

	@property
	def channel(self):
		return self.socket[self.pin_number]

	def read(self):
		return bool(self.channel)

	def bool_to_config(self, boolean):
		"""
		Convert boolean value to corresponding channel
		configuration register value.  The return value is
		self.active or self.inactive if boolean is (equivalent to)
		True or False, respectively.  If boolean is None then
		self.flt is returned.
		"""
		return self.flt if boolean is None else self.active if boolean else self.inactive

	def write(self, boolean):
		self.channel.config = self.bool_to_config(boolean)

	def pulse(self, microseconds, boolean, final_boolean):
		"""
		Set the pin driver channel configuration to the state
		corresponding to boolean, hold it for the given number of
		microseconds, then set it to the state corresponding to
		final_boolean.  See .bool_to_config() for the mapping from
		boolean value to flag state.
		"""
		self.channel.pulse(microseconds, self.bool_to_config(boolean), self.bool_to_config(final_boolean))


class flag_ttl(flag):
	"""
	Boolean pin configured for active high TTL logic levels.
	"""
	def __init__(self, socket, pin_number, **kwargs):
		super(flag_ttl, self).__init__(socket, pin_number, active = PINCON.LOGICH, inactive = PINCON.LOGICL, **kwargs)


class flag_ttl_active_low(flag):
	"""
	Boolean pin configured for active low TTL logic levels.
	"""
	def __init__(self, socket, pin_number, **kwargs):
		super(flag_ttl_active_low, self).__init__(socket, pin_number, active = PINCON.LOGICL, inactive = PINCON.LOGICH, **kwargs)

	def read(self):
		return not super(flag_ttl_active_low, self).read()


class flag_vdac(flag):
	"""
	Boolean pin configured for active high VDAC programmed logic levels.
	"""
	def __init__(self, socket, pin_number, vdac, **kwargs):
		"""
		vdac = voltage to be used for high state.
		"""
		super(flag_vdac, self).__init__(socket, pin_number, active = PINCON.VDAC, inactive = PINCON.LOGICL, **kwargs)
		if vdac <= 0:
			raise ValueError(vdac)
		self.channel.vdac = volt(vdac)


class flag_vdac_active_low(flag):
	"""
	Boolean pin configured for active low VDAC programmed logic levels.
	"""
	def __init__(self, socket, pin_number, vdac, **kwargs):
		"""
		vdac = voltage to be used for high state.
		"""
		super(flag_vdac_active_low, self).__init__(socket, pin_number, active = PINCON.LOGICL, inactive = PINCON.VDAC, **kwargs)
		if vdac <= 0:
			raise ValueError(vdac)
		self.channel.vdac = volt(vdac)

	def read(self):
		return not super(flag_vdac_active_low, self).read()


class bus_parallel(object):
	"""
	A collection of pins whose digital states represent an integer
	number.  The pins can be used for output or input.  To set the
	state of the pins, i.e., to use the bus for output, write a value
	to the bus.  To use the bus for input, write None to the bus to
	float the pins.  To read the state of the pins, read a value from
	the bus.

	A bus may be any number of bits in size between 1 and 32,
	inclusively.  Up to 8 buses may be defined and in use
	simultaneously.  These are limitations of the programmer interface
	firmware.

	default sets the initial state of the bus, which will be passed to
	.write() to perform the configuration.  If not specified, or set to
	None, the bus is initialized to a floating state.  Note that if the
	configured default initial state involves any pins being driven to
	non-zero voltages, those voltages will not take effect until power
	is applied to the socket.  Pins configured for ground potential
	take effect immediately.

	NOTE:  see also devices.bus_proxy_parallel to create a descriptor
	to make calling the .read() and .write() methods of an instance of
	this class more convenient.
	"""
	def __init__(self, programmer, socket, pin_numbers, active, inactive, flt, default = None):
		if not (1 <= len(pin_numbers) <= 32):
			raise ValueError("bus width out of range: 1 <= %d <= 32" % len(pin_numbers))
		self.programmer = programmer
		self.socket = socket
		self.bus_number = self.programmer.get_unused_bus(self)
		self.pin_numbers = tuple(pin_numbers)
		self.max_word = (1 << len(pin_numbers)) - 1
		self.default = default
		# send the bus definition command to the programmer
		command = "B%1XP:%02X%02X%02X%02X" % (self.bus_number, active, inactive, flt, len(pin_numbers))
		command += "".join("%02X" % socket[pin_number].channel for pin_number in pin_numbers)
		command += "\n"
		self.programmer.device.write(self.programmer.ep_addr_out, command.encode("ascii"))
		# clear response
		self.programmer.read_responses()
		# set initial state
		for channel in self.channels:
			if PINCON.VDAC not in (active, inactive, flt):
				channel.vdac = 0
			channel.bypass = False
		self.write(self.default)

	@property
	def channels(self):
		return tuple(self.socket[pin_number] for pin_number in self.pin_numbers)

	def read(self):
		"""
		Return the integer value corresponding to the bus' pin
		voltage comparators.  The "high"/"low" states are defined
		by the VTH voltage, not the .inactive and .active states.
		"""
		command = "B%01XP?\n" % self.bus_number
		self.programmer.device.write(self.programmer.ep_addr_out, command.encode("ascii"))
		word, = self.programmer.read_responses()
		return word

	def write(self, word):
		"""
		Set the pins of the bus to either .inactive or .active
		according to the bits of the integer word.  If word is None
		the pins are floated.
		"""
		# float the bus if word is None
		if word is None:
			command = "B%01XP-\n" % self.bus_number
		# otherwise do a range check
		elif not (0 <= word <= self.max_word):
			raise ValueError("0x0 <= word <= 0x%X: 0x%X" % (self.max_word, word))
		# and set the bus equal to word
		elif len(self.pin_numbers) <= 8:
			command = "B%1XP=%02X\n" % (self.bus_number, word)
		elif len(self.pin_numbers) <= 16:
			command = "B%1XP=%04X\n" % (self.bus_number, word)
		else:
			command = "B%1XP=%08X\n" % (self.bus_number, word)
		self.programmer.device.write(self.programmer.ep_addr_out, command.encode("ascii"))
		# clear response
		self.programmer.read_responses()

	def __len__(self):
		"""
		The number of unique values the bus can represent.
		"""
		return self.max_word + 1

	def __iter__(self):
		"""
		Iterate over the unique values the bus can represent.
		Useful, for example, to iterate over the addresses for a
		ROM chip, or to generate test vectors for a logic chip.
		"""
		return iter(range(len(self)))

	def __del__(self):
		self.programmer.release_bus(self.bus_number)


class bus_parallel_ttl(bus_parallel):
	def __init__(self, programmer, socket, pin_numbers, **kwargs):
		super(bus_parallel_ttl, self).__init__(programmer, socket, pin_numbers, active = PINCON.LOGICH, inactive = PINCON.LOGICL, flt = PINCON.DISABLE, **kwargs)


#
# =============================================================================
#
#                        ALLPRO88 Programmer Interface
#
# =============================================================================
#


class allpro88(object):
	#
	# USB information
	#

	idVendor = 0x1209
	idProduct = 0x000C

	ep_addr_out = 0x02
	ep_addr_in = 0x86

	buf_size = 512	# bytes

	command_queue_size = 64	# commands

	def __init__(self, calibration_file = None):
		self.buf = usb.core.array.array("B", (0,) * self.buf_size)
		self.device = usb.core.find(idVendor = self.idVendor, idProduct = self.idProduct)
		if self.device is None:
			raise ValueError("USB device not found (vid:pid = %04X:%04X)" % (self.idVendor, self.idProduct))

		# firmware resets itself and the programmer.  the
		# .__enter__() method repeats much of what this does, but
		# it doesn't hurt to be cautious
		self.device.set_configuration()

		# initialize channel proxy list.  NOTE:  this step must be
		# completed before initializing the .socket_module
		# attribute.  the socket_module classes use this list to
		# initialize their pin mappings
		self.channels = [channel_proxy(self, i) for i in range(88)]


		# command queues
		self.out_queue = []
		self.in_queue = []

		# configure for the installed socket module
		try:
			self.socket_module = socket_modules[self.socket_module_id](self)
		except KeyError as e:
			if self.socket_module_id == 0xff:
				print("warning:  no socket module detected")
			else:
				print("warning:  unrecognized socket module ID 0x%02X" % self.socket_module_id)
			self.socket_module = None

		# keep track of what bus numbers are in use
		self.bus = {}

		# install calibration model (defaults if no calibration
		# model file is provided)
		self.cal = {}
		self.set_calibration(calibration_file)


	def __enter__(self):
		# ensure the programmer is left in a safe condition (all
		# variable power supplies off, all channel drivers
		# disabled).

		# turn off power supplies
		self.pcr_enable = False

		# ensure all channel drivers are disabled (off), the DAC
		# voltages are 0'ed and the bypass capacitors disabled
		for channel in self.channels:
			channel.config = PINCON.DISABLE
			channel.bypass = False
			channel.vdac = 0
		# set all variable power supplies to 0 V
		self.vpul = 0
		self.load_dacs()	# also updates pin driver DACs
		self.vsr = 0
		self.vth = 0
		self.vtst = 0
		self.itst = 0
		self.vadjth = 0
		self.vadj = 0

		# done
		return self


	def __exit__(self, exc_type, exc_val, exc_tb):
		# ensure the programmer is left in a safe condition (all
		# variable power supplies off, all channel drivers
		# disabled).

		# turn off power supplies
		self.pcr_enable = False

		# ensure all channel drivers are disabled (off), the DAC
		# voltages are 0'ed and the bypass capacitors disabled
		for channel in self.channels:
			channel.config = PINCON.DISABLE
			channel.bypass = False
			channel.vdac = 0
		# set all variable power supplies to 0 V
		self.vpul = 0
		self.load_dacs()	# also updates pin driver DACs
		self.vsr = 0
		self.vth = 0
		self.vtst = 0
		self.itst = 0
		self.vadjth = 0
		self.vadj = 0

		# done.  if an exception has occured, continue processing
		return False


	def set_calibration(self, calibration_file):
		# first, install default calibrations.
		#
		# NOTE:  other code might grab and retain a reference to
		# .cal, therefore do not delete it and create a new object
		# but, instead, clear its contents and re-populate it with
		# the new model.

		self.cal.clear()

		# programmer DAC curves
		self.cal.update({
			"VTH": (lambda dac: -1.01764700e-02 + 9.96709040e-02 * dac + 5.55818066e-07 * dac*dac),
			"VADJ": (lambda dac: 0.371637285 + 0.117641953 * dac + -9.13385655e-07 * dac*dac),
			"VPUL": (lambda dac: max(0., (7.14173430688944e-07 * dac + 0.09954692191382541) * dac + -0.7873764486422744))
		})

		# now overwrite with calibration model is one has been
		# supplied

		if calibration_file is None:
			return
		cal_model_data = yaml.unsafe_load(calibration_file)

		# programmer DAC curves

		# VPUL DAC
		def vpul_cal_func(dac, cal_data = cal_model_data["vpul_ramp_cal"]):
			poly2, poly1, poly0 = cal_data["poly"]
			return max(cal_data["min"], (poly2 * dac + poly1) * dac + poly0) if dac >= cal_data["threshold"] else cal_data["min"]
		self.cal["VPUL"] = vpul_cal_func

		# per channel DAC curves

		for i, channel in enumerate(self.channels):
			try:
				channel_cal_data = cal_model_data["channel%02d" % i]
			except KeyError:
				# no calibration data for this channel.
				# e.g., this is not a full 88-channel unit.
				# FIXME:  after figuring out how to
				# determine which channels are installed,
				# should add a check here to ensure that
				# all installed channels get calibration
				# data.
				continue
			channel.set_cal(channel_cal_data["vdac_ramp_cal"])


	@property
	def serial_number(self):
		"""
		The serial number reported by the USB interface's firmware,
		as a string.  This is not necessarily the historical serial
		number of the programmer hardware, nor is it necessarily a
		"number", or in any specific format, although it is
		expected to be a string that is suitable for use in
		constructing file names and messages for users.  The
		purpose is to provide an ID unique to each programmer so
		calibration files and other hardware-specific data can be
		associated with the correct device, in the event that more
		than one unit is conencted to or available to a given host.
		The value is chosen at firmware compile time, and by
		default it is a UUID, but the developer could choose to set
		it manually to the programmer's original serial number for
		consistency and/or nostalgia, if that number is known (if
		the sticker hasn't been lost).
		"""
		return self.device.serial_number


	def get_unused_bus(self, bus_obj = None):
		# NOTE:  the range() must match the size of the bus
		# definition array in the firmware source
		unused = set(range(8)) - set(self.bus)
		if not unused:
			raise KeyError("no busses available")
		# pick one
		bus_number = unused.pop()
		# if we've been given something to associate with the bus,
		# put it into the dictionary.  use None, if not, so that
		# the bus is still marked as in use
		self.bus[bus_number] = bus_obj
		return bus_number


	def release_bus(self, bus_number):
		del self.bus[bus_number]


	def read_responses(self):
		n = self.device.read(self.ep_addr_in, self.buf)
		# every response ends in a new line character.  some
		# responses are empty, and more than one such response in a
		# row become sequential new line characters.  .split()
		# normally treats them all as a single whitespace boundary,
		# but if given a specific character to split on then each
		# new line is its own boundary.  .split() also normally
		# doesn't create an extra split if the string ends in
		# whitespace, but when given a specific character to split
		# on and the string ends in that character then an
		# additional (zero length) split value is created.  since
		# every command ends in a new line, we always get one extra
		# value, which we must drop from the list
		msg = self.buf[:n].tobytes().decode("ascii").split("\n")[:-1]
		return tuple(int(x, 16) if x else None for x in msg)


	#
	# one command at a time interface
	#


	def write_command(self, verb, addr = None, val = None):
		self.device.write(self.ep_addr_out, str(command(verb, addr, val)).encode("ascii"))
		# every "out" packet generates a response "in" packet, even
		# if the commands did not produce responses (the packet is
		# empty).  we need to retrieve it unconditionally or the
		# "in" queue will fill up in the programmer
		return self.read_responses()


	#
	# command queue based interface
	#


	def push(self, command):
		# don't let the queue get too big or it won't encode into a
		# single packet
		assert len(self.out_queue) < self.command_queue_size
		self.out_queue.append(command)

	def commit(self):
		self.device.write(self.ep_addr_out, "".join(map(str, self.out_queue)).encode("ascii"))
		self.out_queue[:] = (command for command in self.out_queue if command.need_response)
		responses = self.read_responses()
		assert len(responses) == len(self.out_queue)
		for command, response in zip(self.out_queue, responses):
			command.response = response
		self.in_queue.extend(self.out_queue)
		del self.out_queue[:]

	def pop(self):
		return self.in_queue.pop(0)

	def pop_all(self):
		while self.in_queue:
			yield self.pop()

	#
	# higher level interface
	#

	@staticmethod
	def channel_addr(pin):
		"""
		Returns the start address of the register group
		corresponding to the given pin number.
		"""
		assert 0 <= pin < 88
		if pin > 0x27:
			pin += 0x18
		return pin << 4

	@property
	def socket_module_id(self):
		"""
		Returns the ID of the socket module installed in the
		programmer, or 0xff is no module is installed.
		"""
		socket_id, = self.write_command("?", 0x0280)
		return socket_id

	@property
	def system_id(self):
		# in the allpro88 documentation some command line
		# diagnostic tools are shown producing example output
		# reporting a "system ID" of 0x3 and "adapter ID" of 0x11.
		# other examples show an "analog ID" of 0x03.  the "adapter
		# ID" is the socket board ID, and mine is 0x11, like the
		# examples (kevtris' is 0x81).  but where do the "system
		# ID" and "analog ID" come from?  are they synonyms for the
		# same number?  kevtris' documentation describes an A1STAT
		# register, whose low nibble he says is hard-wired to
		# report 0x03, curiously the same as the ID in the examples
		# in the documentation.  my unit also reports 0x03 in that
		# nibble.  is this the "system ID" and/or "analog ID"?  are
		# they synonyms?  I'm guessing they are, and it is, and
		# that's what this returns.  but, I'm just making this up.
		system_id, = self.write_command("?", 0x0300)
		return system_id & 0xf


	pcr_enable = property(fset = lambda self, enable: self.write_command("=", 0x030c, PCR.ENABLE | PCR.NIDLE if enable else PCR.DISABLE))


	vsr = dacregister(address = 0x0300)
	#vth = dacregister(address = 0x0301)
	vth = dacregister(address = 0x0301, cal_key = "VTH")
	vadj = dacregister(address = 0x0302, transient = 0.05, cal_key = "VADJ")
	vadjth = dacregister(address = 0x0303)
	# must call .load_dacs() for vpul changes
	vpul = dacregister(address = 0x0305, cal_key = "VPUL")
	vtst = dacregister(address = 0x0386)
	itst = dacregister(address = 0x0387)


	def load_dacs(self, transient = 0.001):
		self.write_command("=", 0x0308, 0)
		# wait for transient response
		time.sleep(transient)


	def measure_vadj_load(self):
		"""
		Use bisection search with VADJTH to measure the adjustable
		power supply's current sense voltage, and report it as a
		fraction of the power supply's maximum output current.
		"""
		vdac, = self.write_command("V")

		# VADJTH is generated by U3 on analogue control 1, an
		# AD7226.  this chip's voltage output is Vref * (DAC value)
		# / 256 (note:  max voltage is 1 LSB less than Vref).  Vref
		# for the chip is generated by an LM317 with an adjustment
		# crazy-glued in place.  this is an important calibration
		# point in the circuit.  in mine, the Vref is +5.06 V, but
		# I believe it's meant to be 5.1 V.  since mine is out by
		# less than 1% I'm going to call that OK.

		# convert numeric DAC value to DAC output voltage
		vdac *= 5.1 / 256.

		# this value has been selected by comparing it to the
		# output of the VADJ power supply's current sense
		# amplifier.  my schematic is too blurry to figure out what
		# the sense resistor value is, so I don't know how to
		# convert voltage to current, but when the amplifier's
		# output crosses +5 V that triggers the over-current
		# shut-down circuit in the VADJ power supply, so we know
		# the allowed values are in the range [0 V, 5 V].  rather
		# than convert to a calibrated current in amperes, I return
		# a number indicating the current as a fraction of maximum.
		# nominally that means the range [0, 1.0] but if the
		# circuit fails to prevent an overload it could be seen to
		# be above that.
		return vdac / 5.0
