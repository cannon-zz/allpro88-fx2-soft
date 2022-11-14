from tqdm import tqdm
import allpro88
import devices

class m27c512(object):
	def __init__(self, programmer):
		self.programmer = programmer
		self.socket = programmer.socket_module.sockets["DIP28"]
		# make sure all associated pins are disabled so they are in
		# a predictable state.
		for i in range(1, 29):
			self.socket[i].config = allpro88.PINCON.DISABLE

	def __enter__(self):
		# turn on power supplies, set VADJ to 15 V and VTH to 2 V
		self.programmer.pcr_enable = True
		self.programmer.vadj = self.programmer.vadj.invcal(15.)
		self.programmer.vth = self.programmer.vth.invcal(2.)

		# configure power pins
		self.socket[14].config = allpro88.PINCON.GND
		self.socket[28].config = allpro88.PINCON.VDAC
		# apply 5 V
		self.socket[28].vdac = self.socket[28].invcal(5.)
		self.programmer.load_dacs()

		return self

	def __exit__(self, exc_type, exc_val, exc_tb):
		# make sure all non-power pins are disabled so they don't
		# have voltages on them when power is removed from the chip
		for i in range(1, 29):
			if i not in (14, 28):
				self.socket[i].config = allpro88.PINCON.DISABLE
		# set VDAC supply to 0
		self.socket[28].vdac = 0
		self.programmer.load_dacs()
		# now disable power
		self.socket[14].config = allpro88.PINCON.DISABLE
		self.socket[28].config = allpro88.PINCON.DISABLE

		# turn off programmer power supplies
		self.programmer.vth = 0
		self.programmer.vadj = 0
		self.programmer.pcr_enable = False

		# done.  if an exception has occured, continue processing
		return False

	address_bus = devices.bus((10, 9, 8, 7, 6, 5, 4, 3, 25, 24, 21, 23, 2, 26, 27, 1))
	data_bus = devices.bus((11, 12, 13, 15, 16, 17, 18, 19))
	chip_enable = devices.flag(20, inactive = allpro88.PINCON.LOGICH, active = allpro88.PINCON.LOGICL)
	output_enable = devices.flag(22, inactive = allpro88.PINCON.LOGICH, active = allpro88.PINCON.LOGICL)


with open("dump.dat", "wb") as dump:
	with allpro88.allpro88() as programmer:
		with m27c512(programmer) as device:
			device.chip_enable = True

			for device.address_bus in tqdm(range(0x10000), desc = "Reading"):
				device.output_enable = True
				dump.write(bytearray((device.data_bus,)))
				device.output_enable = False

			device.chip_enable = False
