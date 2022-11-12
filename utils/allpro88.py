from enum import IntEnum
import usb.core


#
# NOTE NOTE NOTE:  in all of what follows, "channel number" means a pin
# channel number according to my numbering convention, NOT any of the
# channel numbering conventions shown in the ALLPRO88 technical
# documentation (I've identified at least two).  by my convention channels
# are numbered sequentially from 0 in the order of their control register
# addresses.
#


class PCR(IntEnum):
	# power supplies off, red busy LED off, green idle LED on
	DISABLE = 0x00
	# enables power supplies, and lights red busy LED
	ENABLE = 0x01
	# turns off green idle LED
	NIDLE = 0x02


class PINCON(IntEnum):
	DISABLE = 0x00
	# "Ground Driver"
	GND = 0x01
	# "Power Source Driver"
	VDAC = 0x02
	# "Current Source Driver"
	VTST = 0x04
	# "Logic (TTL) High Driver"
	LOGICH = 0x08
	# "Pull-up Driver"
	PULLUP = 0x10
	LOGICL = 0x20
	POSCLK = 0x40
	NEGCLK = 0x60
	# "Pull-down Driver"
	PULLDN = 0x80


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


class socket_module(object):
	#
	# subclasses over-ride these
	#
	# .name is human readable name of the socket module for user's
	# benefit
	#
	# .module_id is integer code hard-wired into socket module.  used
	# by programmer class to decide which socket module is installed.
	#
	# .sockets class attribute is socket name --> (pin number -->
	# channel number) mapping.  the __init__() method overrides this
	# with an instance attribute providing the same mapping structure,
	# but in which the numerical channel numbers are replaced with
	# channel proxy objects from the programmer instance.
	#

	name = None
	module_id = None
	sockets = {}

	def __init__(self, programmer):
		self.programmer = programmer

		#
		# convert socket pin mapping look-up table from class
		# attribute to instance attribute.  also convert socket pin
		# mappings in the look-up table from integer pin number
		# -to- integer channel mappings to integer pin number -to-
		# channel_proxy mappings.
		#

		self.sockets = dict((name, self.get_channel_proxies(programmer, pin_mapping)) for name, pin_mapping in self.sockets.items())


	@staticmethod
	def get_channel_proxies(programmer, pin_to_channel_mapping):
		"""
		From a dictionary mapping integer socket pin number to
		integer programmer channel number, construct and return a
		dictionary mapping integer socket pin number to programmer
		channel_proxy object.

	`	Used by subclasses to initialize themselves.
		"""
		return dict((pin, programmer.channel[channel]) for pin, channel in pin_to_channel_mapping.items())


	def pin_lookup(self, socket_name, channel):
		"""
		Given the name of a socket on this socket module and a
		channel number, return the pin number of the given socket
		corresponding to that channel number.  This finds use in
		diagnostic programs where it can be helpful to report to
		the user which pin number a channel that is being tested
		corresponds to so that a probe can be inserted into the
		socket.

		Raises KeyError if the channel number does not correspond
		to one of the socket's pins.
		"""
		for pin_number, channel_obj in self.sockets[socket_name].items():
			if channel_obj.channel == channel:
				return pin_number
		raise KeyError(channel)


class socket_module_AP88_PLCC(socket_module):
	name = "AP88 PLCC"
	module_id = 0x11
	sockets = {
		# 20 pin PLCC socket
		"PLCC20": {
			1:	19,
			2:	8,
			3:	9,
			4:	10,
			5:	11,
			6:	0,
			7:	1,
			8:	2,
			9:	3,
			10:	4,
			11:	5,
			12:	6,
			13:	7,
			14:	12,
			15:	13,
			16:	14,
			17:	15,
			18:	20,
			19:	21,
			20:	18
		},

		# 28 pin PLCC socket
		"PLCC28": {
			# FIXME
		},

		# 32 pin PLCC socket
		"PLCC32": {
			1:	24,
			2:	25,
			3:	26,
			4:	27,
			5:	16,
			6:	17,
			7:	18,
			8:	19,
			9:	8,
			10:	9,
			11:	10,
			12:	11,
			13:	0,
			14:	1,
			15:	2,
			16:	3,
			17:	4,
			18:	5,
			19:	6,
			20:	7,
			21:	12,
			22:	13,
			23:	14,
			24:	15,
			25:	20,
			26:	21,
			27:	22,
			28:	23,
			29:	28,
			30:	29,
			31:	30,
			32:	31
		},

		# 44 pin PLCC socket
		"PLCC44": {
			# FIXME
		},

		# 48 pin ZIF socket
		"DIP48": {
			1:	40,
			2:	41,
			3:	42,
			4:	43,
			5:	32,
			6:	33,
			7:	34,
			8:	35,
			9:	24,
			10:	25,
			11:	26,
			12:	27,
			13:	16,
			14:	17,
			15:	18,
			16:	19,
			17:	8,
			18:	9,
			19:	10,
			20:	11,
			21:	0,
			22:	1,
			23:	2,
			24:	3,
			25:	4,
			26:	5,
			27:	6,
			28:	7,
			29:	12,
			30:	13,
			31:	14,
			32:	15,
			33:	20,
			34:	21,
			35:	22,
			36:	23,
			37:	28,
			38:	29,
			39:	30,
			40:	31,
			41:	36,
			42:	37,
			43:	38,
			44:	39,
			45:	44,
			46:	45,
			47:	46,
			48:	47
		}
	}

	def __init__(self, *args, **kwargs):
		super(socket_module_AP88_PLCC, self).__init__(*args, **kwargs)

		# provide socket definitions for DIP packages smaller than
		# 48 pins.  these packages get inserted into the 48 pin
		# socket according to the diagram on the socket module,
		# the drawing only shows 8, 16, 20, 24, 28, 32 and 40 pin
		# packages, but for completeness we generate definitions
		# for all even counts of pins starting with 2.

		for n in range(2, 48, 2):
			self.sockets["DIP%d" % n] = dict((i, self.sockets["DIP48"][24 - n // 2 + i]) for i in range(1, n + 1))


class socket_module_DIP_MODULE(socket_module):
	name = "DIP MODULE"
	module_id = 0x02


class socket_module_TMS370(socket_module):
	name = "TMS370"
	module_id = 0x04


class socket_module_2708_EAROM(socket_module):
	name = "2708 / EAROM"
	# Logical Devices' documentation lists two different adapters for
	# code 0x03:  something called "2708" and something called "EAROM",
	# so I've combined their names
	module_id = 0x03


class socket_module_PAC1000(socket_module):
	name = "PAC1000"
	module_id = 0x07


class socket_module_8789(socket_module):
	name = "8789"
	module_id = 0x05


class socket_module_1702A(socket_module):
	name = "1702A"
	module_id = 0x98


class socket_module_68HC11(socket_module):
	name = "68HC11"
	module_id = 0x06


class socket_module_68701(socket_module):
	name = "68701"
	module_id = 0xc6


class socket_module_68705(socket_module):
	name = "68705"
	module_id = 0x86


class socket_module_68HC705(socket_module):
	name = "68HC705"
	module_id = 0xf6


class socket_module_1468705(socket_module):
	name = "1468705"
	module_id = 0xe6


class socket_module_68HC11F1(socket_module):
	name = "68HC11F1"
	module_id = 0xd6


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
			# measure voltage using VPIN
			assert val is None
			self.cmd = "M%02X\n" % addr
			self.need_response = True
		elif verb == "R":
			# reset
			assert addr is None and val is None
			self.cmd = "R\n"
			self.need_response = False
		else:
			raise ValueError("invalid command \"%s\"" % cmd)
		self.response = None

	def __str__(self):
		return self.cmd


class dacregister(object):
	"""
	Write a value to a DAC register.  Provides type conversion and
	range checking to ensure the value written is allowed.
	"""
	def __init__(self, address):
		self.address = address

	@staticmethod
	def ensure_dac_value(dac):
		# test type cast to int
		dac = int(dac)
		# verify range
		if not 0 <= dac <= 255:
			raise ValueError("0 <= dac <= 255:  %d" % dac)
		# OK
		return dac

	def __set__(self, obj, dac):
		# write value to programmer register
		obj.write_command("=", self.address, self.ensure_dac_value(dac))


class channel_proxy(object):
	def __init__(self, programmer, channel):
		self.programmer = programmer
		self.channel = channel
		self.address = programmer.pin_addr(channel)

	def measure_v(self):
		"""
		Use bisection search with VPIN to measure the voltage on a
		pin.  NOTE:  VPIN is left set to (an approximation of) the
		measured voltage.
		"""
		vdac, = self.programmer.write_command("M", self.channel)
		return vdac / 10.

	vdac = property(fset = lambda self, dac: self.programmer.write_command("=", self.address + 3, dacregister.ensure_dac_value(dac)))

	config = property(fset = lambda self, config: self.programmer.write_command("=", self.address, config))



class allpro88(object):
	idVendor = 0x04b4
	idProduct = 0x1004

	ep_addr_out = 0x02
	ep_addr_in = 0x86

	buf_size = 512	# bytes

	command_queue_size = 64	# commands

	# used by .__init__() to select a socket_module object based on the
	# module ID reported by the programmer.  add more entries hear as
	# needed.
	socket_modules = dict((cls.module_id, cls) for cls in (socket_module_AP88_PLCC, socket_module_DIP_MODULE, socket_module_TMS370, socket_module_2708_EAROM, socket_module_PAC1000, socket_module_8789, socket_module_1702A, socket_module_68HC11, socket_module_68701, socket_module_68705, socket_module_68HC705, socket_module_1468705, socket_module_68HC11F1))

	def __init__(self):
		self.buf = usb.core.array.array("B", (0,) * self.buf_size)
		self.device = usb.core.find(idVendor = self.idVendor, idProduct = self.idProduct)
		if self.device is None:
			raise ValueError("USB device not found (vid:pid = %04X:%04X)" % (self.idVendor, self.idProduct))

		# firmware resets itself and the programmer
		self.device.set_configuration()

		# initialize channel proxy dictionary.  NOTE:  this step
		# must be completed before initializing the socket_module
		# attribute (the socket_module classes use this dictionary
		# to initialize their pin mappings
		self.channel = dict((i, channel_proxy(self, i)) for i in range(88))

		# command queues
		self.out_queue = []
		self.in_queue = []

		# configure for the installed socket module
		try:
			self.socket_module = self.socket_modules[self.socket_module_id](self)
		except KeyError as e:
			if self.socket_module_id == 0xff:
				print("warning:  no socket module detected")
			else:
				print("warning:  unrecognized socket module ID 0x%02X" % self.socket_module_id)
			self.socket_module = None


	def __enter__(self):
		# ensure the programmer is left in a safe condition (all
		# variable power supplies off, all channel drivers
		# disabled).

		# ensure all channel drivers are disabled (off)
		for channel in self.channel.values():
			channel.config = PINCON.DISABLE
		# set all variable power supplies to 0 V
		self.vpin = 0
		self.vpul = 0
		self.load_dacs()
		self.vtst = 0
		self.itst = 0
		self.vadj = 0
		# turn off power supplies
		self.pcr_enable = False

		# done
		return self


	def __exit__(self, exc_type, exc_val, exc_tb):
		# ensure the programmer is left in a safe condition (all
		# variable power supplies off, all channel drivers
		# disabled).

		# ensure all channel drivers are disabled (off)
		for channel in self.channel.values():
			channel.config = PINCON.DISABLE
		# set all variable power supplies to 0 V
		self.vpin = 0
		self.vpul = 0
		self.load_dacs()
		self.vtst = 0
		self.itst = 0
		self.vadj = 0
		# turn off power supplies
		self.pcr_enable = False

		# done.  if an exception has occured, continue processing
		return False


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
	def pin_addr(pin):
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


	vpin = dacregister(0x0301)
	vadj = dacregister(0x0302)
	vpul = dacregister(0x0305)	# must call .load_dacs()
	vtst = dacregister(0x0386)
	itst = dacregister(0x0387)


	def load_dacs(self):
		self.write_command("=", 0x0308, 0)
