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

	def __enter__(self):
		# turn on power supplies, set VADJ to 15 V and VTH to 1.5 V
		self.programmer.pcr_enable = True
		self.programmer.vadj = self.programmer.vadj.invcal(15.)
		self.programmer.vth = self.programmer.vth.invcal(1.5)

		# configure power pins.  VPP = VCC or GND for read (use VCC)
		self.socket[1].bypass = True
		self.socket[1].config = allpro88.PINCON.VDAC
		self.socket[11].bypass = True
		self.socket[11].config = allpro88.PINCON.GND
		self.socket[30].bypass = True
		self.socket[30].config = allpro88.PINCON.GND
		self.socket[40].bypass = True
		self.socket[40].config = allpro88.PINCON.VDAC
		# apply 5 V
		self.socket[1].vdac = self.socket[1].invcal(5.)
		self.socket[40].vdac = self.socket[40].invcal(5.)
		self.programmer.load_dacs()

		return self

	def __exit__(self, exc_type, exc_val, exc_tb):
		# make sure all non-power pins are disabled so they don't
		# have voltages on them when power is removed from the chip
		for pin_number, channel in self.socket.items():
			if pin_number not in (1, 11, 30, 40):
				channel.config = allpro88.PINCON.DISABLE
		# set VDAC supplies to 0
		self.socket[1].vdac = 0
		self.socket[40].vdac = 0
		self.programmer.load_dacs()
		# now disable power
		self.socket[1].bypass = False
		self.socket[1].config = allpro88.PINCON.DISABLE
		self.socket[11].bypass = False
		self.socket[11].config = allpro88.PINCON.DISABLE
		self.socket[30].bypass = False
		self.socket[30].config = allpro88.PINCON.DISABLE
		self.socket[40].bypass = False
		self.socket[40].config = allpro88.PINCON.DISABLE

		# turn off programmer power supplies
		self.programmer.vth = 0
		self.programmer.vadj = 0
		self.programmer.pcr_enable = False

		# done.  if an exception has occured, continue processing
		return False

	address = devices.bus_ttl((21, 22, 23, 24, 25, 26, 27, 28, 29, 31, 32, 33, 34, 35, 36, 37))
	data = devices.bus_ttl((19, 18, 17, 16, 15, 14, 13, 12, 10, 9, 8, 7, 6, 5, 4, 3))
	chip_enable = devices.flag_ttl_active_low(2)
	output_enable = devices.flag_ttl_active_low(20)
	program_enable = devices.flag_ttl_active_low(39)


with open("dump.dat", "wb") as dump:
	with allpro88.allpro88() as programmer:
		with m27c1024(programmer) as device:
			device.chip_enable = True

			for device.address in tqdm(range(2**16), desc = "Reading"):
				device.output_enable = True
				data = device.data
				dump.write(bytearray((data & 0xff, data >> 8)))
				device.output_enable = False

			device.chip_enable = False
