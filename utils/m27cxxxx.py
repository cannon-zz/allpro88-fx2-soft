from tqdm import tqdm
import allpro88
import devices


class m27cxxxx(object):
	# subclasses override these
	socket_name = ""
	voltage_maps = {}
	address_bus_pins = ()
	data_bus_pins = ()
	chip_enable_pin = 0
	output_enable_pin = 0
	program_enable_pin = 0

	def __init__(self, programmer, mode):
		self.programmer = programmer
		self.socket = programmer.socket_module.sockets[self.socket_name]
		self.power = devices.power(self.programmer, self.socket, self.voltage_maps, default_voltage_map = mode)
		# address and data buses
		self.address_bus = allpro88.bus_parallel_ttl(self.programmer, self.socket, self.address_bus_pins)
		self.data_bus = allpro88.bus_parallel_ttl(self.programmer, self.socket, self.data_bus_pins)
		# flags
		self.chip_enable_flag = allpro88.flag_ttl_active_low(self.socket, self.chip_enable_pin)
		self.output_enable_flag = allpro88.flag_ttl_active_low(self.socket, self.output_enable_pin)
		self.program_enable_flag = allpro88.flag_ttl_active_low(self.socket, self.program_enable_pin)

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
	program_enable = devices.flag_proxy("program_enable_flag")


class m27c1001(m27cxxxx):
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


class m27c2001(m27c1001):
	address_bus_pins = (12, 11, 10, 9, 8, 7, 6, 5, 27, 26, 23, 25, 4, 28, 29, 3, 2, 30)


class am27c020(m27c2001):
	pass


class tms28f010(m27c1001):
	socket_name = "PLCC32"


with open("dump.dat", "wb") as dump:
	with allpro88.allpro88() as programmer:
		with m27c1001(programmer, "read") as device:
			device.chip_enable = True
			for device.address in tqdm(device.address_bus, desc = "Reading"):
				device.output_enable = True
				dump.write(bytearray((device.data,)))
				device.output_enable = False
			device.chip_enable = False
