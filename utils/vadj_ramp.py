import allpro88
import sys
import time
from tqdm import tqdm

programmer = allpro88.allpro88()

print("system ID = 0x%X\nsocket module = %s" % (programmer.system_id, programmer.socket_module.name))

# PCR enable
programmer.pcr_enable = True

with tqdm(desc = "VADJ", total = 255, mininterval = 0.) as progress:
	def set_vadj(vadj):
		programmer.vadj = progress.n = vadj
		progress.refresh()

	try:
		for i in range(10):
			for vadj in range(256):
				set_vadj(vadj)
				time.sleep(10. / 256)
			for vadj in range(255, -1, -1):
				set_vadj(vadj)
				time.sleep(10. / 256)
	except KeyboardInterrupt:
		set_vadj(0)

# PCR disable
programmer.pcr_enable = False
