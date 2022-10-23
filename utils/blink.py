import allpro88
import time
from tqdm import tqdm

programmer = allpro88.allpro88()

print("system ID = 0x%X\nsocket module = %s" % (programmer.system_id, programmer.socket_module.name))

def blink_idle():
	for i in tqdm(range(10), desc = "blink IDLE LED"):
		programmer.write_command("=", 0x030c, 0x02)
		time.sleep(0.5)
		programmer.write_command("=", 0x030c, 0x00)
		time.sleep(0.5)

def blink_zif_pin1():
	programmer.vadj = 35	# 5 V
	programmer.vtst = 26	# 3 V
	programmer.itst = 5	# 5 mA
	# set all pins to ground
	for pin in range(88):
		programmer.channel[pin].config = allpro88.PINCON.GND
	# PCR enable
	programmer.pcr_enable = True
	# toggle pin 40 (zif socket pin 1) between VTST and ground
	channel = programmer.channel[40]
	for i in tqdm(range(10), desc = "blink ZIF pin 1"):
		channel.config = allpro88.PINCON.VTST
		time.sleep(0.5)
		channel.config = allpro88.PINCON.GND
		time.sleep(0.5)
	# set all pins to disable
	for pin in range(88):
		programmer.channel[pin].config = allpro88.PINCON.DISABLE
	# power supplies back to 0
	programmer.vtst = 0
	programmer.itst = 0
	programmer.vadj = 0
	# PCR disable
	programmer.pcr_enable = False

blink_idle()

blink_zif_pin1()
