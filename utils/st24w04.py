from tqdm import tqdm
import allpro88
import devices

class st24w04(object):
	device_id = 0b1010

	def __init__(self, programmer):
		self.programmer = programmer
		self.socket = programmer.socket_module.sockets["DIP8"]
		# make sure all associated pins are disabled so they are in
		# a predictable state.
		for channel in self.socket.values():
			channel.config = allpro88.PINCON.DISABLE
			channel.vdac = 0

		self.i2c = devices.bus_iic(self.socket, 5, 6)

	def __enter__(self):
		# turn on power supplies, set VADJ to 15 V and VTH to 2 V
		self.programmer.pcr_enable = True
		self.programmer.vadj = self.programmer.vadj.invcal(15.)
		self.programmer.vpul = self.programmer.vadj.invcal(5.)
		self.programmer.vth = self.programmer.vth.invcal(2.)

		# configure power pins.  VPP = VCC for read
		self.socket[4].bypass = True
		self.socket[4].config = allpro88.PINCON.GND
		self.socket[8].bypass = True
		self.socket[8].config = allpro88.PINCON.VDAC
		# apply 5 V
		self.socket[8].vdac = self.socket[8].invcal(5.)
		self.programmer.load_dacs()

		return self

	def __exit__(self, exc_type, exc_val, exc_tb):
		# make sure all non-power pins are disabled so they don't
		# have voltages on them when power is removed from the chip
		for pin_number, channel in self.socket.items():
			if pin_number not in (4, 8):
				channel.config = allpro88.PINCON.DISABLE
		# set VDAC supplies to 0
		self.socket[8].vdac = 0
		self.programmer.load_dacs()
		# now disable power
		self.socket[4].bypass = False
		self.socket[4].config = allpro88.PINCON.DISABLE
		self.socket[8].bypass = False
		self.socket[8].config = allpro88.PINCON.DISABLE

		# turn off programmer power supplies
		self.programmer.vth = 0
		self.programmer.vpul = 0
		self.programmer.load_dacs()
		self.programmer.vadj = 0
		self.programmer.pcr_enable = False

		# done.  if an exception has occured, continue processing
		return False

	write_protect_enable = devices.flag_ttl(1)
	# documentation calls these two pins chip enable lines, but the
	# value coded onto them must match the two low bits of the device
	# select code.  they are more conveniently treated, here, as a
	# two-bit address bus
	address = devices.bus_ttl((2, 3))
	write_control = devices.flag_ttl_active_low(7)

	def select_code(self, block_select, r_not_w):
		# ensure these are 0 or 1
		block_select = 1 if block_select else 0
		r_now_w = 1 if r_not_w else 0
		# construct the device select code
		return self.device_id << 4 | self.address << 2 | block_select << 1 | r_not_w


with open("dump.dat", "wb") as dump:
	with allpro88.allpro88() as programmer:
		with st24w04(programmer) as device:
			device.address = 0
			device.write_control = False

			device.i2c.start()
			ack = device.i2c.write_byte(device.select_code(0, 1))
			print("device select ack: %d" % ack)
			for i in tqdm(range(256), desc = "Reading"):
				dump.write(bytearray((device.i2c.read_byte(ack = i < 255),)))
			device.i2c.stop()
