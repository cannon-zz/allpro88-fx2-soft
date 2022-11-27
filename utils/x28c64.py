from tqdm import tqdm
import allpro88
import devices

class x28c64(object):
	def __init__(self, programmer):
		self.programmer = programmer
		self.socket = programmer.socket_module.sockets["DIP28"]
		# make sure all associated pins are disabled so they are in
		# a predictable state.
		for channel in self.socket.values():
			channel.config = allpro88.PINCON.DISABLE
			channel.vdac = 0
			channel.bypass = False
		# VPP = VCC or GND for read (use VCC)
		self.power = devices.power(self.programmer, self.socket, {
			14: 0.0,
			28: 5.0
		})

	def __enter__(self):
		# turn on power supplies, set VADJ to 10 V and VTH to 1.5 V
		self.programmer.pcr_enable = True
		self.programmer.vadj = allpro88.volt(10.)
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
		# turn off device power
		self.power.off()
		# turn off programmer power supplies
		self.programmer.vth = 0
		self.programmer.vadj = 0
		self.programmer.pcr_enable = False

		# done.  if an exception has occured, continue processing
		return False

	address = devices.bus_ttl((10, 9, 8, 7, 6, 5, 4, 3, 25, 24, 21, 23, 2))
	data = devices.bus_ttl((11, 12, 13, 15, 16, 17, 18, 19))
	chip_enable = devices.flag_ttl_active_low(20)
	output_enable = devices.flag_ttl_active_low(22)
	write_enable = devices.flag_ttl_active_low(27)


with open("dump.dat", "wb") as dump:
	with allpro88.allpro88() as programmer:
		with x28c64(programmer) as device:
			# FIXME:  write_enable should be pulled high as
			# power is applied, to prevent accidentally
			# starting a write operation.  this will require
			# teaching the single-pin proxies how to initialize
			# themselves to a default state, then getting the
			# device .__enter__() handler to make it happen.
			# my hope here, in the meantime, is the device has
			# some sort of internal pull-up to safety itself in
			# the event of a floating control line, and for the
			# millisecond or so between power-on and setting
			# the state of this pin the chip can take care of
			# itself.
			device.write_enable = False
			device.chip_enable = True

			for device.address in tqdm(range(2**13), desc = "Reading"):
				device.output_enable = True
				dump.write(bytearray((device.data,)))
				device.output_enable = False

			device.chip_enable = False
