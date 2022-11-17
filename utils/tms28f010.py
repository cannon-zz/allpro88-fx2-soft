from tqdm import tqdm
import allpro88
import devices

class tms28f010(object):
	def __init__(self, programmer):
		self.programmer = programmer
		self.socket = programmer.socket_module.sockets["PLCC32"]
		# make sure all associated pins are disabled so they are in
		# a predictable state.
		for channel in self.socket.values():
			channel.config = allpro88.PINCON.DISABLE
			channel.vdac = 0

	def __enter__(self):
		# turn on power supplies, set VADJ to 15 V and VTH to 1.5 V
		self.programmer.pcr_enable = True
		self.programmer.vadj = self.programmer.vadj.invcal(15.)
		self.programmer.vth = self.programmer.vth.invcal(1.5)

		# configure power pins.  VPP = VCC or GND for read (use VCC)
		self.socket[1].bypass = True
		self.socket[1].config = allpro88.PINCON.VDAC
		self.socket[16].bypass = True
		self.socket[16].config = allpro88.PINCON.GND
		self.socket[32].bypass = True
		self.socket[32].config = allpro88.PINCON.VDAC
		# apply 5 V
		self.socket[1].vdac = self.socket[1].invcal(5.)
		self.socket[32].vdac = self.socket[32].invcal(5.)
		self.programmer.load_dacs()

		return self

	def __exit__(self, exc_type, exc_val, exc_tb):
		# make sure all non-power pins are disabled so they don't
		# have voltages on them when power is removed from the chip
		for pin_number, channel in self.socket.items():
			if pin_number not in (1, 16, 32):
				channel.config = allpro88.PINCON.DISABLE
		# set VDAC supplies to 0
		self.socket[1].vdac = 0
		self.socket[32].vdac = 0
		self.programmer.load_dacs()
		# now disable power
		self.socket[1].bypass = False
		self.socket[1].config = allpro88.PINCON.DISABLE
		self.socket[16].bypass = False
		self.socket[16].config = allpro88.PINCON.DISABLE
		self.socket[32].bypass = False
		self.socket[32].config = allpro88.PINCON.DISABLE

		# turn off programmer power supplies
		self.programmer.vth = 0
		self.programmer.vadj = 0
		self.programmer.pcr_enable = False

		# done.  if an exception has occured, continue processing
		return False

	address = devices.bus_ttl((12, 11, 10, 9, 8, 7, 6, 5, 27, 26, 23, 25, 4, 28, 29, 3, 2))
	data = devices.bus_ttl((13, 14, 15, 17, 18, 19, 20, 21))
	chip_enable = devices.flag_ttl_active_low(22)
	output_enable = devices.flag_ttl_active_low(24)
	write_enable = devices.flag_ttl_active_low(31)


with open("dump.dat", "wb") as dump:
	with allpro88.allpro88() as programmer:
		with tms28f010(programmer) as device:
			device.write_enable = False
			device.chip_enable = True

			for device.address in tqdm(range(2**17), desc = "Reading"):
				device.output_enable = True
				dump.write(bytearray((device.data,)))
				device.output_enable = False

			device.chip_enable = False
