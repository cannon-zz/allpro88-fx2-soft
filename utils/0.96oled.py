# Copyright (C) 2022--2024  Kipp Cannon
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation; either version 3 of the License, or (at your
# option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General
# Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.


import time
from . import allpro88
from . import devices

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
		# configure power, VPUL, VTH, and I2C bus
		self.power = devices.power(self.programmer, self.socket, {
			"default": {
				1: 0.0,
				2: 5.0,
				"VPUL": 5.0
			}
		}, vth = 2.0)
		self.i2c = devices.bus_iic(self.socket, 4, 3)

	def __enter__(self):
		# turn on device power
		self.power.on()
		return self

	def __exit__(self, exc_type, exc_val, exc_tb):
		# turn off power
		self.power.off()

		# done.  if an exception has occured, continue processing
		return False

	def select_code(self, r_not_w):
		assert r_not_w in (0, 1)
		# construct the device select code
		return self.device_id << 2 | self.address << 1 | r_not_w


with allpro88.allpro88() as programmer:
	with oled_module(programmer) as device:
		display = ssd1306(i2c(bus = device.i2c, port = None, address = device.device_id << 1 | device.address))
		display.contrast(1)
		with canvas(display, dither = True) as draw:
			draw.line(((0, display.height // 2), (display.width, display.height // 2)), "gray")
			draw.line(((display.width // 2, 0), (display.width // 2, display.height)), "gray")
			draw.text((display.width // 2, display.height // 2), "HELLO WORLD", fill = "white", anchor = "mm")
		time.sleep(20)
