from allpro88 import allpro88
import random
from tqdm import tqdm

allpro88 = allpro88()

for i in tqdm(range(100000), desc = "loopback test"):
	snd = random.randint(0, 0xffff)
	rcv, = allpro88.write_command("E", snd)
	assert rcv == snd

for i in tqdm(range(100000), desc = "port read speed test"):
	# device address 0x0280 is the socket board ID
	allpro88.write_command("?", 0x0280)
