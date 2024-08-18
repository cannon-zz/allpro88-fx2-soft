from tqdm import tqdm
from . import allpro88
from . import devices

class w25x10avaiz(object):
	def __init__(self, programmer):
		self.programmer = programmer
		self.socket = programmer.socket_module.sockets["DIP8"]
		self.power = devices.power(self.programmer, self.socket, {
			"default": {
				4: 0.0,
				8: 3.3
			}
		}, vth = 1.75)
		self.spi = devices.bus_spi(self.socket, 6, 5, 2, vdac = 3.3)
		# flags
		self.chip_select_flag = allpro88.flag_vdac_active_low(self.socket, 1, vdac = 3.3)
		self.write_protect_flag = allpro88.flag_vdac_active_low(self.socket, 3, vdac = 3.3)
		self.hold_flag = allpro88.flag_vdac_active_low(self.socket, 7, vdac = 3.3)

	def __enter__(self):
		self.power.on()
		return self

	def __exit__(self, exc_type, exc_val, exc_tb):
		self.power.off()
		# done.  if an exception has occured, continue processing
		return False

	# proxy descriptors
	chip_select = devices.flag_proxy("chip_select_flag")
	write_protect = devices.flag_proxy("write_protect_flag")
	hold = devices.flag_proxy("hold_flag")


with open("dump.dat", "wb") as dump:
	with allpro88.allpro88(cal_data = "calibration.dat") as programmer:
		with w25x10avaiz(programmer) as device:
			# device ignores chip select until it has seen it
			# deasserted, so we must start with it in that
			# state.  setting it to False is the default for
			# the flag interface, but we do it here explicitly
			# for clarity
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
