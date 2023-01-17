import allpro88
import select
import sys
import termios
import time
from tqdm import tqdm
import tty

tty_old_settings = termios.tcgetattr(sys.stdin)
tty.setcbreak(sys.stdin.fileno())

with allpro88.allpro88() as programmer:
	print("system ID = 0x%X\nsocket module = %s" % (programmer.system_id, programmer.socket_module.name))

	# PCR enable
	programmer.pcr_enable = True
	# set all pins to ground
	for channel in programmer.channel.values():
		channel.config = allpro88.PINCON.GND

	print("j = channel -, k = channel +, q = quit")
	try:
		n = 0
		with tqdm(total = 87, desc = "blinking channel") as progress:
			while True:
				if select.select([sys.stdin], [], [], 0) == ([sys.stdin], [], []):
					c = sys.stdin.read(1)
					if c == "j":
						n = max(0, n - 1)
					elif c == "k":
						n = min(87, n + 1)
					elif c == "q":
						break
					progress.n = n
					progress.refresh()
				programmer.channel[n].config = allpro88.PINCON.LOGICH
				time.sleep(0.5)
				programmer.channel[n].config = allpro88.PINCON.GND
				time.sleep(0.5)
	except KeyboardInterrupt:
		pass

termios.tcsetattr(sys.stdin, termios.TCSADRAIN, tty_old_settings)
