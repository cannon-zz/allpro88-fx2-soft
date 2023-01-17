from tqdm import tqdm
import allpro88
import devices

class nm27c256v(object):
	def __init__(self, programmer):
		self.programmer = programmer
		self.socket = programmer.socket_module.sockets["PLCC32"]
		# VPP = VCC or GND for read (use VCC)
		self.power = devices.power(self.programmer, self.socket, {
			"default": {
				2: 5.0,
				16: 0.0,
				32: 5.0
			}
		})
		# address and data buses
		self.address_bus = allpro88.bus_parallel_ttl(self.programmer, self.socket, (11, 10, 9, 8, 7, 6, 5, 4, 29, 28, 24, 27, 3, 30, 31))
		self.data_bus = allpro88.bus_parallel_ttl(self.programmer, self.socket, (13, 14, 15, 18, 19, 20, 21, 22))
		# flags
		self.chip_enable_flag = allpro88.flag_ttl_active_low(self.socket, 23)
		self.output_enable_flag = allpro88.flag_ttl_active_low(self.socket, 25)

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


with open("dump.dat", "wb") as dump:
	with allpro88.allpro88() as programmer:
		with nm27c256v(programmer) as device:
			device.chip_enable = True

			for device.address in tqdm(device.address_bus, desc = "Reading"):
				device.output_enable = True
				dump.write(bytearray((device.data,)))
				device.output_enable = False

			device.chip_enable = False
