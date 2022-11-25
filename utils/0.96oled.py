import time
from tqdm import tqdm
import allpro88
import devices

from luma.core.interface.serial import i2c
from luma.oled.device import ssd1306
from luma.core.render import canvas


class oled_module(object):
	# top 6 bits of I2C address (fixed value for SSD1306 devices)
	device_id = 0b011110
	# lowest bit of I2C address (configured on carrier PCB)
	address = 0

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
			1: 0.0,
			2: 5.0
		})
		self.i2c = devices.bus_iic(self.socket, 4, 3)

	def __enter__(self):
		# turn on power supplies, set VADJ to 10 V, VPUL to 5
		# (logic high on I2C bus) and VTH to 2 V
		self.programmer.pcr_enable = True
		self.programmer.vadj = allpro88.volt(10.)
		self.programmer.vpul = allpro88.volt(5.)
		self.programmer.vth = allpro88.volt(2.)
		# turn on device power
		self.power.on()	# calls .load_dacs() for vpul
		return self

	def __exit__(self, exc_type, exc_val, exc_tb):
		# make sure all non-power pins are disabled so they don't
		# have voltages on them when power is removed from the chip
		for pin_number, channel in self.socket.items():
			if pin_number not in self.power.pins:
				channel.config = allpro88.PINCON.DISABLE
				channel.vdac = 0
				channel.bypass = False
		# turn off pull-up voltage and device power
		self.programmer.vpul = 0
		self.power.off()	# calls .load_dacs() for vpul
		# turn off programmer power supplies
		self.programmer.vth = 0
		self.programmer.vadj = 0
		self.programmer.pcr_enable = False

		# done.  if an exception has occured, continue processing
		return False

	def select_code(self, r_not_w):
		# ensure these are 0 or 1
		r_now_w = 1 if r_not_w else 0
		# construct the device select code
		return self.device_id << 2 | self.address << 1 | r_not_w


with allpro88.allpro88(calibration_file = open("calibration.dat")) as programmer:
	with oled_module(programmer) as device:
		display = ssd1306(i2c(bus = device.i2c, port = None, address = device.device_id << 1 | device.address))
		display.contrast(1)
		with canvas(display, dither = True) as draw:
			draw.line(((0, display.height // 2), (display.width, display.height // 2)), "gray")
			draw.line(((display.width // 2, 0), (display.width // 2, display.height)), "gray")
			draw.text((display.width // 2, display.height // 2), "HELLOW WORLD", fill = "white", anchor = "mm")
		time.sleep(20)
