import random
import usb.core

buf = usb.core.array.array("B", (0,) * 512)

device = usb.core.find(idVendor = 0x04b4, idProduct = 0x1004)

device.set_configuration()

def read_response():
	n = device.read(0x86, buf)
	msg = buf[:n].tobytes().decode("ascii")
	print(msg)
	return int(msg, 16)

while True:
	x = random.randint(0, 0xffff)
	# end-point 2 has address 0x02
	# end-point 6 has address 0x86
	device.write(0x02, ("E%04X\n" % x).encode("ascii"))
	y = read_response()
	assert y == x
