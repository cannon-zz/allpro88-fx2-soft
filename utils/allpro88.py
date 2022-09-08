import usb.core

class allpro88(object):
	idVendor = 0x04b4
	idProduct = 0x1004

	ep_addr_out = 0x02
	ep_addr_in = 0x86

	buf_size = 512	# bytes

	def __init__(self):
		self.buf = usb.core.array.array("B", (0,) * self.buf_size)
		self.device = usb.core.find(idVendor = self.idVendor, idProduct = self.idProduct)
		# firmware resets itself and the programmer
		self.device.set_configuration()

	def read_response(self):
		n = self.device.read(self.ep_addr_in, self.buf)
		if not n:
			return None
		msg = self.buf[:n].tobytes().decode("ascii").split()
		return (int(x, 16) for x in msg)

	def write_command(self, verb, addr = None, val = None):
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
			cmd = "=%04X%02X\n" % (addr, val)
		elif verb == "?":
			# read value from register
			assert val is None
			cmd = "?%04X\n" % addr
		elif verb == "E":
			# echo 4 digit number (USB loop-back test)
			assert val is None
			cmd = "E%04X\n" % addr
		else:
			raise ValueError("invalid command \"%s\"" % cmd)
		self.device.write(self.ep_addr_out, cmd.encode("ascii"))
		# every "out" packet generates a response "in" packet, even
		# if the commands did not produce responses (the packet is
		# empty).  we need to retrieve it unconditionally or the
		# "in" queue will fill up in the programmer
		return self.read_response()
