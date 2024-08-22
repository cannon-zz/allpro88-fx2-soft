import random
from tqdm import tqdm
from . import allpro88

with allpro88.allpro88() as programmer:
	for i in tqdm(range(100000), desc = "loopback test"):
		snd = random.randint(0, 0xffff)
		rcv = programmer.echo(snd)
		assert rcv == snd

	for i in tqdm(range(100000), desc = "port read speed test"):
		# device address 0x0280 is the socket board ID
		programmer.read_addr(0x0280)

	programmer.pcr_enable = True
	for i in tqdm(range(70000), desc = "voltage read speed test"):
		# my unit only has 48 channels installed
		programmer.channels[random.randint(0, 47)].measure_v()
	programmer.pcr_enable = False
