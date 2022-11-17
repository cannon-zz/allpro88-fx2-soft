from tqdm import tqdm
import allpro88
import devices

class hn462732(object):
	def __init__(self, programmer):
		self.programmer = programmer
		self.socket = programmer.socket_module.sockets["DIP24"]
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

		# configure power pins
		self.socket[12].bypass = True
		self.socket[12].config = allpro88.PINCON.GND
		self.socket[24].bypass = True
		self.socket[24].config = allpro88.PINCON.VDAC
		# apply 5 V
		self.socket[24].vdac = self.socket[24].invcal(5.)
		self.programmer.load_dacs()

		return self

	def __exit__(self, exc_type, exc_val, exc_tb):
		# make sure all non-power pins are disabled so they don't
		# have voltages on them when power is removed from the chip
		for pin_number, channel in self.socket.items():
			if pin_number not in (12, 24):
				channel.config = allpro88.PINCON.DISABLE
		# set VDAC supply to 0
		self.socket[24].vdac = 0
		self.programmer.load_dacs()
		# now disable power
		self.socket[12].bypass = False
		self.socket[12].config = allpro88.PINCON.DISABLE
		self.socket[24].bypass = False
		self.socket[24].config = allpro88.PINCON.DISABLE

		# turn off programmer power supplies
		self.programmer.vth = 0
		self.programmer.vadj = 0
		self.programmer.pcr_enable = False

		# done.  if an exception has occured, continue processing
		return False

	address = devices.bus_ttl((8, 7, 6, 5, 4, 3, 2, 1, 23, 22, 19, 21))
	data = devices.bus_ttl((9, 10, 11, 13, 14, 15, 16, 17))
	chip_enable = devices.flag_ttl_active_low(18)
	output_enable = devices.flag_ttl_active_low(20)


with open("dump.dat", "wb") as dump:
	with allpro88.allpro88() as programmer:
		with hn462732(programmer) as device:
			device.chip_enable = True

			for device.address in tqdm(range(0x1000), desc = "Reading"):
				device.output_enable = True
				dump.write(bytearray((device.data,)))
				device.output_enable = False

			device.chip_enable = False
