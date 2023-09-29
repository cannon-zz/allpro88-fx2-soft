import operator
import time
from . import allpro88


class power(object):
	def __init__(self, programmer, socket, voltage_maps, vadj = "auto", vpul = 0.0, vth = 1.5, default_voltage_map = "default"):
		if default_voltage_map not in voltage_maps:
			raise KeyError("voltage_maps must include '%s'" % default_voltage_map)
		self.programmer = programmer
		self.socket = socket
		self.voltage_maps = voltage_maps
		self.default_voltage_map = default_voltage_map
		self.active_voltage_map = None
		self.vpul = allpro88.volt(vpul) if vpul else 0
		self.vth = allpro88.volt(vth) if vth else 0
		if vadj == "auto":
			self.vadj = allpro88.volt(self.max() + 2.)
		else:
			self.vadj = allpro88.volt(vadj)

	def max(self):
		"""
		Return the highest voltage required for any of the voltage
		configurations, including the pull-up voltage, VPUL, and
		the threshold voltage, VTH.

		The return type is a float, not an allpro88.volt.
		"""
		max_pin_voltage = max(max(voltage_map.values()) for voltage_map in self.voltage_maps.values())
		return float(max(self.vpul, self.vth, max_pin_voltage))

	def reset_vth(self):
		"""
		Reset the programmer's VTH to the configured value.  When a
		pin voltage is measured, VTH is left set to the measured
		voltage.  Use this method to reset it so pin boolean states
		can be interpreted properly again.
		"""
		self.programmer.vth = self.vth

	def on(self, voltage_map = None):
		self.active_voltage_map = self.voltage_maps[voltage_map if voltage_map is not None else self.default_voltage_map]
		# configure pins.  dacs will be loaded below, with main
		# dacs
		for pin, voltage in self.active_voltage_map.items():
			self.socket[pin].bypass = True
			if voltage:
				self.socket[pin].config = allpro88.PINCON.VDAC
				self.socket[pin].vdac = allpro88.volt(voltage)
			else:
				self.socket[pin].config = allpro88.PINCON.GND
				self.socket[pin].vdac = 0
		# set main dacs
		self.programmer.vadj = self.vadj
		self.programmer.vpul = self.vpul
		self.reset_vth()
		self.programmer.load_dacs()
		# turn on power supplies
		self.programmer.pcr_enable = True
		# give VADJ its chance to ramp up.  the power supplies
		# weren't enabled, yet, when we programmed its control DAC,
		# so the power supply that DAC controls is only now
		# ramping.
		time.sleep(self.programmer.vadj.transient)

	def off(self):
		# cut power
		self.programmer.pcr_enable = False
		# set dacs to 0
		self.programmer.vadj = 0
		self.programmer.vpul = 0
		self.programmer.vth = 0
		# set vdac supplies to 0 and disable pins
		for pin in self.active_voltage_map:
			self.socket[pin].vdac = 0
			self.socket[pin].bypass = False
			self.socket[pin].config = allpro88.PINCON.DISABLE
		# load pin dacs and vpul dac
		self.programmer.load_dacs()
		# done
		self.active_voltage_map = None


class read_write_proxy(object):
	"""
	Descriptor to map the get and set operations of an attribute to the
	.read() and .write() methods, respectively, of some object.
	"""
	def __init__(self, attr_name):
		"""
		attr_name:  name of the attribute whose .read() and
		.write() methods will be called by this descriptor's
		.__get__() and .__set__() methods, respectively.
		"""
		self.getter = operator.attrgetter(attr_name)

	def __get__(self, obj, objtype = None):
		"""
		Call getattr(obj, attr_name).read() and return the result.
		"""
		return self.getter(obj).read()

	def __set__(self, obj, val):
		"""
		Call getattr(obj, attr_name).write(val).
		"""
		self.getter(obj).write(val)


class bus_proxy_parallel(read_write_proxy):
	"""
	Example:

	class some_device(object):
		def __init__(self, programmer, socket):
			# initialize a .address_bus instance attribute
			self.address_bus = allpro88.bus_parallel_ttl(programmer, socket, (1, 2, 3, 4))
		# define a proxy named .address to perform .read() and
		# .write() operations on .address_bus
		address = bus_proxy_parallel("address_bus")

	device = some_device(...)
	# iterate the address bus over all allowed values
	for device.address in device.address_bus:
		...
	"""
	pass


class bus_iic(object):
	"""
	IIC (aka I2C) bus.  NOTE:  must set VPUL = VCC for the chip and VTH
	to the minimum bus "high" state voltage.

	The methods must be called as followed:  first .start(), then any
	number of .write_byte(), .start(), and .read_byte() in any order,
	finally .stop().  The bit manipulations performed by each method
	follow correctly from the state the bus has been left in by the
	preceding method;  different orders will not work.
	"""
	lo = allpro88.PINCON.PULLUP | allpro88.PINCON.LOGICL
	hi = allpro88.PINCON.PULLUP
	flt = allpro88.PINCON.PULLUP

	def __init__(self, socket, sda, scl, strict_arbitration = False):
		"""
		socket:  the socket object containing the part
		sda:  the pin number for SDA
		scl:  the pin number for SCL

		if strict_arbitration is True then the bit banging
		algorithm will insert checks to ensure the target device
		has released the SDA and/or SCL lines at times when it
		would be allowed to hold them low to extend I/O cycles, for
		example if the part needs extra time to write data into
		flash memory.  since the bit banging algorithm is sooo
		slooow, it is almost certainly already going slowly enough
		to provide the time delays any part might require and
		adding the extra checking only slows it down even more.
		for this reason the default is to disable the checks (set
		strict_arbitration to False).  if you encounter a part that
		seems to not be working reliably, try setting
		strict_arbitration to True and see if that helps.
		"""
		# the socket object containing the part
		self.socket = socket
		# whether to do additional bus timing and arbitration error
		# checking.  slows the interface down significantly, but
		# some parts might require it.  haven't encountered one
		# yet, though
		self.strict_arbitration = strict_arbitration
		# SDA and SCL pins
		self.sda = socket[sda]
		self.scl = socket[scl]
		# start in idle state
		self.sda.config = self.hi
		self.scl.config = self.hi
		self.started = False

	#
	# helpers
	#

	def wait_sda(self, timeout = 0.5):
		# no-op if not in strict mode
		if not self.strict_arbitration:
			return
		# wait until sda is hi
		timeout += time.time()
		while not bool(self.sda):
			if time.time() > timeout:
				raise IOError("bus sda is being held low")

	def wait_scl(self, timeout = 0.5):
		# no-op if not in strict mode
		if not self.strict_arbitration:
			return
		# wait until scl is hi
		timeout += time.time()
		while not bool(self.scl):
			if time.time() > timeout:
				raise IOError("bus scl is being low")

	#
	# bit-banging bus interface
	#

	def start(self):
		if self.started:
			# restart sequence
			self.scl.config = self.lo
			self.sda.config = self.hi
			self.scl.config = self.hi
		# do start sequence.
		self.wait_scl()
		self.wait_sda()
		self.sda.config = self.lo
		self.started = True

	def stop(self):
		assert self.started
		# do stop sequence.  but have just read or written a byte
		# so first pull clock low, pull data low, raise clock, then
		# raise data.  bus is left in idle state
		self.scl.config = self.lo
		self.sda.config = self.lo
		self.scl.config = self.hi
		self.wait_scl()
		self.sda.config = self.hi
		self.wait_sda()
		self.started = False

	def write_bit(self, boolean):
		assert self.started
		# pull clock low, put bit onto data, raise clock
		self.scl.config = self.lo
		self.sda.config = self.hi if boolean else self.lo
		self.scl.config = self.hi
		# a 4 us pause is required here.  we assume the USB I/O
		# overhead is more than that, and the pause will take care
		# of itself
		self.wait_scl()
		# NOTE:  finally, clock must be pulled low again to
		# complete the bit.  the calling code will need to ensure
		# this.  following this with a call to any of .write_bit(),
		# .read_bit() or .stop() will do the correct thing.

	def read_bit(self):
		assert self.started
		# pull clock low to complete last operation, float data
		# line to allow target to drive it, raise clock, read data
		# state
		# NOTE:  finally, clock must be pulled low again to
		# complete the bit.  the calling code will need to ensure
		# this.  following this with a call to any of .write_bit(),
		# .read_bit() or .stop() will do the correct thing.
		self.scl.config = self.lo
		self.sda.config = self.hi
		self.scl.config = self.hi
		self.wait_scl()
		return bool(self.sda)

	def write_byte(self, byte):
		assert 0 <= byte <= 255
		for bit in (0x80, 0x40, 0x20, 0x10, 0x08, 0x04, 0x02, 0x01):
			self.write_bit(byte & bit)
		# read the ack state
		return not self.read_bit()

	def read_byte(self, ack = True):
		data = 0
		for bit in (0x80, 0x40, 0x20, 0x10, 0x08, 0x04, 0x02, 0x01):
			if self.read_bit():
				data |= bit
		# write the ack state
		self.write_bit(not ack)
		return data

	def scan(self):
		"""
		Scan the IIC bus and report the addresses that generate an
		ACK for a read operation.  Returns a list of the addresses.
		"""
		found = []
		for address in range(128):
			self.start()
			# combine address with R/!W, which we set to 1 so
			# we don't initiate a write operation
			if self.write_byte(address << 1 | 1):
				found.append(address)
			self.stop()
		return found

	#
	# emulate enough of the smbus2 API to allow luma.oled to control an
	# I2C OLED display through the programmer.
	# FIXME:  expand the emulated API for even more fun.
	#

	def write_i2c_block_data(self, i2c_addr, register, data, force = None):
		self.start()
		# combine address with R/!W bit = 0
		self.write_byte(i2c_addr << 1 | 0)
		self.write_byte(register)
		for val in data:
			self.write_byte(val)
		self.stop()


class bus_spi(object):
	"""
	SPI bus.  Calling code must set VTH for the device to VCC - 1 V.
	"""
	hi = allpro88.PINCON.VDAC
	lo = allpro88.PINCON.LOGICL

	def __init__(self, socket, sclk, mosi, miso, vdac):
		self.sclk = socket[sclk]	# clock
		self.mosi = socket[mosi]	# master --> slave
		self.miso = socket[miso]	# master <-- slave

		if vdac <= 0:
			raise ValueError(vdac)
		vdac = allpro88.volt(vdac)
		self.sclk.vdac = vdac
		self.mosi.vdac = vdac

		self.sclk.config = self.lo
		self.mosi.config = self.lo

	def transfer_byte(self, out_byte):
		in_byte = 0
		for bit in (0x80, 0x40, 0x20, 0x10, 0x08, 0x04, 0x02, 0x01):
			self.mosi.config = self.hi if (out_byte & bit) else self.lo
			self.sclk.config = self.hi
			self.sclk.config = self.lo
			if self.miso:
				in_byte |= bit
		return in_byte


#
# Boolean state pins
#


class flag_proxy(read_write_proxy):
	pass
