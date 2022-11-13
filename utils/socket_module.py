#
# NOTE NOTE NOTE:  in all of what follows, "channel number" means a pin
# channel number according to my numbering convention, NOT any of the
# channel numbering conventions shown in the ALLPRO88 technical
# documentation (I've identified at least two).  by my convention channels
# are numbered sequentially from 0 in the order of their control register
# addresses.
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
