import sys
from tqdm import tqdm
import allpro88
import devices


class m27cx_width8_pulse_ce(object):
	# subclasses override these
	socket_name = ""
	voltage_maps = {}
	address_bus_pins = ()
	data_bus_pins = ()
	chip_enable_pin = 0
	output_enable_pin = 0

	def __init__(self, programmer, mode):
		self.programmer = programmer
		self.socket = programmer.socket_module.sockets[self.socket_name]
		# power pins
		self.power = devices.power(self.programmer, self.socket, self.voltage_maps, default_voltage_map = mode)
		# address and data buses
		self.address_bus = allpro88.bus_parallel_ttl(self.programmer, self.socket, self.address_bus_pins)
		self.data_bus = allpro88.bus_parallel_ttl(self.programmer, self.socket, self.data_bus_pins)
		# flags
		self.chip_enable_flag = allpro88.flag_ttl_active_low(self.socket, self.chip_enable_pin)
		self.output_enable_flag = allpro88.flag_ttl_active_low(self.socket, self.output_enable_pin)

	def __enter__(self):
		self.power.on()
		return self

	def __exit__(self, exc_type, exc_val, exc_tb):
		self.power.off()
		# done.  if an exception has occured, continue processing
		return False

	# proxy descriptors
	address = devices.bus_proxy_parallel("address_bus")
	data = devices.bus_proxy_parallel("data_bus")
	chip_enable = devices.flag_proxy("chip_enable_flag")
	output_enable = devices.flag_proxy("output_enable_flag")


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


with open("dump.dat", "wb") as dump:
	with allpro88.allpro88() as programmer:
		with m27c256(programmer, "read") as device:
			device.chip_enable = True
			for device.address in tqdm(device.address_bus, desc = "Reading"):
				device.output_enable = True
				dump.write(bytearray((device.data,)))
				device.output_enable = False
			device.chip_enable = False


with open("dump.dat", "rb") as dump:
	with allpro88.allpro88() as programmer:
		with m27c256(programmer, "program") as device:
			# these are the default states, but let's state it
			# explicitly just to be clear
			device.chip_enable = False
			device.output_enable = False
			for address in tqdm(device.address_bus, desc = "Reading", disable = False):
				device.address = address
				# read 1 byte from file
				byte = dump.read(1)
				byte = int.from_bytes(byte, byteorder = sys.byteorder)
				# write.  repeat until read-back value
				# matches byte
				for i in range(25):
					# write byte to chip
					device.data = byte
					device.chip_enable_flag.pulse(100, True, False)
					device.data = None
					# read back byte
					device.output_enable = True
					verify = device.data
					device.output_enable = False
					# equal?
					if verify == byte:
						break
				else:
					# retries exhausted
					raise ValueError("device failed:  25 tries to write 0x%X at address 0x%X, read-back is 0x%X" % (byte, address, verify))
