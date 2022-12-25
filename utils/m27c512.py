from tqdm import tqdm
import allpro88
import devices

class m27c512(object):
	def __init__(self, programmer):
		self.programmer = programmer
		self.socket = programmer.socket_module.sockets["DIP28"]
		# make sure all associated pins are disabled so they are in
		# a predictable state.
		for channel in self.socket.values():
			channel.config = allpro88.PINCON.DISABLE
			channel.vdac = 0
			channel.bypass = False
		self.power = devices.power(self.programmer, self.socket, {
			14: 0.0,
			28: 5.0
		})
		# address and data buses
		self.address_bus = allpro88.bus_parallel_ttl(self.programmer, self.socket, (10, 9, 8, 7, 6, 5, 4, 3, 25, 24, 21, 23, 2, 26, 27, 1))
		self.data_bus = allpro88.bus_parallel_ttl(self.programmer, self.socket, (11, 12, 13, 15, 16, 17, 18, 19))

	def __enter__(self):
		# turn on power supplies, set VADJ to 10 V and VTH to 2 V
		self.programmer.pcr_enable = True
		self.programmer.vadj = allpro88.volt(10.)
		self.programmer.vth = allpro88.volt(2.)
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
		# turn off device power
		self.power.off()
		# turn off programmer power supplies
		self.programmer.vth = 0
		self.programmer.vadj = 0
		self.programmer.pcr_enable = False

		# done.  if an exception has occured, continue processing
		return False

	address = devices.bus_parallel("address_bus")
	data = devices.bus_parallel("data_bus")
	chip_enable = devices.flag_ttl_active_low(20)
	output_enable = devices.flag_ttl_active_low(22)


with open("dump.dat", "wb") as dump:
	with allpro88.allpro88() as programmer:
		with m27c512(programmer) as device:
			device.chip_enable = True

			for device.address in tqdm(device.address_bus, desc = "Reading"):
				device.output_enable = True
				dump.write(bytearray((device.data,)))
				device.output_enable = False

			device.chip_enable = False
