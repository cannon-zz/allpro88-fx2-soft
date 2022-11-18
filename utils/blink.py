import allpro88
import time
from tqdm import tqdm

def blink_idle(programmer, n = 10):
	for i in tqdm(range(n), desc = "blink IDLE LED"):
		programmer.write_command("=", 0x030c, 0x02)
		time.sleep(0.5)
		programmer.write_command("=", 0x030c, 0x00)
		time.sleep(0.5)

def blink_zif_pin1(programmer, n = 10):
	programmer.vadj = allpro88.volt(5.)
	programmer.vtst = allpro88.volt(3.)
	programmer.itst = 15	# 15 mA
	# set all pins to ground
	for channel in programmer.channel.values():
		channel.config = allpro88.PINCON.GND
	# PCR enable
	programmer.pcr_enable = True
	# ZIF socket pin 1 between VTST and ground
	channel = programmer.socket_module.sockets["DIP48"][1]
	for i in tqdm(range(n), desc = "blink DIP pin 1"):
		channel.config = allpro88.PINCON.VTST
		time.sleep(0.5)
		channel.config = allpro88.PINCON.GND
		time.sleep(0.5)
	# set all pins to disable
	for channel in programmer.channel.values():
		channel.config = allpro88.PINCON.DISABLE
	# power supplies back to 0
	programmer.vtst = 0
	programmer.itst = 0
	programmer.vadj = 0
	# PCR disable
	programmer.pcr_enable = False


with allpro88.allpro88() as programmer:
	print("system ID = 0x%X\nsocket module = %s" % (programmer.system_id, programmer.socket_module.name))

	blink_idle(programmer)

	blink_zif_pin1(programmer)
