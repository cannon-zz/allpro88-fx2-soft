from tqdm import tqdm
import allpro88
import devices

class msm538002e(object):
	def __init__(self, programmer):
		self.programmer = programmer
		self.socket = programmer.socket_module.sockets["DIP42"]
		# VPP = VCC or GND for read (use VCC)
		self.power = devices.power(self.programmer, self.socket, {
			"default": {
				22: 5.0,
				12: 0.0,
				31: 0.0
			}
		})
		# address and data buses
		# these are the address bus and data bus definitions for
		# word-mode addressing.  in byte-mode addressing, data bus
		# bit 15 (MSB) is used as the LSB of the address bus
		# (adding 1 additional bit).  NOTE:  for the configuration
		# here, the .byte_mode flag must be set to False
		self.address_bus = allpro88.bus_parallel_ttl(self.programmer, self.socket, (10, 9, 8, 7, 6, 5, 4, 3, 41, 40, 39, 38, 37, 36, 35, 34, 33, 2, 1))
		self.data_bus = allpro88.bus_parallel_ttl(self.programmer, self.socket, (14, 16, 18, 20, 23, 25, 27, 29, 15, 17, 19, 21, 24, 26, 28, 30))
		# flags.  .byte_mode_flag's default is set to False.  this
		# is the default default, but we write it explicitly here
		# just to be clear that it's required
		self.chip_enable_flag = allpro88.flag_ttl_active_low(self.socket, 11)
		self.output_enable_flag = allpro88.flag_ttl_active_low(self.socket, 13)
		self.byte_mode_flag = allpro88.flag_ttl_active_low(self.socket, 32, default = False)

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
	# no proxy provided because this pin's state must be set to logic
	# Flase for the address and data bus configurations to be valid
	#byte_mode = devices.flag_proxy("byte_mode_flag")


with open("dump.dat", "wb") as dump:
	with allpro88.allpro88() as programmer:
		with msm538002e(programmer) as device:
			device.chip_enable = True

			for device.address in tqdm(device.address_bus, desc = "Reading"):
				device.output_enable = True
				data = device.data
				dump.write(bytearray((data & 0xff, data >> 8)))
				device.output_enable = False

			device.chip_enable = False
