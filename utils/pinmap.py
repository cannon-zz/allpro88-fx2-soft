import allpro88
import select
import sys
import termios
import time
from tqdm import tqdm
import tty

programmer = allpro88.allpro88()

print("system ID = 0x%X\nsocket adapter ID = 0x%X" % (programmer.system_id, programmer.socket_id))

# PCR enable
programmer.pcr_enable = True
# set all pins to ground
for pin in range(88):
	programmer.write_command("=", programmer.pin_addr(pin), allpro88.PINCON.GND)

tty_old_settings = termios.tcgetattr(sys.stdin)
tty.setcbreak(sys.stdin.fileno())

print("j = pin -, k = pin +, q = quit")
try:
	pin = 0
	with tqdm(total = 87, desc = "blinking pin") as progress:
		while True:
			if select.select([sys.stdin], [], [], 0) == ([sys.stdin], [], []):
				c = sys.stdin.read(1)
				if c == "j":
					pin = max(0, pin - 1)
				elif c == "k":
					pin = min(87, pin + 1)
				elif c == "q":
					break
				progress.n = pin
				progress.refresh()
			programmer.write_command("=", programmer.pin_addr(pin), allpro88.PINCON.LOGICH)
			time.sleep(0.5)
			programmer.write_command("=", programmer.pin_addr(pin), allpro88.PINCON.GND)
			time.sleep(0.5)
except KeyboardInterrupt:
	pass

termios.tcsetattr(sys.stdin, termios.TCSADRAIN, tty_old_settings)

# set all pins to disable
for pin in range(88):
	programmer.write_command("=", programmer.pin_addr(pin), allpro88.PINCON.DISABLE)
# PCR disable
programmer.pcr_enable = False
