import allpro88
import sys
import time
from tqdm import tqdm

programmer = allpro88.allpro88()

print("system ID = 0x%X\nsocket module = %s" % (programmer.system_id, programmer.socket_module.name if programmer.socket_module else "not detected"))

# ensure all pins are disabled (off)
for channel in programmer.channel.values():
	channel.config = allpro88.PINCON.DISABLE

# turn on power supplies
programmer.pcr_enable = True

# VADJ = max
programmer.vadj = 255

def test_logich(programmer, pin, trials = 40, max_lo = 0.2, min_hi = 3.9):
	"""
	Toggle the pin between logic high and ground several times, measure the
	voltage in each state, and confirm it is in the allowed range.
	Raise ValueError if the test fails.  Returns the highest voltage
	measured in the GND state, and the lowest voltage measured in the
	LOGICH state.

	Logic TTL high is generated locally on each pin driver board by a
	78L05 regulator IC.  Failure of this test for a group of 8 pins
	likely indicates failure of that regulator IC or of the bus
	interface circuitry on the pin driver board.  If other tests pass
	suspect the regulator IC.

	Failure of this test for an individual pin could indicate a short
	to ground in that pin's output path, possibly on the hybrid module
	driving it.  In addition to the associated analogue circuitry,
	suspect the octal latch chip on the hybrid board whose 8 output
	bits enable and disable the various circuits for the specific pin.
	"""
	channel = programmer.channel[pin]
	print("toggling pin %d GND <--> LOGICH %d times:" % (channel.channel, trials))
	lowest_hi, highest_lo = 25.5, 0.0
	for i in range(trials):
		channel.config = allpro88.PINCON.LOGICH
		v = channel.measure_v()
		if v < lowest_hi:
			lowest_hi = v;
		if v < min_hi:
			raise ValueError("required >= %g V, got %g V" % (min_hi, v))
		channel.config = allpro88.PINCON.GND
		v = channel.measure_v()
		if v > highest_lo:
			highest_lo = v;
		if v > max_lo:
			raise ValueError("expected <= %g V, got %g V" % (max_lo, v))
	channel.config = allpro88.PINCON.DISABLE
	print("\thighest GND voltage = %g V, lowest LOGICH voltage = %g V" % (highest_lo, lowest_hi))
	return lowest_hi, highest_lo


def test_vpul_ramp(programmer, pin):
	"""
	"""
	channel = programmer.channel[pin]
	channel.config = allpro88.PINCON.PULLUP
	max_residual = 0.
	rms_residual = 0.
	for vdac in range(256):
		programmer.vpul = vdac
		programmer.load_dacs()
		expected = -0.54392 + (vdac * 0.100723) + (vdac**2. * 0.000000000497)
		measured = channel.measure_v()
		residual = abs(measured - expected)
		if residual > max_residual:
			max_residual = residual
		rms_residual += residual**2.
		#print("pin %d:  VPUL %d, measured %.3g V, expected %.3g V" % (channel.channel, vdac, measured, expected))
	rms_residual = rms_residual**0.5 / 256.
	print("pin %d VPUL ramp max residual = %.3g V, RMS residual = %.3g V" % (channel.channel, max_residual, rms_residual))
	if rms_residual > 0.010:
		print("\t ^^ large RMS residual for pin %d" % channel.channel)
	programmer.vpul = 0
	programmer.load_dacs()
	channel.config = allpro88.PINCON.DISABLE


def test_vdac_ramp(programmer, pin):
	"""
	Each pin has its own 8-bit DAC controlling a high current
	constant-voltage linear power supply.  This test ramps the DAC from
	minimum to maximum and confirms the voltage measured on the pin is
	within allowed tolerance.

	Partial, weak, shorts to ground often do not cause this test to
	fail because the power supply can deliver enough current to
	overcome the short.  Failure of this test for a group of 8 pins
	likely indicates failure of the bus interface circuitry.
	"""
	channel = programmer.channel[pin]
	channel.config = allpro88.PINCON.VDAC
	max_residual = 0.
	rms_residual = 0.
	for vdac in range(256):
		channel.vdac = vdac
		programmer.load_dacs()
		expected = max(0., -0.5 + 0.1 * vdac)
		measured = channel.measure_v()
		residual = abs(measured - expected)
		if residual > max_residual:
			max_residual = residual
		rms_residual += residual**2.
		#print("pin %d:  VDAC %d, measured %.3g V, expected %.3g V" % (channel.channel, vdac, measured, expected))
	rms_residual = rms_residual**0.5 / 256.
	print("pin %d VDAC ramp max residual = %.3g V, RMS residual = %.3g V" % (channel.channel, max_residual, rms_residual))
	if rms_residual > 0.020:
		print("\t ^^ large RMS residual for pin %d" % channel.channel)
	channel.vdac = 0
	programmer.load_dacs()
	channel.config = allpro88.PINCON.DISABLE


def test_vtst_ramp(programmer, pin, idac = 10):
	"""
	VTST is a variable constant-current/constant-voltage supply used
	either as a current source or as a probe to test for the presence
	of a part.  This test sets the current limit to (a default of) 10
	mA and attempts to ramp the voltage to maximum on a pin while
	measuring the voltage at each setting.  If the measured voltage is
	not within tolerance or the RMS error accumulated over the entire
	ramp is not within tolerance the pin fails.

	Because of the low current limit used, this test is especially good
	at detecting shorts to ground in the pin's driver circuitry.
	"""
	channel = programmer.channel[pin]
	channel.config = allpro88.PINCON.VTST
	max_residual = 0.
	rms_residual = 0.
	for vdac in range(256):
		programmer.vtst = vdac
		programmer.itst = idac
		expected = 0.408 + (0.003855 * idac) + (0.10151 * vdac)
		measured = channel.measure_v()
		residual = abs(measured - expected)
		if residual > max_residual:
			max_residual = residual
		rms_residual += residual**2.
		#print("pin %d:  VTST %d, measured %.3g V, expected %.3g V" % (channel.channel, vdac, measured, expected))
	rms_residual = rms_residual**0.5 / 256.
	print("pin %d VTST ramp max residual = %.3g V, RMS residual = %.3g V" % (channel.channel, max_residual, rms_residual))
	if rms_residual > 0.03:
		print("\t ^^ large RMS residual for pin %d" % channel.channel)
	programmer.vtst = 0
	programmer.itst = 0
	channel.config = allpro88.PINCON.DISABLE


lowest_hi, highest_lo = 25.5, 0.0
for pin in range(48):
	try:
		a, b = test_logich(programmer, pin)
	except ValueError as e:
		print("\tpin failed: %s" % str(e))
		continue
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


for channel in programmer.channel.values():
	channel.config = allpro88.PINCON.DISABLE

# reset all voltages to 0
programmer.vpin = 0
programmer.vpul = 0
programmer.load_dacs()
programmer.vadj = 0

# PCR disable
programmer.pcr_enable = False
