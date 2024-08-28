import select
import sys
import termios
import time
from tqdm import tqdm
import tty
from . import allpro88

tty_old_settings = termios.tcgetattr(sys.stdin)
tty.setcbreak(sys.stdin.fileno())

with allpro88.allpro88() as programmer:
	allpro88.command_line_banner(programmer)

	# set all pins to ground
	for channel in programmer.channels:
		channel.config = allpro88.PINCON.GND

	# PCR enable
	programmer.pcr_enable = True
	programmer.vadj = allpro88.volt(5.)
	programmer.vtst = allpro88.volt(3.)
	programmer.itst = 15	# mA

	# connect an LED's anode to the pin in question and the cathode to
	# any other pin. no current limit resistor is required
	print("j = channel down, k = channel up, q = quit")
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
				programmer.channels[n].config = allpro88.PINCON.VTST
				time.sleep(0.125)
				programmer.channels[n].config = allpro88.PINCON.GND
				time.sleep(0.125)
	except KeyboardInterrupt:
		pass

termios.tcsetattr(sys.stdin, termios.TCSADRAIN, tty_old_settings)
