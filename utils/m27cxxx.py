import sys
from tqdm import tqdm
from . import allpro88
from . import devices


class m27cx_width8_pulse_ce(object):
	"""
	M27Cx style chip, 8 bit data bus, programmed by pulsing chip enable.
	"""
	# subclasses override these
	socket_name = ""
	voltage_maps = {}
	address_bus_pins = ()
	data_bus_pins = ()
	chip_enable_pin = 0
	output_enable_pin = 0
	Tpw = 100	# program pulse width in microseconds
	Vadj = "auto"

	def __init__(self, programmer, mode):
		self.programmer = programmer
		self.socket = programmer.socket_module.sockets[self.socket_name]
		if mode not in self.voltage_maps:
			raise ValueError("unknown mode \"%s\"" % mode)
		self.mode = mode
		# power pins
		self.power = devices.power(self.programmer, self.socket, self.voltage_maps, vadj = self.Vadj)
		# address and data buses
		self.address_bus = allpro88.bus_parallel_ttl(self.programmer, self.socket, self.address_bus_pins)
		self.data_bus = allpro88.bus_parallel_ttl(self.programmer, self.socket, self.data_bus_pins)
		# flags
		self.chip_enable_flag = allpro88.flag_ttl_active_low(self.socket, self.chip_enable_pin)
		self.output_enable_flag = allpro88.flag_ttl_active_low(self.socket, self.output_enable_pin)

	def __enter__(self):
		self.power.on(self.mode)
		return self

	def __exit__(self, exc_type, exc_val, exc_tb):
		self.power.off()
		# done.  if an exception has occured, continue processing
		return False

	# proxy descriptors
	address = devices.read_write_proxy("address_bus")
	data = devices.read_write_proxy("data_bus")
	chip_enable = devices.read_write_proxy("chip_enable_flag")
	output_enable = devices.read_write_proxy("output_enable_flag")

	# read/write

	@classmethod
	def read_device(cls, imgfile):
		with allpro88.allpro88() as programmer:
			with cls(programmer, "read") as device:
				device.chip_enable = True
				for device.address in tqdm(device.address_bus, desc = "Reading"):
					device.output_enable = True
					imgfile.write(bytearray((device.data,)))
					device.output_enable = False
				device.chip_enable = False

	@classmethod
	def write_device(cls, imgfile, skip_bytes = 0xff):
		"""
		imfile = file object from which to read bytes

		skip_bytes = erased parts typically reset to 0xff, so we
		don't need to write these values to the part.  only 0 bits
		are actually written to eproms. 1 bits do not change the
		contents of the part.  an all-1's value, therefore, is a
		no-op.  whatever value skip_bytes is set to will not be
		written to the part (default = 0xff).  set to None to
		disable this feature.
		"""
		# FIXME:  this has only been tested with one specific part
		# type.  before using it to burn eeproms confirm the
		# algorithm is appropriate.  I know of at least one part
		# that requires a much longer program pulse.

		# FIXME:  there isn't much error checking.  it would be
		# good to confirm the file is the correct size for the
		# part, for example, before burning bytes into the part.
		# most parts have the ability to identify themselves, to
		# confirm you have the correct part in the programmer, and
		# this code also doesn't check that.
		with allpro88.allpro88() as programmer:
			with cls(programmer, "program") as device:
				# these are the default states, and power
				# has already been applied to the device at
				# this point, but let's set these states
				# explicitly just to be clear
				device.chip_enable = False
				device.output_enable = False
				for address in tqdm(device.address_bus, desc = "Writing", disable = False):
					# read 1 byte from file
					byte = imgfile.read(1)
					byte = int.from_bytes(byte, byteorder = sys.byteorder)
					# skip no-op bytes
					if skip_bytes is not None and byte == skip_bytes:
						continue
					# write.  repeat until read-back
					# value matches byte
					device.address = address
					for i in range(25):
						# write byte to chip
						device.data = byte
						device.chip_enable_flag.pulse(device.Tpw, True, False)
		# I have seen a ROM chip that had been inserted into its
		# socket backwards, that I was testing to see if it could
		# be reprogrammed, appear to pass the verification phase in
		# this loop because, in fact, the chip was totally blown
		# and the data pins were just floating and retaining
		# voltage from when they were being driven by the
		# programmer.  to not be fooled by completely dead parts,
		# we momentarily ground the pins before attempting a read
		# back.
						device.data = 0
						device.data = None
						# read back byte
						verify = self._write_verify(device)
						# equal?
						if verify == byte:
							break
					else:
						# retries exhausted
						raise IOError("device failed:  25 tries to write 0x%X at address 0x%X, read-back is 0x%X" % (byte, address, verify))

	def _write_verify(self, device):
		# for internal use only.  configures the chip for read-back
		# during programming, reads the byte, and returns
		# configuration to programming state.  this is separated
		# out as a separate method so that it can be customized on
		# a part-by-part basis
		device.output_enable = True
		verify = device.data
		device.output_enable = False
		return verify


class m27cx_width8_program_enable(m27cx_width8_pulse_ce):
	"""
	M27Cx style chip, 8 bit data bus, programmed by asserting program enable pin.
	"""
	# subclasses override these.  see also parent class
	program_enable_pin = 0

	def __init__(self, programmer, mode):
		super(m27cx_width8_program_enable, self).__init__(programmer, mode)
		self.program_enable_flag = allpro88.flag_ttl_active_low(self.socket, self.program_enable_pin)

	# proxy descriptors.  see also parent class
	program_enable = devices.read_write_proxy("program_enable_flag")

	@classmethod
	def write_device(cls, imgfile):
		raise NotImplementedError("not yet implemented for this part")


class m27cx_width16_pulse_ce(m27cx_width8_pulse_ce):
	"""
	M27Cx style chip, 16 bit data bus, programmed by pulsing chip enable.
	"""
	# read/write

	@classmethod
	def read_device(cls, imgfile):
		with allpro88.allpro88() as programmer:
			with cls(programmer, "read") as device:
				device.chip_enable = True
				for device.address in tqdm(device.address_bus, desc = "Reading"):
					device.output_enable = True
					data = device.data
					# write low byte then high byte
					imgfile.write(bytearray((data & 0xff, data >> 8)))
					device.output_enable = False
				device.chip_enable = False

	@classmethod
	def write_device(cls, imgfile):
		raise NotImplementedError("not yet implemented for this part")


class m27cx_width16_program_enable(m27cx_width8_program_enable):
	"""
	M27Cx style chip, 16 bit data bus, programmed by asserting program enable pin.
	"""
	# read/write

	@classmethod
	def read_device(cls, imgfile):
		with allpro88.allpro88() as programmer:
			with cls(programmer, "read") as device:
				device.chip_enable = True
				for device.address in tqdm(device.address_bus, desc = "Reading"):
					device.output_enable = True
					data = device.data
					# write low byte then high byte
					imgfile.write(bytearray((data & 0xff, data >> 8)))
					device.output_enable = False
				device.chip_enable = False

	@classmethod
	def write_device(cls, imgfile):
		raise NotImplementedError("not yet implemented for this part")


class m27c32(m27cx_width8_pulse_ce):
	socket_name = "DIP24"
	voltage_maps = {
		"read": {
			12: 0.0,	# GND
			24: 5.0		# Vcc
		},
		"program": {
			12: 0.0,	# GND
			24: 6.25	# Vcc
		}
	}
	address_bus_pins = (8, 7, 6, 5, 4, 3, 2, 1, 23, 22, 19, 21)
	data_bus_pins = (9, 10, 11, 13, 14, 15, 16, 17)
	chip_enable_pin = 18
	output_enable_pin = 20	# shared with Vpp
	Vadj = 14.	# volts
	Vprog = 12.75	# volts

	def __init__(self, *args, **kwargs):
		super(m27c32, self).__init__(*args, **kwargs)
		# this chip's Vpp is shared with !OE so the pin
		# configuration requires some custom treatment.
		if self.power.default_voltage_map == "read":
			# continue with parent class' configuration (ttl
			# active low)
			pass
		elif self.power.default_voltage_map == "program":
			self.output_enable_flag = allpro88.flag_vdac_active_low(self.socket, self.output_enable_pin, self.Vprog)
		else:
			raise ValueError("unrecognized power configuration: %s" % self.power.default_voltage_map)

	def _write_verify(self, device):
		# chip enable must be set to True for this part
		device.output_enable = True
		device.chip_enable = True
		verify = device.data
		device.chip_enable = False
		device.output_enable = False
		return verify


class nmc27c16q(m27cx_width8_pulse_ce):
	socket_name = "DIP24"
	voltage_maps = {
		"read": {
			12: 0.0,	# GND
			21: 5.0,	# Vpp
			24: 5.0		# Vcc
		},
		"program": {
			12: 0.0,	# GND
			21: 12.75,	# Vpp
			24: 5.0		# Vcc
		}
	}
	address_bus_pins = (8, 7, 6, 5, 4, 3, 2, 1, 23, 22, 19)
	data_bus_pins = (9, 10, 11, 13, 14, 15, 16, 17)
	chip_enable_pin = 18
	output_enable_pin = 20
	Tpw = 100 # us


class hn462716(nmc27c16q):
	voltage_maps = {
		"read": {
			12: 0.0,	# GND
			21: 5.0,	# Vpp
			24: 5.0		# Vcc
		},
		"program": {
			12: 0.0,	# GND
			21: 25.0,	# Vpp
			24: 5.0		# Vcc
		}
	}
	Tpw = 50000	# 50 ms <--- FIXME: confirm


class hn462732(m27c32):
	voltage_maps = {
		"read": {
			12: 0.0,	# GND
			24: 5.0		# Vcc
		},
		"program": {
			12: 0.0,	# GND
			24: 5.0		# Vcc
		}
	}
	Tpw = 50000	# 50 ms
	Vadj = 27.	# volts
	Vprog = 25.	# volts


class m27c128(m27cx_width8_program_enable):
	# datasheet for M27128A-2F1
	socket_name = "DIP28"
	voltage_maps = {
		"read": {
			1: 5.0,		# Vpp
			14: 0.0,	# GND
			28: 5.0		# Vcc
		},
		"program": {
			1: 12.5,	# Vpp 12.5 V +/- 0.3 V
			14: 0.0,	# GND
			28: 6.25	# Vcc
		}
	}
	address_bus_pins = (10, 9, 8, 7, 6, 5, 4, 3, 25, 24, 21, 23, 2, 26)
	data_bus_pins = (11, 12, 13, 15, 16, 17, 18, 19)
	chip_enable_pin = 20
	output_enable_pin = 22
	program_enable_pin = 27


class m27c256(m27cx_width8_pulse_ce):
	socket_name = "DIP28"
	voltage_maps = {
		"read": {
			1: 5.0,		# Vpp
			14: 0.0,	# GND
			28: 5.0		# Vcc
		},
		"program": {
			1: 12.75,	# Vpp
			14: 0.0,	# GND
			28: 6.25	# Vcc
		}
	}
	address_bus_pins = (10, 9, 8, 7, 6, 5, 4, 3, 25, 24, 21, 23, 2, 26, 27)
	data_bus_pins = (11, 12, 13, 15, 16, 17, 18, 19)
	chip_enable_pin = 20
	output_enable_pin = 22


class m27c512(m27c256):
	voltage_maps = {
		"read": {
			14: 0.0,	# GND
			28: 5.0		# Vcc
		}
	}
	address_bus_pins = (10, 9, 8, 7, 6, 5, 4, 3, 25, 24, 21, 23, 2, 26, 27, 1)


class m27c1024(m27cx_width16_program_enable):
	socket_name = "DIP40"
	voltage_maps = {
		"read": {
			1: 5.0,
			11: 0.0,
			30: 0.0,
			40: 5.0
		}
	}
	address_bus_pins = (21, 22, 23, 24, 25, 26, 27, 28, 29, 31, 32, 33, 34, 35, 36, 37)
	data_bus_pins = (19, 18, 17, 16, 15, 14, 13, 12, 10, 9, 8, 7, 6, 5, 4, 3)
	chip_enable_pin = 2
	output_enable_pin = 20
	program_enable_pin = 39


class msm538002e(m27cx_width16_pulse_ce):
	# this part is not writable.  we choose to subclass "pulse CE"
	# because there is no program enable pin.

	# this part can be configured for 8 bit or 16 bit data buses.  what
	# is here is the 16 bit configuration because it is assumed this
	# part will only be used in applications that require a 16 bit data
	# bus (otherwise a lower pin count component would probably be more
	# convenient to work with).  in 8 bit mode half the data bus pins
	# are used, and one of the unused pins is repurposed as a new
	# least(est)-significant bit for the address bus.  all of the
	# memory is accessible in either configuration:  it is either
	# organized as 16 bit words or as twice as many 8 bit words.  for
	# that reason is mostly irrelevant what the organization is assumed
	# to be.  for the purpose of dumping an existing part and writing
	# the data into a replacement, it's completely irrelevant.
	socket_name = "DIP42"
	voltage_maps = {
		"read": {
			22: 5.0,
			12: 0.0,
			31: 0.0
		}
	}
	address_bus_pins = (10, 9, 8, 7, 6, 5, 4, 3, 41, 40, 39, 38, 37, 36, 35, 34, 33, 2, 1)
	data_bus_pins = (14, 16, 18, 20, 23, 25, 27, 29, 15, 17, 19, 21, 24, 26, 28, 30)

	def __init__(self, programmer, mode):
		super(m27cx_width16_pulse_ce, self).__init__(programmer, mode)
		# .byte_mode_flag's default is set to False (logic high).
		# this is the default default for the active low flag
		# class, but we write it explicitly here just to be clear
		# that it's required
		self.byte_mode_flag = allpro88.flag_ttl_active_low(self.socket, 32, default = False)

	# no proxy provided because this pin's state must be held fixed to
	# logic False for the address and data bus configurations to be
	# valid
	#byte_mode = devices.read_write_proxy("byte_mode_flag")

	@classmethod
	def write_device(cls, imgfile):
		raise NotImplementedError("MSM538002 is a mask ROM:  not writable")


class tms27c210a(m27c1024):
	pass


class m27c4001(m27cx_width8_pulse_ce):
	socket_name = "DIP32"
	voltage_maps = {
		"read": {
			1: 5.0,		# Vpp
			16: 0.0,	# GND
			32: 5.0		# Vcc
		},
		"program": {
			1: 12.75,	# Vpp
			16: 0.0,	# GND
			32: 6.25	# Vcc
		}
	}
	address_bus_pins = (12, 11, 10, 9, 8, 7, 6, 5, 27, 26, 23, 25, 4, 28, 29, 3, 2, 30, 31)
	data_bus_pins = (13, 14, 15, 17, 18, 19, 20, 21)
	chip_enable_pin = 22
	output_enable_pin = 24


class nm27c256v(m27cx_width8_pulse_ce):
	socket_name = "PLCC32"
	voltage_maps = {
		"read": {
			2: 5.0,		# Vpp
			16: 0.0,	# GND
			32: 5.0		# Vcc
		},
		"program": {
			2: 12.75,	# Vpp
			16: 0.0,	# GND
			32: 6.25	# Vcc
		}
	}
	address_bus_pins = (11, 10, 9, 8, 7, 6, 5, 4, 29, 28, 24, 27, 3, 30, 31)
	data_bus_pins = (13, 14, 15, 18, 19, 20, 21, 22)
	chip_enable_pin = 23
	output_enable_pin = 25


class d2764a(m27cx_width8_program_enable):
	socket_name = "DIP28"
	voltage_maps = {
		"read": {
			1: 5.0,		# Vpp
			14: 0.0,	# GND
			28: 5.0,	# Vcc
		},
		"program": {
			1: 12.5,	# Vpp
			14: 0.0,	# GND
			28: 5.0,	# Vcc
		}
	}
	address_bus_pins = (10, 9, 8, 7, 6, 5, 4, 3, 25, 24, 21, 23, 2)
	data_bus_pins = (11, 12, 13, 15, 16, 17, 18, 19)
	chip_enable_pin = 20
	output_enable_pin = 22
	program_enable_pin = 27


class m27c1001(m27cx_width8_program_enable):
	socket_name = "DIP32"
	voltage_maps = {
		"read": {
			1: 5.0,		# Vpp
			16: 0.0,	# GND
			32: 5.0		# Vcc
		},
		"program": {
			1: 12.75,	# Vpp
			16: 0.0,	# GND
			32: 6.25	# Vcc
		}
	}
	address_bus_pins = (12, 11, 10, 9, 8, 7, 6, 5, 27, 26, 23, 25, 4, 28, 29, 3, 2)
	data_bus_pins = (13, 14, 15, 17, 18, 19, 20, 21)
	chip_enable_pin = 22
	output_enable_pin = 24
	program_enable_pin = 31


class d27c010(m27c1001):
	pass


class m27c2001(m27c1001):
	address_bus_pins = (12, 11, 10, 9, 8, 7, 6, 5, 27, 26, 23, 25, 4, 28, 29, 3, 2, 30)


class am27c020(m27c2001):
	pass


class tms28f010(m27c1001):
	socket_name = "PLCC32"


class am29f040(tms28f010):
	# NOTE:  this part does not require any special programming
	# voltages.  it simply requires the write-enable pin to be set to
	# True (pulled low)
	voltage_maps = {
		"read": {
			16: 0.0,	# GND
			32: 5.0		# Vcc
		},
		"program": {
			16: 0.0,	# GND
			32: 5.0		# Vcc
		}
	}
	address_bus_pins = (12, 11, 10, 9, 8, 7, 6, 5, 27, 26, 23, 25, 4, 28, 29, 3, 2, 30, 1)


class x28c64(m27cx_width8_program_enable):
	# NOTE:  this is an EEPROM.  it does not require any special
	# programming voltages.  it simply requires the write-enable pin to
	# be set to True (pulled low)
	socket = "DIP28"
	voltage_maps = {
		"read": {
			14: 0.0,	# GND
			28: 5.0		# Vcc
		},
		"program": {
			14: 0.0,	# GND
			28: 5.0		# Vcc
		}
	}
	address_bus_pins = (10, 9, 8, 7, 6, 5, 4, 3, 25, 24, 21, 23, 2)
	data_bus_pins = (11, 12, 13, 15, 16, 17, 18, 19)
	chip_enable_pin = 20
	output_enable_pin = 22
	program_enable_pin = 27


class ds1230y(x28c64):
	# NOTE:  this is a battery-backed RAM.  it does not require any
	# special programming voltages.  it simply requires the
	# write-enable pin to be set to True (pulled low)
	address_bus_pins = (10, 9, 8, 7, 6, 5, 4, 3, 25, 24, 21, 23, 2, 26, 1)


###
#
# Entry Point
#
###


nmc27c16q.read_device(open("dump.dat", "wb"))
