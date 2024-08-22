import time
from tqdm import tqdm
from . import allpro88

def blink_idle(programmer, n = 10):
	for i in tqdm(range(n), desc = "blink IDLE LED"):
		programmer.write_addr(0x030c, allpro88.PCR.NIDLE)
		time.sleep(0.5)
		programmer.write_addr(0x030c, allpro88.PCR.DISABLE)
		time.sleep(0.5)

def blink_zif_pin1(programmer, n = 10):
	# connect the anode of an LED to pin 1 and the cathode to any other
	# pin of the DIP48 socket.  no current limiting resistor is
	# required.
	programmer.vadj = allpro88.volt(5.)
	programmer.vtst = allpro88.volt(3.)
	programmer.itst = 15	# mA
	# set all pins to ground
	for channel in programmer.channels:
		channel.config = allpro88.PINCON.GND
	# PCR enable
	programmer.pcr_enable = True
	# toggle DIP48 socket pin 1 between VTST and ground n times
	channel = programmer.socket_module.sockets["DIP48"][1]
	for i in tqdm(range(n), desc = "blink DIP pin 1"):
		channel.config = allpro88.PINCON.VTST
		time.sleep(0.5)
		channel.config = allpro88.PINCON.GND
		time.sleep(0.5)
	# set all pins to disable
	for channel in programmer.channels:
		channel.config = allpro88.PINCON.DISABLE
	# programmer context manager will zero and turn off power supplies


with allpro88.allpro88() as programmer:
	print("system ID = 0x%X\nsocket module = %s" % (programmer.system_id, programmer.socket_module.name))

	blink_idle(programmer)

	blink_zif_pin1(programmer)
