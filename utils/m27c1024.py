from tqdm import tqdm
import allpro88
import devices

class m27c1024(object):
	def __init__(self, programmer):
		self.programmer = programmer
		self.socket = programmer.socket_module.sockets["DIP40"]
		# make sure all associated pins are disabled so they are in
		# a predictable state.
		for channel in self.socket.values():
			channel.config = allpro88.PINCON.DISABLE
			channel.vdac = 0
			channel.bypass = False
		# VPP = VCC or GND for read (use VCC)
		self.power = devices.power(self.programmer, self.socket, {
			1: 5.0,
			11: 0.0,
			30: 0.0,
			40: 5.0
		})
		# address and data buses
		self.address_bus = allpro88.bus_parallel_ttl(self.programmer, self.socket, (21, 22, 23, 24, 25, 26, 27, 28, 29, 31, 32, 33, 34, 35, 36, 37))
		self.data_bus = allpro88.bus_parallel_ttl(self.programmer, self.socket, (19, 18, 17, 16, 15, 14, 13, 12, 10, 9, 8, 7, 6, 5, 4, 3))

	def __enter__(self):
		# set VTH to 1.5 V
		self.programmer.vth = allpro88.volt(1.5)
		# turn on device power
		self.power.on()
		return self

	def __exit__(self, exc_type, exc_val, exc_tb):
		# make sure all non-power pins are disabled so they don't
		# have voltages on them when power is removed from the chip
		for pin_number, channel in self.socket.items():
			if pin_number not in self.power.pins:
				channel.config = allpro88.PINCON.DISABLE
				channel.vdac = 0
				channel.bypass = False
		# turn off power
		self.power.off()
		self.programmer.vth = 0

		# done.  if an exception has occured, continue processing
		return False

	address = devices.bus_parallel("address_bus")
	data = devices.bus_parallel("data_bus")
	chip_enable = devices.flag_ttl_active_low(2)
	output_enable = devices.flag_ttl_active_low(20)
	program_enable = devices.flag_ttl_active_low(39)


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
