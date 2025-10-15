#
# NOTE NOTE NOTE:  in all of what follows, "channel number" means a pin
# channel number according to my numbering convention, NOT any of the
# channel numbering conventions shown in the ALLPRO88 technical
# documentation (I've identified at least two).  by my convention channels
# are numbered sequentially from 0 in the order of their control register
# addresses.
#

#
# Within the programmer, addresses 0x0280 through 0x02ff inclusively are a
# 128 word I/O window assigned to the socket module.  An active-low
# !SOCKETEN signal is available on the socket module connectors indicating
# that the value on the address bus is in this range.  The least
# significant 7 bits of the address bus then indicate which of the 128
# addresses is selected.  The PLCC socket module uses writes to these
# addresses to enable and disable bypass capacitors connected to the 48
# pins of the DIP socket.  I don't know what other socket modules do with
# these addresses.
#


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
		#
		# this must be set before calling .get_channel_proxies()
		#

		self.programmer = programmer

		#
		# convert socket pin mapping look-up table from class
		# attribute to instance attribute.  also convert socket pin
		# mappings in the look-up table from integer pin number
		# -to- integer channel mappings to integer pin number -to-
		# channel_proxy mappings.
		#

		self.sockets = dict((name, self.get_channel_proxies(pin_mapping)) for name, pin_mapping in self.sockets.items())


	def get_channel_proxies(self, pin_to_channel_mapping):
		"""
		From a dictionary mapping integer socket pin number to
		integer programmer channel number, construct and return a
		dictionary mapping integer socket pin number to programmer
		channel_proxy object.

	`	Used by subclasses to initialize themselves.
		"""
		return dict((pin, self.programmer.channels[channel]) for pin, channel in pin_to_channel_mapping.items())


	def set_bypass(self, channel, enabled):
		"""
		Enable or disable the bypass capacitor for the given
		channel number.  Not all socket modules provide
		programmable bypass capacitors, and those that do don't
		necessarily provide them for all channels.  Subclasses
		override this method to implement the behaviour.  If the
		requested channel does not support the feature, the
		operation is silently a no-op.
		"""
		pass


	def pin_lookup(self, socket_name, channel):
		"""
		Given the name of a socket on this socket module and a
		channel number, return the pin number of the given socket
		corresponding to that channel number.  This finds use in
		diagnostic programs where it can be helpful to report to
		the user which pin number a channel that is being tested
		corresponds to so that a probe can be inserted into the
		socket.

		Raises KeyError if there is no socket with the given name
		or if the channel number does not correspond to one of that
		socket's pins.
		"""
		for pin_number, channel_obj in self.sockets[socket_name].items():
			if channel_obj.channel == channel:
				return pin_number
		raise KeyError(channel)


class socket_module_DIP_MODULE(socket_module):
	name = "DIP MODULE"
	module_id = 0x02
	# I suspect this means the 40 pin DIP only socket module with the
	# single 96 pin DIN connector that shipped with the earlier
	# programmer, preceding the ALLPRO88.  if so, this should be
	# exactly compatible with the PLCC socket module, being equivalent
	# to the upper 40 pins of the 48 pin DIP socket.


class socket_module_2708(socket_module):
	name = "2708"
	module_id = 0x03
	# Logical Devices' documentation lists two different adapters for
	# code 0x03:  something called "2708" and something called "EAROM".
	# I suspect EAROM is a typo, improperly transcripted from EPROM by
	# somebody not familiar with the technical terms.  I've called this
	# just 2708.
	#
	# 2708 probably refers to the TMS2708 series EPROM parts.  these
	# require a 25 V to 27 V (26 V nominal) program pulse.  that is at
	# the very upper end of what the ALLPRO88 can deliver to a pin.  it
	# can drive a pin to a little over 25 V, which should meet the
	# minimum requirements to program one of these parts, but it's
	# maybe not 100% reliable, and if an ALLPRO88 is even just slightly
	# misadjusted it might not be able to get all the way to 25 V.
	# this is probably why a custom socket module was provided for this
	# series of parts, to ensure a higher programming reliability.
	# this socket module might be a bodge:  they might have intended to
	# support these parts natively but found it just wasn't
	# sufficiently reliable to do so, and were forced to solve the
	# problem with a separate socket module.


class socket_module_TMS370(socket_module):
	name = "TMS370"
	module_id = 0x04
	# after giving the TMS370 microcontroller family documentation a
	# brief read, I don't see why a custom socket module is required,
	# except possibly for purely physical reasons, to accomodate the 68
	# pin PLCC and 64 pin PDIP package variants (which the standard
	# socket module doesn't support).  there are plenty of TMS370
	# series parts in packages that will fit in the standard socket
	# module.


class socket_module_8789(socket_module):
	name = "8789"
	module_id = 0x05
	# don't know what this is for.


class socket_module_68HC11(socket_module):
	name = "68HC11"
	module_id = 0x06
	# the 68HC11 series parts require a current limiting feature on the
	# programming voltage supply pin.  the datasheet states that a 1
	# kOhm or 100 Ohm resistor (depending on the part) in series with
	# the programming supply is sufficient.  I'm skeptical that that is
	# the reason for a separate socket module, because I think the VTST
	# supply could be used to supply a suitable current-limited
	# programming voltage to the part.  apart from the unusual need for
	# a current limited programming voltage, the only other need for a
	# custom socket module is the need to support the 56 pin DIP
	# package and 52 pin QFP package variants, which wouldn't fit into
	# the standard socket module.


class socket_module_PAC1000(socket_module):
	name = "PAC1000"
	module_id = 0x07
	# probably refers to the PAC1000 programmable microcontroller by
	# Waferscale Integration.  briefly reading the datasheet, I don't
	# see any electrical reason to require a custom socket module to
	# support this part.  the part, however, is only available in a 100
	# pin QFP package and an 88 pin PGA package, neither of which is
	# supported by the standard socket module.  the 100 pin version has
	# more pins than a maxed-out ALLPRO88 has channels, but surely not
	# all pins need to be used to program the part.


class socket_module_AP88_PLCC(socket_module):
	"""
	ALLPRO88 Universal PLCC module.  There are two versions of this
	module.  One version is missing the 84 pin PLCC socket.  Except for
	the one socket not being installed, the two module versions are
	identical.  Which sockets can be used with your programmer is
	determined by the number of channels installed in your programmer.
	For example, a 48 channel programmer cannot use the three largest
	PLCC sockets, but can use all the others.
	"""
	name = "AP88 PLCC"
	module_id = 0x11
		# PIN NUMBER	CHANNEL NUMBER
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
			1:	26,
			2:	27,
			3:	16,
			4:	17,
			5:	18,
			6:	19,
			7:	8,
			8:	9,
			9:	10,
			10:	11,
			11:	0,
			12:	1,
			13:	2,
			14:	3,
			15:	4,
			16:	5,
			17:	6,
			18:	7,
			19:	12,
			20:	13,
			21:	14,
			22:	15,
			23:	20,
			24:	21,
			25:	22,
			26:	23,
			27:	28,
			28:	29
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
			1:	42,
			2:	43,
			3:	32,
			4:	33,
			5:	34,
			6:	35,
			7:	24,
			8:	25,
			9:	26,
			10:	27,
			11:	16,
			12:	17,
			13:	18,
			14:	19,
			15:	8,
			16:	9,
			17:	10,
			18:	11,
			19:	0,
			20:	1,
			21:	2,
			22:	3,
			23:	4,
			24:	5,
			25:	6,
			26:	7,
			27:	12,
			28:	13,
			29:	14,
			30:	15,
			31:	20,
			32:	21,
			33:	22,
			34:	23,
			35:	28,
			36:	29,
			37:	30,
			38:	31,
			39:	36,
			40:	37,
			41:	38,
			42:	39,
			43:	44,
			44:	45
		},

		# 48 pin DIP socket
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
		},

		"PLCC52": {
			1:	50,
			2:	51,
			3:	40,
			4:	41,
			5:	42,
			6:	43,
			7:	32,
			8:	33,
			9:	34,
			10:	35,
			11:	24,
			12:	25,
			13:	26,
			14:	27,
			15:	16,
			16:	17,
			17:	18,
			18:	19,
			19:	8,
			20:	9,
			21:	10,
			22:	11,
			23:	0,
			24:	1,
			25:	2,
			26:	3,
			27:	4,
			28:	5,
			29:	6,
			30:	7,
			31:	12,
			32:	13,
			33:	14,
			34:	15,
			35:	20,
			36:	21,
			37:	22,
			38:	23,
			39:	28,
			40:	29,
			41:	30,
			42:	31,
			43:	36,
			44:	37,
			45:	38,
			46:	39,
			47:	44,
			48:	45,
			49:	46,
			50:	47,
			51:	52,
			52:	53
		},

		# 68 pin PLCC socket
		"PLCC68": {
			1:	66,
			2:	67,
			3:	56,
			4:	57,
			5:	58,
			6:	59,
			7:	48,
			8:	49,
			9:	50,
			10:	51,
			11:	40,
			12:	41,
			13:	42,
			14:	43,
			15:	32,
			16:	33,
			17:	34,
			18:	35,
			19:	24,
			20:	25,
			21:	26,
			22:	27,
			23:	16,
			24:	17,
			25:	18,
			26:	19,
			27:	8,
			28:	9,
			29:	10,
			30:	11,
			31:	0,
			32:	1,
			33:	2,
			34:	3,
			35:	4,
			36:	5,
			37:	6,
			38:	7,
			39:	12,
			40:	13,
			41:	14,
			42:	15,
			43:	20,
			44:	21,
			45:	22,
			46:	23,
			47:	28,
			48:	29,
			49:	30,
			50:	31,
			51:	36,
			52:	37,
			53:	38,
			54:	39,
			55:	44,
			56:	45,
			57:	46,
			58:	47,
			59:	52,
			60:	53,
			61:	54,
			62:	55,
			63:	60,
			64:	61,
			65:	62,
			66:	63,
			67:	68,
			68:	69
		},

		# 84 pin PLCC socket
		"PLCC84": {
			1:	81,
			2:	83,
			3:	72,
			4:	73,
			5:	74,
			6:	75,
			7:	64,
			8:	65,
			9:	66,
			10:	67,
			11:	56,
			12:	57,
			13:	58,
			14:	59,
			15:	48,
			16:	49,
			17:	50,
			18:	51,
			19:	40,
			20:	41,
			21:	42,
			22:	43,
			23:	32,
			24:	33,
			25:	34,
			26:	35,
			27:	24,
			28:	25,
			29:	26,
			30:	27,
			31:	16,
			32:	17,
			33:	18,
			34:	19,
			35:	8,
			36:	9,
			37:	10,
			38:	11,
			39:	0,
			40:	1,
			41:	2,
			42:	3,
			43:	4,
			44:	5,
			45:	6,
			46:	7,
			47:	12,
			48:	13,
			49:	14,
			50:	15,
			51:	20,
			52:	21,
			53:	22,
			54:	23,
			55:	28,
			56:	29,
			57:	30,
			58:	31,
			59:	36,
			60:	37,
			61:	38,
			62:	39,
			63:	44,
			64:	45,
			65:	46,
			66:	47,
			67:	52,
			68:	53,
			69:	54,
			70:	55,
			71:	60,
			72:	61,
			73:	62,
			74:	63,
			75:	68,
			76:	69,
			77:	70,
			78:	71,
			79:	76,
			80:	77,
			81:	78,
			82:	79,
			83:	84,
			84:	85
		}
	}

	def __init__(self, *args, **kwargs):
		super(socket_module_AP88_PLCC, self).__init__(*args, **kwargs)

		# provide socket definitions for DIP packages smaller than
		# 48 pins.  these packages get inserted into the 48 pin
		# socket according to the diagram on the socket module's
		# case.  the drawing only shows 8, 16, 20, 24, 28, 32 and
		# 40 pin packages, but for completeness we generate
		# definitions for all even counts of pins starting with 2.

		for n in range(2, 48, 2):
			self.sockets["DIP%d" % n] = dict((i, self.sockets["DIP48"][24 - n // 2 + i]) for i in range(1, n + 1))


	def set_bypass(self, channel, enabled):
		# bypass capacitor is turned on and off with bit 0.
		# silently ignore requests to turn on or off bypass
		# capacitors on channels that don't have them but raise
		# ValueError if the channel number is out of range.
		if not 0 <= channel < 88:
			raise ValueError(channel)
		if channel <= 0x27:
			address = 0x280 + channel
		elif channel <= 0x2f:
			address = 0x2c0 + (channel - 0x28)
		else:
			return
		self.programmer.write_addr(address, 1 if enabled else 0)


class socket_module_68705(socket_module):
	name = "68705"
	module_id = 0x86


class socket_module_1702A(socket_module):
	name = "1702A"
	module_id = 0x98


class socket_module_68701(socket_module):
	name = "68701"
	module_id = 0xc6


class socket_module_68HC11F1(socket_module):
	name = "68HC11F1"
	module_id = 0xd6


class socket_module_1468705(socket_module):
	name = "1468705"
	module_id = 0xe6


class socket_module_68HC705(socket_module):
	name = "68HC705"
	module_id = 0xf6


#
# used to select a socket_module object based on the module ID reported by
# the programmer.  add more entries here as needed.
#


socket_modules = dict((cls.module_id, cls) for cls in (
	socket_module_DIP_MODULE,
	socket_module_2708,
	socket_module_TMS370,
	socket_module_8789,
	socket_module_68HC11,
	socket_module_PAC1000,
	socket_module_AP88_PLCC,
	socket_module_68705,
	socket_module_1702A,
	socket_module_68701,
	socket_module_68HC11F1,
	socket_module_1468705,
	socket_module_68HC705
))
