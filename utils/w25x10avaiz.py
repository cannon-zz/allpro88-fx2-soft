from tqdm import tqdm
import allpro88
import devices

class w25x10avaiz(object):
	def __init__(self, programmer):
		self.programmer = programmer
		self.socket = programmer.socket_module.sockets["DIP8"]
		# make sure all associated pins are disabled so they are in
		# a predictable state.
		for channel in self.socket.values():
			channel.config = allpro88.PINCON.DISABLE
			channel.vdac = 0
			channel.bypass = False
		self.power = devices.power(self.programmer, self.socket, {
			4: 0.0,
			8: 3.3
		})
		self.spi = devices.bus_spi(self.socket, 6, 5, 2)

	def __enter__(self):
		# set VTH to 1.75 V
		self.programmer.vth = allpro88.volt(1.75)
		# turn on device power
		self.power.on()
		# set vdac on sclk and mosi pins to 3.3 V
		self.spi.sclk.vdac = allpro88.volt(3.3)
		self.spi.mosi.vdac = allpro88.volt(3.3)
		# !cs, !wp, !hold.  FIXME:  we need a systematic way of
		# doing this
		for pin in (1, 3, 7):
			self.socket[pin].vdac = allpro88.volt(3.3)
		self.programmer.load_dacs()

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

	chip_select = devices.flag_vdac_active_low(1)
	write_protect = devices.flag_vdac_active_low(3)
	hold = devices.flag_vdac_active_low(7)


with open("dump.dat", "wb") as dump:
	with allpro88.allpro88(calibration_file = open("calibration.dat")) as programmer:
		with w25x10avaiz(programmer) as device:
			# device ignores chip select until it has seen it
			# deasserted, so we must start with it in that
			# state
			device.chip_select = False
			device.write_protect = True
			device.hold = False

			# now assert chip select to access the chip
			device.chip_select = True
			# send read data command
			device.spi.transfer_byte(0x03)
			# send 3 byte start address
			device.spi.transfer_byte(0x00)
			device.spi.transfer_byte(0x00)
			device.spi.transfer_byte(0x00)
			# read data
			for i in tqdm(range(2**17), desc = "Reading"):
				dump.write(bytearray((device.spi.transfer_byte(0x00),)))
			device.chip_select = False
