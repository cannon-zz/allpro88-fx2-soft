import random
from tqdm import tqdm
import usb.core

buf = usb.core.array.array("B", (0,) * 512)

device = usb.core.find(idVendor = 0x04b4, idProduct = 0x1004)

device.set_configuration()

def read_response():
	# in end-point 6 has address 0x86
	n = device.read(0x86, buf)
	msg = buf[:n].tobytes().decode("ascii")
	return int(msg, 16)

for i in tqdm(range(100000), desc = "running loopback test"):
	x = random.randint(0, 0xffff)
	# out end-point 2 has address 0x02
	device.write(0x02, ("E%04X\n" % x).encode("ascii"))
	y = read_response()
	assert y == x
