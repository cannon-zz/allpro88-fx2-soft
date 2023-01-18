import sys
from tqdm import tqdm
import allpro88
import devices

class m27c256(object):
	def __init__(self, programmer, mode):
		self.programmer = programmer
		self.socket = programmer.socket_module.sockets["DIP28"]
		# power pins
		self.power = devices.power(self.programmer, self.socket, {
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
		}, default_voltage_map = mode, vth = 2.0)
		# address and data buses
		self.address_bus = allpro88.bus_parallel_ttl(self.programmer, self.socket, (10, 9, 8, 7, 6, 5, 4, 3, 25, 24, 21, 23, 2, 26, 27))
		self.data_bus = allpro88.bus_parallel_ttl(self.programmer, self.socket, (11, 12, 13, 15, 16, 17, 18, 19))
		# flags
		self.chip_enable_flag = allpro88.flag_ttl_active_low(self.socket, 20)
		self.output_enable_flag = allpro88.flag_ttl_active_low(self.socket, 22)

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


with open("dump.dat", "rb") as dump:
	with allpro88.allpro88() as programmer:
		with m27c256(programmer, "program") as device:
			# these are the default states, but let's state it
			# explicitly just to be clear
			device.chip_enable = False
			device.output_enable = False
			for device.address in tqdm(device.address_bus, desc = "Reading", disable = False):
				byte = dump.read(1)
				byte = int.from_bytes(byte, byteorder = sys.byteorder)
				# loop until read-back value matches byte
				verify = None
				while verify != byte:
					# write byte to chip
					device.data = byte
					device.chip_enable_flag.pulse(100, True, False)
					device.data = None
					# read back byte
					device.output_enable = True
					verify = device.data
					device.output_enable = False


with open("dump.dat", "wb") as dump:
	with allpro88.allpro88() as programmer:
		with m27c256(programmer, "read") as device:
			device.chip_enable = True
			for device.address in tqdm(device.address_bus, desc = "Reading"):
				device.output_enable = True
				dump.write(bytearray((device.data,)))
				device.output_enable = False
			device.chip_enable = False
