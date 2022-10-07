import allpro88
import sys
import time
from tqdm import tqdm

programmer = allpro88.allpro88()

print("system ID = 0x%X\nsocket adapter ID = 0x%X" % (programmer.system_id, programmer.socket_id))

# PCR enable
programmer.pcr_enable = True

# VADJ = max
programmer.vadj = 255

# ensure all pins are disabled (off)
for pin in range(88):
	programmer.write_command("=", programmer.pin_addr(pin), allpro88.PINCON.GND)

def test_logich(programmer, pin, trials = 40, max_lo = 0.2, min_hi = 3.9):
	"""
	Toggle the pin between logic high and ground several times, measure the
	voltage in each state, and confirm it is in the allowed range.
	Raise ValueError if the test fails.  Returns the highest voltage
	measured in the GND state, and the lowest voltage measured in the
	LOGICH state.
	"""
	print("toggling pin %d GND <--> LOGICH %d times:" % (pin, trials))
	lowest_hi, highest_lo = 25.5, 0.0
	for i in range(trials):
		programmer.write_command("=", programmer.pin_addr(pin), allpro88.PINCON.LOGICH)
		v = programmer.measure_pin_voltage(pin)
		if v < lowest_hi:
			lowest_hi = v;
		if v < min_hi:
			raise ValueError("required >= %g V, got %g V" % (min_hi, v))
		programmer.write_command("=", programmer.pin_addr(pin), allpro88.PINCON.GND)
		v = programmer.measure_pin_voltage(pin)
		if v > highest_lo:
			highest_lo = v;
		if v > max_lo:
			raise ValueError("expected <= %g V, got %g V" % (max_lo, v))
	programmer.write_command("=", programmer.pin_addr(pin), allpro88.PINCON.DISABLE)
	print("\thighest GND voltage = %g V, lowest LOGICH voltage = %g V" % (highest_lo, lowest_hi))
	return lowest_hi, highest_lo


def test_vpul_ramp(programmer, pin):
	programmer.write_command("=", programmer.pin_addr(pin), allpro88.PINCON.PULLUP)
	max_residual = 0.
	rms_residual = 0.
	for vpul in range(256):
		programmer.vpul = vpul
		programmer.load_dacs()
		expected = -0.54392 + (vpul * 0.100723) + (vpul**2. * 0.000000000497)
		measured = programmer.measure_pin_voltage(pin)
		residual = abs(measured - expected)
		if residual > max_residual:
			max_residual = residual
		rms_residual += residual**2.
		#print("pin %d:  vpul %d, measured %g V, expected %g V" % (pin, vpul, measured, expected))
	rms_residual = rms_residual**0.5 / 256.
	print("pin %d VPUL ramp max residual = %g V, RMS residual = %g V" % (pin, max_residual, rms_residual))
	if rms_residual > 0.010:
		print("\t ^^ large RMS residual for pin %d" % pin)
	programmer.vpul = 0
	programmer.load_dacs()
	programmer.write_command("=", programmer.pin_addr(pin), allpro88.PINCON.DISABLE)


try:
	lowest_hi, highest_lo = 25.5, 0.0
	for pin in range(48):
		a, b = test_logich(programmer, pin)
		if a < lowest_hi:
			lowest_hi = a
		if b > highest_lo:
			highest_lo = b
	print("\noverall highest GND voltage = %g V, lowest LOGICH voltage = %g V" % (highest_lo, lowest_hi))

	for pin in range(48):
		test_vpul_ramp(programmer, pin)
except ValueError as e:
	print(e)
	pass

for pin in range(88):
	programmer.write_command("=", programmer.pin_addr(pin), allpro88.PINCON.DISABLE)

# reset all voltages to 0
programmer.vpin = 0
programmer.vpul = 0
programmer.load_dacs()
programmer.vadj = 0

# PCR disable
programmer.pcr_enable = False
