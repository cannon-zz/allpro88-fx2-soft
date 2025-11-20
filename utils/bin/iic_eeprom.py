# Copyright (C) 2023-2024  Kipp Cannon
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


import math
from tqdm import tqdm
from . import allpro88
from . import devices

class iic_eeprom(object):
	socket = "DIP8"
	voltage_maps = {
		"default": {
			4: 0.0,	# GND
			8: 5.0,	# Vcc
			"VPUL": 5.0
		}
	}
	device_id = 0b1010
	# subclass sets to integers
	blocks = None
	block_length = 256
	# most chips use these pins or some subset as a chip select
	# mechanism.  subclasses can customize as needed.  these pins will
	# be set low by default.
	address_pins = (1, 2, 3)

	def __init__(self, programmer):
		self.programmer = programmer
		self.socket = programmer.socket_module.sockets[self.socket]
		# confiugre VPUL and VTH for I2C bus
		self.power = devices.power(self.programmer, self.socket, self.voltage_maps, vth = 2.0)
		# IIC bus
		self.i2c = devices.bus_iic(self.socket, 5, 6)
		# address select pins
		self.address_bus = allpro88.bus_parallel_ttl(self.programmer, self.socket, self.address_pins)
		# flags
		self.write_control_flag = allpro88.flag_ttl_active_low(self.socket, 7)

	def __enter__(self):
		self.power.on()
		return self

	def __exit__(self, exc_type, exc_val, exc_tb):
		self.power.off()
		# done.  if an exception has occured, continue processing
		return False

	# proxy descriptors
	address = devices.read_write_proxy("address_bus")
	write_control = devices.read_write_proxy("write_control_flag")

	def select_code(self, block, r_not_w):
		raise NotImplementedError("subclass must provide this method")


class st24w04(iic_eeprom):
	blocks = 2
	address_pins = (2, 3)

	def __init__(self, *args, **kwargs):
		super(st24w04, self).__init__(*args, **kwargs)
		self.write_protect_enable_flag = allpro88.flag_ttl(self.socket, 1)

	write_protect_enable = devices.read_write_proxy("write_protect_enable_flag")

	def select_code(self, block, r_not_w):
		assert 0 <= block < self.blocks
		assert r_not_w in (0, 1)
		# construct the device select code
		return self.device_id << 4 | self.address << 2 | block << 1 | r_not_w


class stm24c32(iic_eeprom):
	blocks = 1
	block_length = 4096

	def select_code(self, block, r_not_w):
		assert 0 <= block < self.blocks
		assert r_not_w in (0, 1)
		# construct the device select code
		return self.device_id << 4 | self.address << 1 | r_not_w


class atmel_24c02n(iic_eeprom):
	blocks = 1

	def select_code(self, block, r_not_w):
		assert 0 <= block < self.blocks
		assert r_not_w in (0, 1)
		# construct the device select code
		return self.device_id << 4 | self.address << 1 | r_not_w


class microchip_24lc16b(iic_eeprom):
	blocks = 8
	# the address pins are not connected

	def select_code(self, block, r_not_w):
		assert 0 <= block < self.blocks
		assert r_not_w in (0, 1)
		# construct the device select code
		return self.device_id << 4 | block << 1 | r_not_w


with open("dump.dat", "wb") as dump:
	with allpro88.allpro88() as programmer:
		with atmel_24c02n(programmer) as device:
			device.address = 0
			for block in range(device.blocks):
				# send start bit
				device.i2c.start()
				# set the internal address pointer by
				# sending a write command with the desired
				# start address (0).  we assume the start
				# address requires as many bytes as are
				# needed to encode the length of a block.
				# e.g., a block length of 256 bytes
				# requires a 1 byte adddress, a block
				# length of 4096 requires a two byte start
				# address.
				if not device.i2c.write_byte(device.select_code(block, 0)):
					raise ValueError("device did not ack")
				for i in range(math.ceil(math.log2(device.block_length) / 8)):
					if not device.i2c.write_byte(0x00):
						raise ValueError("device did not ack")
				# cancel the write operation by sending a
				# new start bit and a read command
				device.i2c.start()
				if not device.i2c.write_byte(device.select_code(block, 1)):
					raise ValueError("device did not ack")
				# read bytes one-by-one, only ack final
				# byte
				for i in tqdm(range(device.block_length), desc = "Block %d" % block):
					dump.write(bytearray((device.i2c.read_byte(ack = i < device.block_length - 1),)))
				# send stop bit
				device.i2c.stop()
