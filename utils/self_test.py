import allpro88
import matplotlib
from matplotlib import figure
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
matplotlib.rcParams.update({
	"font.size": 10.0,
	"axes.titlesize": 10.0,
	"axes.labelsize": 10.0,
	"xtick.labelsize": 8.0,
	"ytick.labelsize": 8.0,
	"legend.fontsize": 8.0,
	"figure.dpi": 300,
	"savefig.dpi": 300,
	"text.usetex": True
})
import numpy
import scipy.stats
import sys
import time
from tqdm import tqdm
import yaml



def measure_v(channel):
	"""
	Report median of 5 measurements
	"""
	return numpy.median([channel.measure_v() for i in range(5)])


def vtst_measure_r(programmer, channel, max_milliamps):
	# assume 10 mA is required for the VTST base pull-down circuit
	vtst_current = 10

	# set VTST voltage limit to max, and start with current
	# limit set to 0
	programmer.vtst = 255
	# we seem to need to warm it up a bit ... ?
	programmer.itst = vtst_current
	time.sleep(0.1)

	# ramp current, taking voltage readings.
	current = list(range(max_milliamps))
	voltage = []
	for i in current:
		programmer.itst = vtst_current + i
		time.sleep(0.05)
		voltage.append(measure_v(channel))

	# turn off VTST and disable channel
	programmer.vtst = 0
	programmer.itst = 0

	# report resistance
	return scipy.stats.linregress(current, voltage)[0] * 1000.


class channel_driver_test_suite(object):
	"""
	Run a series of tests on a single pin driver channel, and collect
	the results for reporting.  Also, provide the utilities to perform
	individual tests to calling code.
	"""
	def __init__(self, programmer, channel_obj):
		self.programmer = programmer
		self.channel = channel_obj


	def test_vadj_ramp(self):
		"""
		Ramps VADJ up and down in a triangle wave pattern.  NOTE:
		confirming the VADJ power supply voltage and its ramp
		requires access to the interior of the programmer.  This
		code is not intended to be used for self-test purpose.
		"""
		with tqdm(desc = "VADJ", total = 255, mininterval = 0.) as progress:
			def set_vadj(vadj):
				self.programmer.vadj = progress.n = vadj
				progress.refresh()

			for i in range(3):
				for vadj in range(256):
					set_vadj(vadj)
					time.sleep(10. / 256)
				for vadj in range(255, -1, -1):
					set_vadj(vadj)
					time.sleep(10. / 256)


	def test_logich(self, trials = 40, max_lo = 0.2, min_hi = 3.9):
		"""
		Toggle the channel between logic high and ground several
		times, measure the voltage in each state, and confirm it is
		in the allowed range.  Raise ValueError if the test fails.
		Otherwise, returns the highest voltage measured in the GND
		state, and the lowest voltage measured in the LOGICH state.

		Logic TTL high is generated locally on each pin driver
		board by a 78L05 regulator IC.  Failure of this test for a
		group of 8 channels likely indicates failure of that
		regulator IC or of the bus interface circuitry on the pin
		driver board.  If other tests pass suspect the regulator
		IC.  The "TTL high" output is driven onto the channel by
		the same analogue circuity used to drive the clock signal
		onto the channel.  If a clock signal can be delivered but
		not the "TTL high" signal, the analogue electronics is not
		at fault.
		"""
		print("toggling channel %d LOGICL <--> LOGICH %d times:" % (self.channel.channel, trials))
		lowest_hi, highest_lo = 100.0, 0.0
		for i in range(trials):
			self.channel.config = allpro88.PINCON.LOGICH
			v = self.channel.measure_v()
			if v < lowest_hi:
				lowest_hi = v;
			self.channel.config = allpro88.PINCON.LOGICL
			v = self.channel.measure_v()
			if v > highest_lo:
				highest_lo = v;
		self.channel.config = allpro88.PINCON.DISABLE
		failed = lowest_hi < min_hi or highest_lo > max_lo
		print("\thighest LOGICL voltage = %g V, lowest LOGICH voltage = %g V%s" % (highest_lo, lowest_hi, "" if not failed else "\t<-- FAILED"))
		return lowest_hi, highest_lo


	def test_vpul_ramp(self):
		"""
		"""
		self.channel.config = allpro88.PINCON.PULLUP
		max_residual = 0.
		rms_residual = 0.
		for vdac in range(256):
			self.programmer.vpul = vdac
			self.programmer.load_dacs()
			expected = self.programmer.vpul.cal(vdac)
			measured = self.channel.measure_v()
			residual = abs(measured - expected)
			if residual > max_residual:
				max_residual = residual
			rms_residual += residual**2.
		rms_residual = rms_residual**0.5 / 256.
		failed = rms_residual > 0.010
		print("channel %d VPUL ramp max residual = %.3g V, RMS residual = %.3g V%s" % (self.channel.channel, max_residual, rms_residual, "" if not failed else "\t<-- FAILED"))
		self.programmer.vpul = 0
		self.programmer.load_dacs()
		self.channel.config = allpro88.PINCON.DISABLE


	def test_pulldn(self):
		"""
		In pull-down mode there should be about 5.4 kOhm of
		resistance to ground.  This test enables the pull-down
		mode, then applies a VTST current ramp to measure the
		resistance to ground.
		"""
		# I don't know what current the pull-down circuit path can
		# handle.  the 7406 inverter that drives it can sink up to
		# 40 mA on any output, but that would require over 200 V to
		# be applied to the circuit and would lead to over 8 W of
		# power being disspated by the 5.4 kOhm resistor, so I
		# don't think the 7406's limits define the limits of the
		# circuit.  VTST can't deliver more than about 25 V, which
		# means the current flow will never get above about 5 mA
		# and the power dissipated won't get above 1/8 W.  those
		# are probably safe for the 5.4 kOhm resistors.

		# enable VTST and pull-down modes together
		self.channel.config = allpro88.PINCON.VTST | allpro88.PINCON.PULLDN

		# measure resistance.  don't let current exceed 5 mA
		R = vtst_measure_r(self.programmer, self.channel, 5)

		# disable VTST
		self.channel.config = allpro88.PINCON.DISABLE

		failed = R < 5000.
		print("channel %d pull-down resistance:  %.0f Ohm%s" % (self.channel.channel, R, "" if not failed else "\t<-- FAILED"))


	def test_logicl(self):
		"""
		The TTL low driver is a 50 Ohm resistor to ground.  This
		test uses a VTST current ramp to test for this resistance.
		"""
		# enable VTST and logic low modes together
		self.channel.config = allpro88.PINCON.VTST | allpro88.PINCON.LOGICL

		# measure resistance.  don't let current exceed 20 mA
		R = vtst_measure_r(self.programmer, self.channel, 10)

		# disable VTST
		self.channel.config = allpro88.PINCON.DISABLE

		failed = False
		print("channel %d logic low pull-down resistance:  %.0f Ohm%s" % (self.channel.channel, R, "" if not failed else "\t<-- FAILED"))


	def test_vdac_ramp(self):
		"""
		Each channel has its own 8-bit DAC controlling a high
		current constant-voltage linear power supply.  This test
		ramps the DAC from minimum to maximum and confirms the
		voltage measured on the channel is within allowed
		tolerance.
		"""
		# configure for VDAC output.  enable the pull-down driver
		# (5.4 kOhm to ground) so the output sees a load, otherwise
		# the voltage drop across the final diode in the driver
		# circuit isn't measured properly.  at the maximum output
		# voltage, a bit less than 1/8 W is being dissipated by the
		# pull-down resistor, which hopefully is safe.  turn on the
		# bypass capacitor to reduce noise
		self.channel.config = allpro88.PINCON.VDAC | allpro88.PINCON.PULLDN
		self.channel.bypass = True

		# run the DAC from 0 to 255 inclusively and measure the
		# output voltage
		self.vdac_ramp_x = numpy.arange(256)
		self.vdac_ramp_y = numpy.zeros(256)
		for i, dac in enumerate(self.vdac_ramp_x):
			self.channel.vdac = dac
			self.programmer.load_dacs()
			self.vdac_ramp_y[i] = measure_v(self.channel)

		# disable output
		self.channel.vdac = 0
		self.programmer.load_dacs()
		self.channel.bypass = False
		self.channel.config = allpro88.PINCON.DISABLE

		# report deviation from calibration model
		expected = numpy.array([self.channel.cal(dac) for dac in self.vdac_ramp_x])
		max_residual = abs(self.vdac_ramp_y[2:] - expected[2:]).max()
		rms_residual = ((self.vdac_ramp_y[2:] - expected[2:])**2.).mean()**0.5
		failed = max_residual > 0.3
		print("channel %d VDAC ramp max residual = %.3g V, RMS residual = %.3g V%s" % (self.channel.channel, max_residual, rms_residual, "" if not failed else "\t<-- FAILED"))

		# derive updated calibration model and report what its
		# accuracy would have been
		self.vdac_ramp_cal = {
			"poly": tuple(map(float, numpy.polyfit(self.vdac_ramp_x[6:], self.vdac_ramp_y[6:], 2))),
			"min": float(numpy.median(self.vdac_ramp_y[:4]))
		}
		print("\tupdated calibration model:  max(%.3g, %.3g dac^2 + %.3g dac + %.3g)" % ((self.vdac_ramp_cal["min"],) + self.vdac_ramp_cal["poly"]))
		@numpy.vectorize
		def model(dac):
			return max(self.vdac_ramp_cal["min"], (self.vdac_ramp_cal["poly"][0] * dac + self.vdac_ramp_cal["poly"][1]) * dac + self.vdac_ramp_cal["poly"][2])
		print("\tupdated model's max residual = %.3g V" % (abs(model(self.vdac_ramp_x[2:]) - self.vdac_ramp_y[2:]).max()))

		# plot the results
		fig = figure.Figure()
		FigureCanvas(fig)
		axes = fig.gca()
		axes.set_title("Channel %02d Voltage vs. DAC" % self.channel.channel)
		axes.set_xlabel("DAC Value (counts)")
		axes.set_ylabel("Voltage (volts)")
		axes.scatter(self.vdac_ramp_x, self.vdac_ramp_y, marker = ".", color = "k")
		axes.xaxis.set_major_locator(matplotlib.ticker.MultipleLocator(32))
		axes.xaxis.set_minor_locator(matplotlib.ticker.MultipleLocator(4))
		axes.tick_params(which = "both")
		axes.grid(True, which = "both")
		axes.set_xlim((0, 256))
		fig.savefig("channel%02d_vdac_ramp.png" % self.channel.channel)


	def test_vtst(self):
		"""
		VTST is a variable constant-current/constant-voltage supply
		used either as a current source or as a probe to test for
		the presence of a part.

		The VTST drive output is delivered to the pin via a PNP
		transistor whose base is pulled towards ground when the
		output is enabled.  If it was shorted directly to ground
		the current flowing through the emitter-base junction would
		damage the transistor as soon as VTST was raised high
		enough to forward-bias the junction, so a current limiting
		circuit is used to limit the base current to at most about
		10 mA.  If the transistor's gain is at least about 100 then
		that's enough to ensure the transistor can deliver VTST's
		max current driving capabilities to the pin (minus the 10
		mA going through the base).

		The current limiting circuit is a 68 Ohm resistor combined
		with a PNP transistor whose base rides on the high side of
		the resistor, whose collector is tied to the digital
		control signal and whose emitter is grounded.  If the
		voltage drop across the resistor is less than the
		forward-bias voltage of the PNP transistor's base-emitter
		junction the circuit looks like the 68 Ohm resistor to
		ground.  Once the voltage drop gets above about 600 mV
		(approximately 10 mA of current flows) the transitor begins
		to conduct, partially shorting the digital control signal
		to ground and throttling the current pulled out through the
		driver transistor's base.

		All of this circuitry appears in parallel across
		whatever load is inserted into the socket that VTST is
		being used to probe.  So if nothing is connected to the
		VTST output, then VTST sees a 68 Ohm resistor up to a
		current of about 10 mA after which it sees a fixed 10 mA
		current sink regardless of voltage.

		This test measures the properties of the output
		transistor's base control circuitry, testing for the 68 Ohm
		resistor, by ramping the current limit and measuring the
		voltage developed by the VTST output.

		Unfortunately, these measurements require tweaking the
		parameters of the VTST power supply at the very bottom end
		of its operating regime and there's quite a bit of noise in
		these measurements.  It is recommended that the results of
		this test not be taken too seriously until the programmer
		has been allowed a 20 min or longer warm up period.
		"""
		self.channel.config = allpro88.PINCON.VTST

		# measure the resistance to ground in the base pull-down
		# circuit

		# limit the output voltage to about 9 V.  precise value not
		# important, but we want to stay in the linear, ohmic,
		# regime of the circuit.  we don't want to enter the
		# constant current regime.
		self.programmer.vtst = 90
		# we seem to need to warm it up a bit ... ?
		self.programmer.itst = 9
		time.sleep(0.1)
		# ramp the output current, and measure the voltage on the
		# output.  the slope gives us the resistance.  again, we
		# need to not leave the ohmic regime of the circuit, so the
		# current must be kept to less than 10 mA.
		idac = list(range(10))
		R = scipy.stats.linregress(idac, [measure_v(self.channel) for self.programmer.itst in idac])[0] * 1000.
		self.programmer.itst = 0	# reset to 0
		print("channel %d VTST base pull-down resistance: %.3g Ohm" % (self.channel.channel, R))

		# measure the current limit threshold in the base pull-down
		# circuit by setting the drive voltage to max and seeing
		# what VTST current limit allows us to achieve that voltage

		self.programmer.vtst = 255
		for current_limit in range(256):
			self.programmer.itst = current_limit
			time.sleep(0.05)
			if self.channel.measure_v() > 20.:
				break
		failed = current_limit > 12
		print("channel %d VTST base pull-down current limit: %.3g mA%s" % (self.channel.channel, current_limit, "" if not failed else "\t<-- FAILED"))

		self.programmer.vtst = 0
		self.programmer.itst = 0
		self.channel.config = allpro88.PINCON.DISABLE


calibration = {}
with allpro88.allpro88() as programmer:
	print("system ID = 0x%X\nsocket module = %s" % (programmer.system_id, programmer.socket_module.name if programmer.socket_module else "not detected"))

	# turn on power supplies
	programmer.pcr_enable = True

	#channel_driver_test_suite(programmer, None).test_vadj_ramp()

	# VADJ = max
	programmer.vadj = 255

	for channel in range(48):
		calibration_name = "channel%02d" % channel
		calibration[calibration_name] = {}

		test_suite = channel_driver_test_suite(programmer, programmer.channel[channel])
		print("channel %d --> pin driver group %d, DAC U%d, hybrid H%d, hybrid channel %d" % ((channel,) + programmer.channel[channel].physical))
		try:
			print("channel %d --> DIP48 pin %d" % (channel, programmer.socket_module.pin_lookup("DIP48", channel)))
		except KeyError:
			print("channel %d --> DIP48 no connection" % channel)

		test_suite.test_logich()

		test_suite.test_vpul_ramp()

		test_suite.test_vdac_ramp()
		calibration[calibration_name]["vdac_ramp_cal"] = test_suite.vdac_ramp_cal

		test_suite.test_vtst()

		test_suite.test_pulldn()

		test_suite.test_logicl()

		print("\n")

	# context manager turns off all power supplies, we don't have to do
	# that here.

with open("calibration.dat", "w") as calfile:
	yaml.dump(calibration, calfile)
