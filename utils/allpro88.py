import usb.core


class command(object):
	"""
	Device for constructing a command string from a verb and optional
	address and value.  This also provides a place for the command
	queue machinery to place a response from the programmer, allowing
	each response to be associated with the command that produced it.
	"""
	def __init__(self, verb, addr = None, val = None, label = None):
		self.verb = verb
		self.addr = addr
		self.val = val
		self.label = label
		if verb == "=":
			# write arbitrary value to arbitrary register
			# NOTE NOTE NOTE:  physical damage will occur if
			# the wrong value is written to the wrong address.
			# by writing an unfortunate value to a pin
			# configuration register, a pin might be connected
			# to both a supply voltage and ground
			# simultaneously, destroying the pin driver
			# electronics.  for testing purposes, writing 0 to
			# any address is safe.  this always corresponds to
			# the "disabled" or "turned off" setting for any
			# register.  other values should only be written
			# after carefully consulting the documentation.
			self.cmd = "=%04X%02X\n" % (addr, val)
			self.need_response = False
		elif verb == "?":
			# read value from register
			assert val is None
			self.cmd = "?%04X\n" % addr
			self.need_response = True
		elif verb == "E":
			# echo 4 digit number (USB loop-back test)
			assert val is None
			self.cmd = "E%04X\n" % addr
			self.need_response = True
		elif verb == "R":
			# reset
			assert addr is None and val is None
			self.cmd = "R\n"
			self.need_response = False
		else:
			raise ValueError("invalid command \"%s\"" % cmd)
		self.response = None

	def __str__(self):
		return self.cmd


class allpro88(object):
	idVendor = 0x04b4
	idProduct = 0x1004

	ep_addr_out = 0x02
	ep_addr_in = 0x86

	buf_size = 512	# bytes

	command_queue_size = 64	# commands

	def __init__(self):
		self.buf = usb.core.array.array("B", (0,) * self.buf_size)
		self.device = usb.core.find(idVendor = self.idVendor, idProduct = self.idProduct)
		if self.device is None:
			raise ValueError("USB device not found (vid:pid = %04X:%04X)" % (self.idVendor, self.idProduct))

		# firmware resets itself and the programmer
		self.device.set_configuration()

		# command queues
		self.out_queue = []
		self.in_queue = []

	def read_responses(self):
		n = self.device.read(self.ep_addr_in, self.buf)
		# every response ends in a new line character.  some
		# responses are empty, and more than one such response in a
		# row become sequential new line characters.  .split()
		# normally treats them all as a single whitespace boundary,
		# but if given a specific character to split on then each
		# new line is its own boundary.  .split() also normally
		# doesn't create an extra split if the string ends in
		# whitespace, but when given a specific character to split
		# on and the string ends in that character then an
		# additional (zero length) split value is created.  since
		# every command ends in a new line, we always get one extra
		# value, which we must drop from the list
		msg = self.buf[:n].tobytes().decode("ascii").split("\n")[:-1]
		return tuple(int(x, 16) if x else None for x in msg)


	#
	# one command at a time interface
	#


	def write_command(self, verb, addr = None, val = None):
		self.device.write(self.ep_addr_out, str(command(verb, addr, val)).encode("ascii"))
		# every "out" packet generates a response "in" packet, even
		# if the commands did not produce responses (the packet is
		# empty).  we need to retrieve it unconditionally or the
		# "in" queue will fill up in the programmer
		return self.read_responses()


	#
	# command queue based interface
	#


	def push(self, command):
		# don't let the queue get too big or it won't encode into a
		# single packet
		assert len(self.out_queue) < self.command_queue_size
		self.out_queue.append(command)

	def commit(self):
		self.device.write(self.ep_addr_out, "".join(map(str, self.out_queue)).encode("ascii"))
		self.out_queue[:] = (command for command in self.out_queue if command.need_response)
		responses = self.read_responses()
		assert len(responses) == len(self.out_queue)
		for command, response in zip(self.out_queue, responses):
			command.response = response
		self.in_queue.extend(self.out_queue)
		del self.out_queue[:]

	def pop(self):
		return self.in_queue.pop(0)

	def pop_all(self):
		while self.in_queue:
			yield self.pop()

	#
	# higher level interface
	#

	@property
	def socket_id(self):
		socket_id, = self.write_command("?", 0x0280)
		return socket_id

	@property
	def system_id(self):
		# in the allpro88 documentation some command line
		# diagnostic tools are shown producing example output
		# reporting a "system ID" of 0x3 and "adapter ID" of 0x11.
		# other examples show an "analog ID" of 0x03.  the "adapter
		# ID" is the socket board ID, and mine is 0x11, like the
		# examples (kevtris' is 0x81).  but where do the "system
		# ID" and "analog ID" come from?  are they synonyms for the
		# same number?  kevtris' documentation describes an A1STAT
		# register, whose low nibble he says is hard-wired to
		# report 0x03, curiously the same as the ID in the examples
		# in the documentation.  my unit also reports 0x03 in that
		# nibble.  is this the "system ID" and/or "analog ID"?  are
		# they synonyms?  I'm guessing they are, and it is, and
		# that's what this returns.  but, I'm just making this up.
		system_id, = self.write_command("?", 0x0300)
		return system_id & 0xf
