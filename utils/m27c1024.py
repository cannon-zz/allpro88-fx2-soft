from tqdm import tqdm
import allpro88
import devices

class m27c1024(object):
	def __init__(self, programmer):
		self.programmer = programmer
		self.socket = programmer.socket_module.sockets["DIP40"]
		# VPP = VCC or GND for read (use VCC)
		self.power = devices.power(self.programmer, self.socket, {
			"default": {
				1: 5.0,
				11: 0.0,
				30: 0.0,
				40: 5.0
			}
		})
		# address and data buses
		self.address_bus = allpro88.bus_parallel_ttl(self.programmer, self.socket, (21, 22, 23, 24, 25, 26, 27, 28, 29, 31, 32, 33, 34, 35, 36, 37))
		self.data_bus = allpro88.bus_parallel_ttl(self.programmer, self.socket, (19, 18, 17, 16, 15, 14, 13, 12, 10, 9, 8, 7, 6, 5, 4, 3))
		# flags
		self.chip_enable_flag = allpro88.flag_ttl_active_low(self.socket, 2)
		self.output_enable_flag = allpro88.flag_ttl_active_low(self.socket, 20)
		self.program_enable_flag = allpro88.flag_ttl_active_low(self.socket, 39)

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
	output_enable = devices.flag_proxy("outout_enable_flag")
	program_enable = devices.flag_proxy("program_enable_flag")


with open("dump.dat", "wb") as dump:
	with allpro88.allpro88() as programmer:
		with m27c1024(programmer) as device:
			device.chip_enable = True

			for device.address in tqdm(device.address_bus, desc = "Reading"):
				device.output_enable = True
				data = device.data
				dump.write(bytearray((data & 0xff, data >> 8)))
				device.output_enable = False

			device.chip_enable = False
