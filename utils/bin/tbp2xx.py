# Copyright (C) 2024-2025  Kipp Cannon
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


from tqdm import tqdm
import allpro88
import devices


class tbp2xx(object):
	"""
	TBP24x parts:  4 bit PROMs.
	TBP28x parts:  8 bit PROMs.
	"""
	# subclasses override these
	socket_name = ""
	voltage_maps = {}
	address_bus_pins = ()
	data_bus_pins = ()
	# the parts have between 1 and 4 enable pins, some active low some
	# active high.  to make it easier to write generic handling
	# routines, we treat the enable pins as another bus and require
	# subclasses to say what pins go in the bus and what to set that
	# "bus" to to enable the chip (disable is assumed to be any other
	# value, nominally the bitwise inverse)
	chip_enable_pins = ()
	enabled = 0	# state to set chip enable pins to to enable chip
	Tpw = 20	# program pulse width in microseconds
	Vadj = "auto"

	def __init__(self, programmer, mode):
		self.programmer = programmer
		self.socket = programmer.socket_module.sockets[self.socket_name]
		if mode not in self.voltage_maps:
			raise ValueError("unknown mode \"%s\"" % mode)
		self.mode = mode
		# power pins
		self.power = devices.power(self.programmer, self.socket, self.voltage_maps, vadj = self.Vadj)
		# address and data buses
		self.address_bus = allpro88.bus_parallel_ttl(self.programmer, self.socket, self.address_bus_pins)
		self.data_bus = allpro88.bus_parallel_ttl(self.programmer, self.socket, self.data_bus_pins)
		# chip enable "bus"
		self.chip_enable_bus = allpro88.bus_parallel_ttl(self.programmer, self.socket, self.chip_enable_pins, default = ~self.enabled, ignore_overflow = True)

	def __enter__(self):
		self.power.on(self.mode)
		return self

	def __exit__(self, exc_type, exc_val, exc_tb):
		self.power.off()
		# done.  if an exception has occured, continue processing
		return False

	# proxy descriptors
	address = devices.read_write_proxy("address_bus")
	data = devices.read_write_proxy("data_bus")
	chip_enable = devices.read_write_proxy("chip_enable_bus")

	# read/write

	@classmethod
	def read_device(cls, imgfile):
		with allpro88.allpro88() as programmer:
			with cls(programmer, "read") as device:
				device.chip_enable = device.enabled
				for device.address in tqdm(device.address_bus, desc = "Reading"):
					imgfile.write(bytearray((device.data,)))
				device.chip_enable = ~device.enabled

	@classmethod
	def write_device(cls, imgfile):
		"""
		imfile = file object from which to read bytes
		"""
		raise NotImplementedError


class tbp28l22(tbp2xx):
	socket_name = "DIP20"		# "J" and "N" variants
	voltage_maps = {
		"read": {
			20:  +5.0,	# Vcc
			10:  0.0	# GND
		}
	}
	address_bus_pins = (1, 2, 3, 4, 5, 17, 18, 19)
	data_bus_pins = (6, 7, 8, 9, 11, 12, 13, 14)
	chip_enable_pins = (15, 16)
	enabled = 0x0


###
#
# Entry Point
#
###


tbp28l22.read_device(open("dump.dat", "wb"))
