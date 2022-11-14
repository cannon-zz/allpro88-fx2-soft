from tqdm import tqdm
import allpro88

class m27c256(object):
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

		# configure power pins.  VPP = VCC for read
		self.socket[1].config = allpro88.PINCON.VDAC
		self.socket[14].config = allpro88.PINCON.GND
		self.socket[28].config = allpro88.PINCON.VDAC
		# apply 5 V
		self.socket[1].vdac = self.socket[1].invcal(5.)
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

	@property
	def address_bus(self):
		"""
		Tuple of address bus channel objects from MSB to LSB.
		"""
		return tuple(self.socket[i] for i in (27, 26, 2, 23, 21, 24, 25, 3, 4, 5, 6, 7, 8, 9, 10))

	@property
	def data_bus(self):
		"""
		Tuple of data bus channel objects from MSB to LSB.
		"""
		return tuple(self.socket[i] for i in (19, 18, 17, 16, 15, 13, 12, 11))

	@property
	def chip_enable(self):
		"""
		Active low chip enable channel object.
		"""
		raise NotImplemented

	@chip_enable.setter
	def chip_enable(self, boolean):
		self.socket[20] = allpro88.PINCON.LOGICL if boolean else allpro88.PINCON.LOGICH

	@property
	def output_enable(self):
		"""
		Active low output enable channel object.
		"""
		raise NotImplementedError

	@output_enable.setter
	def output_enable(self, boolean):
		self.socket[22] = allpro88.PINCON.LOGICL if boolean else allpro88.PINCON.LOGICH

	@property
	def address(self):
		raise NotImplementedError

	@address.setter
	def address(self, addr):
		# check type compatibility and range
		addr = int(addr)
		if not (0 <= addr <= 0x7fff):
			raise ValueError("0 <= addr <= 0x7FFF: 0x%X" % addr)
		bit = 0x4000
		for pin in self.address_bus:
			pin.config = allpro88.PINCON.LOGICH if (addr & bit) else allpro88.PINCON.LOGICL
			bit >>= 1

	@property
	def data(self):
		data = 0
		bit = 0x80
		for pin in self.data_bus:
			data |= bit if pin else 0
			bit >>= 1
		return data


with open("dump.dat", "wb") as dump:
	with allpro88.allpro88() as programmer:
		with m27c256(programmer) as device:
			device.chip_enable = True

			for device.address in tqdm(range(0x8000), desc = "Reading"):
				device.output_enable = True
				dump.write(bytearray((device.data,)))
				device.output_enable = False

			device.chip_enable = False
