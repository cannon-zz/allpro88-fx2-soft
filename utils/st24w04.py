from tqdm import tqdm
import allpro88
import devices

class st24w04(object):
	device_id = 0b1010

	def __init__(self, programmer):
		self.programmer = programmer
		self.socket = programmer.socket_module.sockets["DIP8"]
		# put all pins in a predictable state.
		for channel in self.socket.values():
			channel.config = allpro88.PINCON.DISABLE
			channel.vdac = 0
			channel.bypass = False
		# confiugre VPUL and VTH for I2C bus
		self.power = devices.power(self.programmer, self.socket, {
			"default": {
				4: 0.0,
				8: 5.0
			}
		}, vpul = 5.0, vth = 2.0)
		self.i2c = devices.bus_iic(self.socket, 5, 6)
		# documentation calls these two pins chip enable lines, but
		# the value coded onto them must match the two low bits of
		# the device select code.  they are more conveniently
		# treated, here, as a two-bit address bus
		self.address_bus = allpro88.bus_parallel_ttl(self.programmer, self.socket, (2, 3))

	def __enter__(self):
		# turn on device power
		self.power.on()
		return self

	def __exit__(self, exc_type, exc_val, exc_tb):
		# turn off power
		self.power.off()

		# done.  if an exception has occured, continue processing
		return False

	write_protect_enable = devices.flag_ttl(1)
	address = devices.bus_parallel("address_bus")
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
			if not ack:
				raise ValueError("device did not ack")
			for i in tqdm(range(256), desc = "Reading"):
				dump.write(bytearray((device.i2c.read_byte(ack = i < 255),)))
			device.i2c.stop()
