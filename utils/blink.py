import allpro88
import time
from tqdm import tqdm

programmer = allpro88.allpro88()

print("system ID = 0x%X\nsocket adapter ID = 0x%X" % (programmer.system_id, programmer.socket_id))

def blink_busy():
	for i in tqdm(range(10), desc = "blink BUSY LED"):
		programmer.write_command("=", 0x030c, 0x03)
		time.sleep(0.5)
		programmer.write_command("=", 0x030c, 0x00)
		time.sleep(0.5)

def blink_zif_pin1():
	# VADJ = 35 (5 V)
	#programmer.write_command("=", 0x0302, 35)
	programmer.write_command("=", 0x0302, 255)
	# VTST = 26 (3 V), ITST = 5 (5 mA)
	programmer.write_command("=", 0x0386, 26)
	programmer.write_command("=", 0x0387, 5)
	# VPUL = max
	programmer.write_command("=", 0x0305, 255)
	programmer.write_command("=", 0x0308, 0)
	# PCR enable
	programmer.write_command("=", 0x030c, 0x03)
	# set all pins to ground
	def pin_addr(pin):
		if pin > 0x27:
			pin += 0x18
		return pin << 4
	for pin in range(88):
		programmer.write_command("=", pin_addr(pin), 0x01)
	# set pin 40 DAC to 35 (3 V)
	pin = 40
	programmer.write_command("=", pin_addr(pin) + 3, 255)
	programmer.write_command("=", 0x0308, 0)
	# toggle pin 40 (zif socket pin 1) between VTST and ground
	for i in tqdm(range(10), desc = "blink BUSY LED"):
		#programmer.write_command("=", pin_addr(pin), 0x04)
		programmer.write_command("=", pin_addr(pin), 0x10)
		time.sleep(0.5)
		programmer.write_command("=", pin_addr(pin), 0x01)
		time.sleep(0.5)
	# set all pins to disable
	for pin in range(88):
		programmer.write_command("=", pin_addr(pin), 0)
	# set pin 40 DAC and VPUL to 0
	programmer.write_command("=", pin_addr(pin) + 3, 0)
	programmer.write_command("=", 0x0305, 0)
	programmer.write_command("=", 0x0308, 0)
	# VTST = 0, ITST = 0
	programmer.write_command("=", 0x0386, 0)
	programmer.write_command("=", 0x0387, 0)
	# VADJ = 0
	programmer.write_command("=", 0x0302, 0)
	# PCR disable
	programmer.write_command("=", 0x030c, 0)

#blink_busy()

blink_zif_pin1()
