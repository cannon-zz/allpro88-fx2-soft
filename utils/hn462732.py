from tqdm import tqdm
import allpro88
import devices

class hn462732(object):
	def __init__(self, programmer):
		self.programmer = programmer
		self.socket = programmer.socket_module.sockets["DIP24"]
		self.power = devices.power(self.programmer, self.socket, {
			"default": {
				12: 0.0
				24: 5.0
			}
		})
		# address and data buses
		self.address_bus = allpro88.bus_parallel_ttl(self.programmer, self.socket, (8, 7, 6, 5, 4, 3, 2, 1, 23, 22, 19, 21))
		self.data_bus = allpro88.bus_parallel_ttl(self.programmer, self.socket, (9, 10, 11, 13, 14, 15, 16, 17))
		# flags
		self.chip_enable_flag = allpro88.flag_ttl_active_low(self.socket, 18)
		self.output_enable_flag = allpro88.flag_ttl_active_low(self.socket, 20)

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


with open("dump.dat", "wb") as dump:
	with allpro88.allpro88() as programmer:
		with hn462732(programmer) as device:
			device.chip_enable = True

			for device.address in tqdm(device.address_bus, desc = "Reading"):
				device.output_enable = True
				dump.write(bytearray((device.data,)))
				device.output_enable = False

			device.chip_enable = False
