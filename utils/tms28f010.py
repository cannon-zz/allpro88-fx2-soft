from tqdm import tqdm
import allpro88
import devices

class tms28f010(object):
	def __init__(self, programmer):
		self.programmer = programmer
		self.socket = programmer.socket_module.sockets["PLCC32"]
		# put all pins in a predictable state.
		for channel in self.socket.values():
			channel.config = allpro88.PINCON.DISABLE
			channel.vdac = 0
			channel.bypass = False
		# VPP = VCC or GND for read (use VCC)
		self.power = devices.power(self.programmer, self.socket, {
			1: 5.0,
			16: 0.0,
			32: 5.0
		})
		# address and data buses
		self.address_bus = allpro88.bus_parallel_ttl(self.programmer, self.socket, (12, 11, 10, 9, 8, 7, 6, 5, 27, 26, 23, 25, 4, 28, 29, 3, 2))
		self.data_bus = allpro88.bus_parallel_ttl(self.programmer, self.socket, (13, 14, 15, 17, 18, 19, 20, 21))

	def __enter__(self):
		# set VTH to 1.5 V
		self.programmer.vth = allpro88.volt(1.5)
		# turn on device power
		self.power.on()
		return self

	def __exit__(self, exc_type, exc_val, exc_tb):
		# turn off power
		self.power.off()
		self.programmer.vth = 0

		# done.  if an exception has occured, continue processing
		return False

	address = devices.bus_parallel("addrses_bus")
	data = devices.bus_parallel("data_bus")
	chip_enable = devices.flag_ttl_active_low(22)
	output_enable = devices.flag_ttl_active_low(24)
	write_enable = devices.flag_ttl_active_low(31)


with open("dump.dat", "wb") as dump:
	with allpro88.allpro88() as programmer:
		with tms28f010(programmer) as device:
			device.write_enable = False
			device.chip_enable = True

			for device.address in tqdm(device.address_bus, desc = "Reading"):
				device.output_enable = True
				dump.write(bytearray((device.data,)))
				device.output_enable = False

			device.chip_enable = False
