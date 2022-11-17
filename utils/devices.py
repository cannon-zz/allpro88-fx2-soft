import allpro88


class power(object):
	def __init__(self, programmer, socket, pin_voltage_map):
		self.programmer = programmer
		self.socket = socket
		self.pin_voltage_map = pin_voltage_map

	def on(self):
		# configure pins
		for pin, voltage in self.pin_voltage_map.items():
			self.socket[pin].bypass = True
			self.socket[pin].config = allpro88.PINCON.VDAC if voltage else allpro88.PINCON.GND
		# apply power
		for pin, voltage in self.pin_voltage_map.items():
			self.socket[pin].vdac = self.socket[pin].invcal(voltage) if voltage else 0
		self.programmer.load_dacs()

	def off(self):
		# set vdac supplies to 0
		for pin in self.pin_voltage_map:
			self.socket[pin].vdac = 0
		self.programmer.load_dacs()
		# disable power
		for pin in self.pin_voltage_map:
			self.socket[pin].bypass = False
			self.socket[pin].config = allpro88.PINCON.DISABLE

	@property
	def pins(self):
		return tuple(self.pin_voltage_map)


class bus(object):
	"""
	A collection of pins whose digital states represent an integer
	number.  The pins can be used for output or input.  To use the bus
	for output, write a value to it.  To use the bus for input, read a
	value from it.  To switch a bus that is being used for output to
	input, write None to the bus to float the pins.
	"""
	# subclasses must override these
	inactive = None
	active = None

	def __init__(self, pin_numbers, min_word = None, max_word = None):
		"""
		pin_numbers:  sequence of socket pin numbers for this bus
		in order from least-significant bit to most-significant
		bit.

		min_word, max_word:  the numeric value written to the bus
		will be restricted to the range min_word <= word <=
		max_word.  If None (default), min_word is set to 0 and
		max_word is defined by the number of pins.
		"""
		self.min_word = 0 if min_word is None else min_word
		self.max_word = 2**len(pin_numbers) - 1 if max_word is None else max_word
		self.pin_numbers = tuple((1 << i, pin_number) for i, pin_number in enumerate(pin_numbers))
		# to improve performance, when setting pin states only pins
		# whose state has changed are updated.  .last_state = None
		# forces all pins to be updated, otherwise .last_state
		# contains the most recently written word, and an exclusive
		# or operation is used to identify the bits that need
		# updating.
		self.last_state = None

	def __get__(self, obj, objtype = None):
		"""
		Return the integer value corresponding to the bus' pin
		voltage comparators.  The "high"/"low" states are defined
		by the VTH voltage, not the .inactive and .active states.
		"""
		data = 0
		for bit, pin_number in self.pin_numbers:
			if obj.socket[pin_number]:
				data |= bit
		return data

	def __set__(self, obj, word):
		"""
		Set the pins of the bus to either .inactive or .active
		according to the bits of the integer word.  If word is None
		the pins are floated.  Only pins whose state is different
		from the previous value written will be updated, so if code
		elsewhere is playing with the pin states that should be
		taken into consideration.
		"""
		# disable (float) pins if word is None
		if word is None:
			for bit, pin_number in self.pin_numbers:
				obj.socket[pin_number].config = allpro88.PINCON.DISABLED
				self.last_state = None
		else:
			# check type compatibility and range
			word = int(word)
			if not (self.min_word <= word <= self.max_word):
				raise ValueError("0x%X <= word <= 0x%X: 0x%X" % (self.min_word, self.max_word, word))
			mask = -1 if self.last_state is None else (self.last_state ^ word)
			# set the pin states
			for bit, pin_number in self.pin_numbers:
				if mask & bit:
					obj.socket[pin_number].config = self.active if (word & bit) else self.inactive
			self.last_state = word


class bus_ttl(bus):
	inactive = allpro88.PINCON.LOGICL
	active = allpro88.PINCON.LOGICH


class bus_iic(object):
	"""
	IIC (aka I2C) bus.  NOTE:  must set VPUL = VCC for the chip and VTH
	to the minimum bus "high" state voltage.

	example sequences:

	start()
	write_byte()	# return value = ack
	write_byte()
	...
	read_byte(ack)	# return value = byte
	...
	stop()
	"""
	lo = allpro88.PINCON.LOGICL | allpro88.PINCON.PULLUP
	hi = allpro88.PINCON.PULLUP
	flt = allpro88.PINCON.PULLUP

	def __init__(self, socket, sda, scl):
		# the socket object containing the part
		self.socket = socket
		# SDA and SCL pins
		self.sda = socket[sda]
		self.scl = socket[scl]
		# start in idle state
		self.idle()

	def idle(self):
		# idle state
		self.sda.config = self.hi
		self.scl.config = self.hi

	def start(self):
		# do start sequence.  must be in idle state
		self.sda.config = self.lo

	def stop(self):
		# do stop sequence.  but have just read or written a byte
		# pull clock low, pull data low, raise clock, then raise
		# data.  bus is left in idle state
		self.scl.config = self.lo
		self.sda.config = self.lo
		self.scl.config = self.hi
		self.sda.config = self.hi

	def write_bit(self, boolean):
		# pull clock low, put bit onto data, raise clock
		self.scl.config = self.lo
		self.sda.config = self.hi if boolean else self.lo
		self.scl.config = self.hi
		# a 4 us pause is required here.  we assume the USB I/O
		# overhead is more than that, and the pause will take care
		# of itself
		# NOTE:  finally, clock must be pulled low again to
		# complete the bit.  the calling code will need to ensure
		# this.  calling this function repeatedly in sequence will
		# do the correct thing.

	def read_bit(self):
		# pull clock low, raise clock, read data state
		# NOTE:  finally, clock must be pulled low again to
		# complete the bit.  the calling code will need to ensure
		# this.  calling this function repeatedly in sequence will
		# do the correct thing.
		self.scl.config = self.lo
		self.scl.config = self.hi
		return bool(self.sda)

	def write_byte(self, byte):
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


#
# Boolean state pins
#


class flag(object):
	# subclasses override these with the appropriate states
	inactive = None
	active = None

	def __init__(self, pin_number):
		self.pin_number = pin_number

	def __get__(self, obj, objtype = None):
		"""
		Returns the state of the pin's comparator.  The
		comparator's threshold is set by VTH, not the values of
		.inactive and .active.
		"""
		return bool(obj.socket[self.pin_number])

	def __set__(self, obj, boolean):
		"""
		Sets the pin's state to .active (.inactive) if boolean is
		True (False).  If boolean is None the state is set to
		DISABLED (floating).
		"""
		obj.socket[self.pin_number].config = allpro88.PINCON.DISABLED if boolean is None else self.active if boolean else self.inactive


class flag_ttl(flag):
	inactive = allpro88.PINCON.LOGICL
	active = allpro88.PINCON.LOGICH


class flag_ttl_active_low(flag):
	inactive = allpro88.PINCON.LOGICH
	active = allpro88.PINCON.LOGICL
