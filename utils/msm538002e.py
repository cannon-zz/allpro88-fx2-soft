from tqdm import tqdm
import allpro88
import devices

class msm538002e(object):
	def __init__(self, programmer):
		self.programmer = programmer
		self.socket = programmer.socket_module.sockets["DIP42"]
		# put all pins in a predictable state.
		for channel in self.socket.values():
			channel.config = allpro88.PINCON.DISABLE
			channel.vdac = 0
			channel.bypass = False
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

	def __enter__(self):
		# turn on device power
		self.power.on()
		return self

	def __exit__(self, exc_type, exc_val, exc_tb):
		# turn off power
		self.power.off()

		# done.  if an exception has occured, continue processing
		return False

	address = devices.bus_proxy_parallel("address_bus")
	data = devices.bus_proxy_parallel("data_bus")
	chip_enable = devices.flag_ttl_active_low(11)
	output_enable = devices.flag_ttl_active_low(13)
	byte_mode = devices.flag_ttl_active_low(32)


with open("dump.dat", "wb") as dump:
	with allpro88.allpro88() as programmer:
		with msm538002e(programmer) as device:
			device.byte_mode = False
			device.chip_enable = True

			for device.address in tqdm(device.address_bus, desc = "Reading"):
				device.output_enable = True
				data = device.data
				dump.write(bytearray((data & 0xff, data >> 8)))
				device.output_enable = False

			device.chip_enable = False
