import allpro88
import sys
import time
from tqdm import tqdm

programmer = allpro88.allpro88()

print("system ID = 0x%X\nsocket module = %s" % (programmer.system_id, programmer.socket_module.name))

# PCR enable
programmer.pcr_enable = True

# VADJ = max
programmer.vadj = 255

# ensure all pins are disabled (off)
for pin in range(88):
	programmer.write_command("=", programmer.pin_addr(pin), allpro88.PINCON.DISABLE)

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
	for vdac in range(256):
		programmer.vpul = vdac
		programmer.load_dacs()
		expected = -0.54392 + (vdac * 0.100723) + (vdac**2. * 0.000000000497)
		measured = programmer.measure_pin_voltage(pin)
		residual = abs(measured - expected)
		if residual > max_residual:
			max_residual = residual
		rms_residual += residual**2.
		#print("pin %d:  VPUL %d, measured %.3g V, expected %.3g V" % (pin, vdac, measured, expected))
	rms_residual = rms_residual**0.5 / 256.
	print("pin %d VPUL ramp max residual = %.3g V, RMS residual = %.3g V" % (pin, max_residual, rms_residual))
	if rms_residual > 0.010:
		print("\t ^^ large RMS residual for pin %d" % pin)
	programmer.vpul = 0
	programmer.load_dacs()
	programmer.write_command("=", programmer.pin_addr(pin), allpro88.PINCON.DISABLE)


def test_vdac_ramp(programmer, pin):
	programmer.write_command("=", programmer.pin_addr(pin), allpro88.PINCON.VDAC)
	max_residual = 0.
	rms_residual = 0.
	for vdac in range(256):
		programmer.write_command("=", programmer.pin_addr(pin) + 3, vdac)
		programmer.load_dacs()
		expected = max(0., -0.5 + 0.1 * vdac)
		measured = programmer.measure_pin_voltage(pin)
		residual = abs(measured - expected)
		if residual > max_residual:
			max_residual = residual
		rms_residual += residual**2.
		#print("pin %d:  VDAC %d, measured %.3g V, expected %.3g V" % (pin, vdac, measured, expected))
	rms_residual = rms_residual**0.5 / 256.
	print("pin %d VDAC ramp max residual = %.3g V, RMS residual = %.3g V" % (pin, max_residual, rms_residual))
	if rms_residual > 0.020:
		print("\t ^^ large RMS residual for pin %d" % pin)
	programmer.write_command("=", programmer.pin_addr(pin) + 3, 0)
	programmer.load_dacs()
	programmer.write_command("=", programmer.pin_addr(pin), allpro88.PINCON.DISABLE)


def test_vtst_ramp(programmer, pin):
	programmer.write_command("=", programmer.pin_addr(pin), allpro88.PINCON.VTST)
	max_residual = 0.
	rms_residual = 0.
	idac = 10
	for vdac in range(256):
		programmer.vtst = vdac
		programmer.itst = idac
		expected = 0.408 + (0.003855 * idac) + (0.10151 * vdac)
		measured = programmer.measure_pin_voltage(pin)
		residual = abs(measured - expected)
		if residual > max_residual:
			max_residual = residual
		rms_residual += residual**2.
		#print("pin %d:  VTST %d, measured %.3g V, expected %.3g V" % (pin, vdac, measured, expected))
	rms_residual = rms_residual**0.5 / 256.
	print("pin %d VTST ramp max residual = %.3g V, RMS residual = %.3g V" % (pin, max_residual, rms_residual))
	if rms_residual > 0.03:
		print("\t ^^ large RMS residual for pin %d" % pin)
	programmer.vtst = 0
	programmer.itst = 0
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

	print("\n")
	for pin in range(48):
		test_vpul_ramp(programmer, pin)

	print("\n")
	for pin in range(48):
		test_vdac_ramp(programmer, pin)

	print("\n")
	for pin in range(48):
		test_vtst_ramp(programmer, pin)

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
