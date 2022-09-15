import allpro88
import time
from tqdm import tqdm

programmer = allpro88.allpro88()

def blink_busy():
	for i in tqdm(range(10), desc = "blink BUSY LED"):
		programmer.write_command("=", 0x030c, 0x03)
		time.sleep(0.5)
		programmer.write_command("=", 0x030c, 0x00)
		time.sleep(0.5)

blink_busy()
