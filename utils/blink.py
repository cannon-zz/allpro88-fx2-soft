from allpro88 import allpro88
import time
from tqdm import tqdm

allpro88 = allpro88()

for i in tqdm(range(10), desc = "blink BUSY LED"):
	allpro88.write_command("=", 0x030c, 0x01)
	time.sleep(0.5)
	allpro88.write_command("=", 0x030c, 0x00)
	time.sleep(0.5)
