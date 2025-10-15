import argparse
import datetime
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
from . import allpro88
import hioki3801


#
# when computing polynomial fits to DAC voltage data, use this weight
# function.  we want the fit to be more strongly constrained at the end
# points than in the middle so that the voltages at the ends of the range
# are correct.  we don't want a situation where the curve is predicting
# output voltages with the wrong sign at the low end, for example, as
# that's physically impossible.  the following is 1.0 at counts of 0 and
# 255, and about 0.5 at a count of 128.
#

dacfitweights = numpy.fromfunction(numpy.polynomial.Polynomial((1., -2. / 255, +2. / 255**2)), (256,))


class power_supply_sweep(object):
	"""
	Notes on power supply behaviour

	The VPUL power supply is constructed from a DAC0832 current DAC, an
	op amp acting as a current-to-voltage converter, a second op amp
	acting as a gain amplifier to set the output voltage range, and a
	NPN power transistor in an emitter-follower configuration to
	provide high current output capability.  The final op amp's output
	voltage can be observed on TP6 on Analogue Control 1.  The NPN
	power transistor does not begin to conduct until the voltage
	difference across its base-emitter junction exceeds about 0.6 V,
	and the circuit employs an LM334 current source from the
	transistor's emitter to the -5 V supply rail, set to about 5 mA, to
	pull the emitter potential down and ensure the transistor's
	base-emitter junction is always forward biased and conducting even
	when the op amp output voltage is at 0 V.  This ensures the VPUL
	potential remains controlled at all times, it's never freely
	floating.  All of this also means, however, that VPUL is expected
	to be about 0.6 V below the op amp output voltage on TP6, and in
	particular it is expected to be slightly negative for low DAC
	settings.  Failing to see VPUL go negative at low DAC settings
	might indicate a failure of the -5 V supply or of the LM334 current
	source.  The NPN power transistor is rated for at least 1 A maximum
	collector current, which is enough to deliver VPUL's maximum
	voltage to all 88 2.7 kOhm pull-up resistors in a fully-equiped
	unit, when all 88 are being shorted to ground.
	"""
	def __init__(self, programmer, which = ["VADJ", "VTH", "VPUL", "VSR", "VTST"], meter = None):
		self.programmer = programmer
		which = set(which)
		# do VADJ first if it's in the list so that it's ramped
		# from 0 to max and then left there while other tests are
		# done.  if it's not in the list, the tests will set it to
		# max before running
		for name, sweepfunc in (
			("VADJ", self.sweep_vadj),
			("VTH", self.sweep_vth),
			("VPUL", self.sweep_vpul),
			("VSR", self.sweep_vsr),
			("VTST", self.sweep_vtst)
		):
			if name in which:
				ramp_x, ramp_y, model = sweepfunc(meter = meter)
				which.remove(name)
		if which:
			raise ValueError("unrecognized power supplies: %s" % which)

	def test_vadj_ramp(self):
		"""
		Ramps VADJ up and down in a triangle wave pattern.
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

	def sweep(self, attr, leave_at = 0, meter = None):
		# need VADJ at max to test other power supplies
		if attr != "vadj":
			self.programmer.vadj = 255
		# run a DAC from 0 to 255 inclusively and measure the
		# output voltage.  to make this process go faster, only
		# every 5th value is measured.
		ramp_x = numpy.arange(0, 256, 5)
		ramp_y = numpy.zeros_like(ramp_x, dtype = "double")
		for i, dac in enumerate(ramp_x):
			setattr(self.programmer, attr, dac)
			if attr == "vpul":
				self.programmer.load_dacs()
			print("@ DAC count %03d:  " % dac, end = "", flush = True)
			if meter is None:
				ramp_y[i] = float(input("voltage (in volts) = "))
			else:
				# wait for the meter to stabilize
				time.sleep(2.)
				# measure the 5 second arithmetic mean
				ramp_y[i] = meter.time_average(5.)
				print("voltage = %g V" % ramp_y[i])
		# leave DAC at requested value (typically 0 for safety)
		setattr(self.programmer, attr, leave_at)
		if attr == "vpul":
			self.programmer.load_dacs()
		# done
		return ramp_x, ramp_y

	def plot(self, attr, ramp_x, ramp_y, model):
		fig = figure.Figure()
		FigureCanvas(fig)
		axes = fig.add_axes((0.1, 0.3, 0.85, 0.65))
		axes.set_title("%s DAC Calibration" % attr.upper())
		#axes.set_xlabel("DAC Value (count)")
		axes.set_ylabel("Voltage (volts)")
		axes.plot(ramp_x, ramp_y, fmt = "ok", label = "Observed")
		model_x = numpy.linspace(0, 255, 256)
		axes.plot(model_x, model(model_x), label = "Calibration model")
		axes.xaxis.set_major_locator(matplotlib.ticker.MultipleLocator(32))
		axes.xaxis.set_minor_locator(matplotlib.ticker.MultipleLocator(4))
		axes.yaxis.set_major_locator(matplotlib.ticker.MultipleLocator(5))
		axes.yaxis.set_minor_locator(matplotlib.ticker.MultipleLocator(1))
		axes.tick_params(which = "both")
		axes.grid(True, which = "both")
		axes.legend(loc = "upper left")
		axes.set_xlim((0, 256))
		axes.set_ylim((-1, 30))

		axes = fig.add_axes((0.1, 0.1, 0.85, 0.15))
		axes.set_xlabel("DAC Value (count)")
		axes.set_ylabel("Residual (volts)")
		axes.plot(ramp_x, ramp_y - model(ramp_x), label = "Observed - model")
		axes.xaxis.set_major_locator(matplotlib.ticker.MultipleLocator(32))
		axes.xaxis.set_minor_locator(matplotlib.ticker.MultipleLocator(4))
		axes.tick_params(which = "both")
		axes.grid(True, which = "both")
		axes.legend(loc = "lower center")
		axes.set_xlim((0, 256))
		axes.set_ylim((-0.075, +0.075))
		fig.savefig("%s_ramp.png" % attr)

	def sweep_vadj(self, meter = None):
		print("\ncalibrating main adjustable power supply, VADJ.\nConnect multimeter leads:\n\t+ --> DIN 1 (primary), pin A5\n\t- --> DIN 1 (primary), pin C1\nPress Enter when ready ...")
		input()
		# after sweep, must be left at max for other tests
		self.vadj_ramp_x, self.vadj_ramp_y = self.sweep("vadj", leave_at = 255, meter = meter)
		self.vadj_model = numpy.polynomial.Polynomial.fit(self.vadj_ramp_x[1:-3], self.vadj_ramp_y[1:-3], 2, w = dacfitweights[self.vadj_ramp_x[1:-3]]).convert()
		self.plot("vadj", self.vadj_ramp_x, self.vadj_ramp_y, self.vadj_model)
		return self.vadj_ramp_x, self.vadj_ramp_y, self.vadj_model

	def sweep_vth(self, meter = None):
		print("\ncalibrating threshold DAC, VTH.\nConnect multimeter leads:\n\t+ --> DIN 1 (primary), pin B9\n\t- --> DIN 1 (primary), pin C1\nPress Enter when ready ...")
		input()
		self.vth_ramp_x, self.vth_ramp_y = self.sweep("vth", meter = meter)
		self.vth_model = numpy.polynomial.Polynomial.fit(self.vth_ramp_x, self.vth_ramp_y, 2, w = dacfitweights[self.vth_ramp_x]).convert()
		self.plot("vth", self.vth_ramp_x, self.vth_ramp_y, self.vth_model)
		return self.vth_ramp_x, self.vth_ramp_y, self.vth_model

	def sweep_vpul(self, meter = None):
		print("\ncalibrating pull-up power supply, VPUL.\nConnect multimeter leads:\n\t+ --> DIN 1 (primary), pin B4\n\t- --> DIN 1 (primary), pin C1\nPress Enter when ready ...")
		input()
		self.vpul_ramp_x, self.vpul_ramp_y = self.sweep("vpul", meter = meter)
		self.vpul_model = numpy.polynomial.Polynomial.fit(self.vpul_ramp_x[1:], self.vpul_ramp_y[1:], 2, w = dacfitweights[self.vpul_ramp_x[1:]]).convert()
		self.plot("vpul", self.vpul_ramp_x, self.vpul_ramp_y, self.vpul_model)
		return self.vpul_ramp_x, self.vpul_ramp_y, self.vpul_model

	def sweep_vsr(self, meter = None):
		print("\ncalibrating sweep rate DAC, VSR.\nConnect multimeter leads:\n\t+ --> DIN 1 (primary), pin B3\n\t- --> DIN 1 (primary), pin C1\nPress Enter when ready ...")
		input()
		self.vsr_ramp_x, self.vsr_ramp_y = self.sweep("vsr", meter = meter)
		self.vsr_model = numpy.polynomial.Polynomial.fit(self.vsr_ramp_x[1:], self.vsr_ramp_y[1:], 2, w = dacfitweights[self.vsr_ramp_x[1:]]).convert()
		self.plot("vsr", self.vsr_ramp_x, self.vsr_ramp_y, self.vsr_model)
		return self.vsr_ramp_x, self.vsr_ramp_y, self.vsr_model

	def sweep_vtst(self, meter = None):
		print("\ncalibrating constant current supply's maximum voltage DAC, VTST.\nConnect multimeter leads:\n\t+ --> DIN 1 (primary), pin B2\n\t- --> DIN 1 (primary), pin C1\nPress Enter when ready ...")
		input()
		# the current-limited power supply's output, when unloaded,
		# is a function of both the VTST DAC setting and the ITST
		# DAC setting.  for the calibration ramp we set ITST to 0.
		# increasing this DAC's setting increases the output
		# voltage for a given VTST DAC setting, so this
		# configuration gives us a lower bound on the calibrated
		# output voltage
		self.programmer.itst = 0
		# ramp the voltage limit DAC
		self.vtst_ramp_x, self.vtst_ramp_y = self.sweep("vtst", meter = meter)
		self.vtst_model = numpy.polynomial.Polynomial.fit(self.vtst_ramp_x[1:], self.vtst_ramp_y[1:], 2, w = dacfitweights[self.vtst_ramp_x[1:]]).convert()
		return self.vtst_ramp_x, self.vtst_ramp_y, self.vtst_model


class channel_driver_test_suite(object):
	"""
	Run a series of tests on a single pin driver channel, and collect
	the results for reporting.  Also, provide the utilities to perform
	individual tests to calling code.
	"""
	def __init__(self, programmer, channel_obj):
		self.programmer = programmer
		self.channel = channel_obj
		# for convenience, a vectorized wrapper of the programmer's
		# .round_v() method to convert a voltage applied to the pin
		# to the value that will be reported by the quantized VTH
		# based measurement of that voltage
		def round_v(v):
			return self.programmer.round_v(v)
		self.round_v = numpy.vectorize(round_v)


	def measure_v(self):
		"""
		Measure the voltage on this channel 5 times and report the
		median.
		"""
		return self.channel.measure_v(5)


	def vtst_measure_r(self, max_milliamps):
		"""
		Use a ramp on the VTST current limited power supply to
		measure the resistance between this channel's output and
		ground.  The channel's configuration register is not
		modified by this method:  calling code must ensure VTST
		mode is enabled on this channel (and disabled on all other
		chanenls) or this function will report nonsense.
		"""
		# assume 10 mA is required for the VTST base pull-down
		# circuit.  FIXME:  this should be taken from the
		# calibration if available.
		vtst_current = 10

		# set VTST voltage limit to max
		self.programmer.vtst = 255
		# we seem to need to warm it up a bit ... ?
		self.programmer.itst = vtst_current + max_milliamps
		time.sleep(0.1)

		# ramp current, taking voltage readings.
		current = list(range(max_milliamps, -1, -1))
		voltage = []
		for i in current:
			self.programmer.itst = vtst_current + i
			time.sleep(0.05)
			voltage.append(self.measure_v())

		# turn off VTST
		self.programmer.vtst = 0
		self.programmer.itst = 0

		# report resistance in Ohms (currents and voltages are
		# measured in milliamperes and volts, respectively)
		return scipy.stats.linregress(current, voltage)[0] * 1000.


	def test_logich(self, trials = 40, max_lo = 0.2, min_hi = 3.9):
		"""
		Toggle the channel between TTL logic high and logic low
		several times, measure the voltage in each state, and
		confirm it is in the allowed range.  Returns the highest
		voltage measured in the logic low state, and the lowest
		voltage measured in the logic high state.

		The TTL logic high supply voltage is generated locally on
		each pin driver board by a 78L05 regulator IC.  Failure of
		this test for a group of 8 channels likely indicates
		failure of that regulator IC or of the bus interface
		circuitry on the pin driver board.  If other tests pass
		suspect the regulator.  The "TTL high" output is driven
		onto the channel by the same analogue circuity used to
		drive the clock signal onto the channel.  If a clock signal
		can be delivered but not the "TTL high" signal, the
		analogue electronics is not at fault, the fault is in the
		digital decode logic.

		A small, approximately 10 Ohm, resistor is in series with
		the TTL high output, so loads cause the voltage to sag.
		If, with no configured load, the output switches, but does
		not achieve the expected voltage, suspect a partial short
		to ground.  If the low TTL voltage problem is common to all
		channels on the same pin driver board, suspect the
		regulator or one or more stuck bits in the digital control
		electronics.  If the problem is unique to a channel, then
		checking the behaviour of that channel's VPUL and VTST
		outputs (which are especially sensitive to current paths to
		ground) can provide a clue as to the location of the fault.
		If VPUL and VTST exhibit no unusual behaviour, the fault is
		almost certainly the VTTL reverse protection diode, the
		output transistor, or the demux driver chip, all on the
		hybrid module.  Also suspect the VDAC output reverse
		protection diode on the pin driver carrier board.  Enabling
		both VDAC output and the ground-drive transistor overloads
		this diode, possibly causing it to fail and thereafter
		provide a path to ground through the VDAC power
		transistor's emitter bias circuit.
		"""
		print("toggling channel %d LOGICL <--> LOGICH %d times:" % (self.channel.channel, trials))
		lowest_hi, highest_lo = 100.0, 0.0
		for i in range(trials):
			self.channel.config = allpro88.PINCON.LOGICH
			lowest_hi = min(lowest_hi, self.channel.measure_v())
			self.channel.config = allpro88.PINCON.LOGICL
			highest_lo = max(highest_lo, self.channel.measure_v())
		self.channel.config = allpro88.PINCON.DISABLE
		failed = lowest_hi < min_hi or highest_lo > max_lo
		print("\thighest LOGICL voltage = %g V, lowest LOGICH voltage = %g V%s" % (highest_lo, lowest_hi, "" if not failed else "\t<-- FAILED"))
		return lowest_hi, highest_lo


	def test_vpul(self, diode_vf):
		"""
		diode_vf is the current calibration's average VPUL reverse
		protection diode forward-bias voltage.  It is required,
		here, to partially un-calibrate the VPUL pin voltage to
		obtain the internal VPUL voltage being applied to the
		pin-driver circuit for some tests.
		"""
		# this test checks the circuit for placing the pull-up
		# voltage onto a pin.  the VPUL power supply is assumed to
		# have been manually calibrated before this step.
		#
		# the pull-up voltage is switched onto a pin using a PNP
		# transistor that is biased into the off state by the
		# pull-up voltage itself, and biased into the on state by
		# an open-collector 7406 inverter whose output pulls the
		# biasing network to ground greating a voltage differential
		# across the PNP transistor's emitter-base junction.  the
		# biasing network consists of a 10 kOhm resistor between
		# the pull-up rail and the transitor's base, and a 10 kOhm
		# resistor between the base and the 7406's output.  when
		# the inverter's output if "false", the pair of resistors
		# put the base at 1/2 the voltage of the pull-up rail.  at
		# room temperature the transistor requires about 0.6 V
		# across the emitter-base junction before it conducts,
		# therefore until the pull-up voltage exceeds about 1.2 V
		# the transistor remains off and the pull-up voltage cannot
		# appear on a pin.  a Schottky diode with a forward bias
		# voltage of about 150 mV protects the circuit from reverse
		# voltages, so when the transistor turns on, the voltage
		# that appears on that pin is about 150 mV below the
		# pull-up power supply's configured voltage (assuming there
		# is no load on the pin).
		#
		# by assuming the pull-up and threshold power supplies have
		# been correctly calibrated, we can compare the configured
		# to observed pull-up voltage on a pin to check the health
		# of the switching transistor and reverse protection diode.
		# we can use the y-intercept of a voltage ramp to measure
		# the forward-bias voltage of the reverse protection diode,
		# and then after correcting for that we can mesaure the
		# voltage at which the pull-up output first appears to
		# cross the emitter-base forward-bias voltage of the
		# switching transistor.
		#
		# to do these tests, we configure the channel for pull-up
		# and turn on the pull-down driver.  without the pull-down
		# resistor turned on, these measurements don't work, we
		# need something to establish a voltage difference across
		# the reverse protection diode or it won't turn on and the
		# voltage measurements are nonsensical.  we also make a
		# point of not using the bypass capacitor on the channel
		# because the resistance in the circuit leads to too high a
		# time constant, and then unless inconveniently long delays
		# are added the voltage measurements become unreliable.
		# even without the bypass capacitor, we need to wait a bit
		# for stray capacitance.
		#
		# for the pull-up supply specifically, the pull-down
		# resistance is only 2.7 kOhm to ground, because the
		# pull-up driver drives the mid-point of the pull-down
		# circuit's 5.4 kOhm resistor.  I don't know what power the
		# resistor is rated to dissipate, but if we assume the pull
		# down current path has been designed to work safely in
		# conjunction with a pin DAC at it's maximum output
		# voltage, then because only 1/2 of that total resistance
		# is between the pull-up voltage source and ground we
		# assume here that we can safely ramp the pull-up voltage
		# to 1/2 of its maximum value so that the current flowing
		# through the pull-down resistor is limited to what it
		# would be in the worst-case VDAC configuration, meaning
		# about 63 mW is dissipated by the resistor.  even with the
		# VPUL voltage set to its maximum of about 25 V, only about
		# 1/4 W would be dissipated in the pull-down resistor,
		# which doesn't sound like a lot for the resistor to
		# handle, nevertheless we avoid stressing it.

		self.channel.config = allpro88.PINCON.PULLUP | allpro88.PINCON.PULLDN
		self.channel.bypass = False	# make sure it's off
		# discharge the circuit
		self.programmer.vpul = 0
		self.programmer.load_dacs()
		time.sleep(0.2)	# wait for RC delay

		# ramp the pull-up DAC over a range of voltages to measure
		# a voltage curve.  for what we are doing here, we want to
		# record the measured voltage as a function of the pull-up
		# voltage applied to the circuit, meaning not as a function
		# of the pull-up power supply's DAC setting, and not as a
		# function of the pull-up voltage model that includes the
		# diode Vf parameter that we in the process of trying to
		# measure.  we need to zero that parameter while we do this
		# test, by removing it from the calibration model.
		self.vpul_ramp_x = numpy.zeros(128)
		self.vpul_ramp_y = numpy.zeros(128)
		for dac in tqdm(range(128), "VPUL"):
			self.programmer.vpul = dac
			self.programmer.load_dacs()
			time.sleep(0.010)	# wait for RC delay
			# the applied VPUL voltage is obtained by adding
			# the calibration model's diode_vf parameter to the
			# vpul calibration model.
			self.vpul_ramp_x[dac] = self.programmer.vpul.cal(dac, self.programmer) + diode_vf
			self.vpul_ramp_y[dac] = self.measure_v()

		# disable channel
		self.programmer.vpul = 0
		self.programmer.load_dacs()
		self.channel.config = allpro88.PINCON.DISABLE

		# get a fit from what should be the linear regime.  the
		# y-intercept is an estimate of the forward-bias voltage of
		# the reverse protection diode.
		poly = numpy.polynomial.Polynomial.fit(self.vpul_ramp_x[20:], self.vpul_ramp_y[20:], 1, w = dacfitweights[20:128]).convert()
		# require slope to be within 2% of 1.0.  NOTE:  in my
		# experience, failure of this test is caused by the failure
		# of the reverse protection diode in the TTL high output
		# drive circuit.  on three occasions, so far, that has been
		# the cause.
		failed = not (0.98 <= poly.coef[1] <= 1.02)
		print("channel %d VPUL fit: %s%s" % (self.channel.channel, poly, "\t<-- FAILED" if failed else ""))

		# the y-intercept of the observed voltage vs applied
		# voltage line provides the forward-bias voltage of this
		# pin's reverse protection diode.
		self.vpul_diode_vf = -poly.coef[0]
		# require Vf consistent with Schottky diode
		failed = not (0.150 <= self.vpul_diode_vf <= 0.35)
		print("channel %d VPUL reverse-protection Vf:  %.3g V%s" % (self.channel.channel, self.vpul_diode_vf, "\t<-- FAILED" if failed else ""))

		# identify the voltage at which the output transistor turns
		# on by searching for the VPUL voltage below which the
		# mesaured voltage disagrees with the model.  measuring
		# where that occurs gives us an estimate of twice the
		# transistor's emitter-base forward-bias voltage.

		# for which VPUL voltages does the observed voltage
		# disagree with the linear fit?  "agree" --> residual <= 1
		# DAC count for VTH.  find the threshold where a transition
		# occurs.
		not_good = abs(self.round_v(poly(self.vpul_ramp_x[:40])) - self.vpul_ramp_y[:40]) > 0.12
		assert not all(not_good), "cannot identify VPUL output transistor bias voltage:  no measured voltages are consistent with VPUL calibration:\nx = %s\ny = %s\nresidual = %s" % (self.vpul_ramp_x[:40], self.vpul_ramp_y[:40], self.vpul_ramp_y[:40] - self.vpul_ramp_x[:40])
		threshold = max(i for i, i_not_good in enumerate(not_good) if i_not_good) + 1
		assert 5 <= threshold <= 40
		minimum = numpy.median(self.vpul_ramp_y[:5])

		self.vpul_trans_vf = self.vpul_ramp_x[threshold] / 2.0
		failed = not (0.6 <= self.vpul_trans_vf <= 0.8)
		print("channel %d VPUL transistor Veb:  %.3g V%s" % (self.channel.channel, self.vpul_trans_vf, "\t<-- FAILED" if failed else ""))
		print("channel %d VPUL voltage when transistor off:  %.3g V" % (self.channel.channel, minimum))

		# if the pin driver circuitry is working optimally, for
		# voltages above the switch transistor's turn-on voltage
		# the observed voltage should be the applied pull-up
		# voltage minus the reverse protection diode's forward bias
		# voltage quantized to an integer VTH DAC setting.
		# measure the difference between the observed voltage and
		# that simple model.  because the VPUL drive circuit for
		# each pin includes 2.7 kOhm of output impedance, partial
		# short circuits to ground will drag down the observed
		# voltage.  given the VTH quantization noise of 0.1 V, the
		# limit of detection for a stray current path to ground is
		# about 680 kOhm.  leakage to ground through resistances as
		# high as 250 kOhm should be easily seen, so this is quite
		# a sensitive test for faults in the rest of the pin driver
		# circuitry.
		def model(vpul):
			return numpy.where(vpul < 2 * self.vpul_trans_vf, minimum, vpul - self.vpul_diode_vf)

		residual = self.vpul_ramp_y[threshold:] - self.round_v(model(self.vpul_ramp_x[threshold:]))
		max_residual = abs(residual).max()
		rms_residual = (residual**2.).mean()**0.5
		# allow 1 DAC count of disagreement for VTH
		failed = max_residual > 0.12
		print("\tw.r.t. basic calibration max residual = %.3g V, RMS residual = %.3g V%s" % (max_residual, rms_residual, "" if not failed else "\t<-- FAILED"))

		# plot the results.  take the reverse protection diode's
		# forward voltage back out of the y values to plot the
		# actual voltage measurements.  draw a 1-to-1 line offset
		# by the reverse protection diode's bias voltage and a
		# vertical line at the switching transistor's forward bias
		# voltage.
		fig = figure.Figure()
		FigureCanvas(fig)
		axes = fig.add_axes((0.1, 0.3, 0.85, 0.65))
		axes.set_title("Channel %02d Voltage vs.\\@ Pull-Up Voltage" % self.channel.channel)
		#axes.set_xlabel("Applied Pull-Up Voltage (volts)")
		axes.set_ylabel("Observed Voltage (volts)")
		axes.scatter(self.vpul_ramp_x, self.vpul_ramp_y, marker = ".", color = "k", label = "Data")
		x = numpy.linspace(0, 15, 120)
		axes.plot(x, model(x), color = "b", label = "Expected: observed = applied - diode Vf")
		x = numpy.linspace(2 * self.vpul_trans_vf, 15, 120)
		axes.plot(x, poly(x), color = "r", alpha = 0.5, label = "Derived calibration model")
		axes.xaxis.set_major_locator(matplotlib.ticker.MultipleLocator(5))
		axes.xaxis.set_minor_locator(matplotlib.ticker.MultipleLocator(1))
		axes.yaxis.set_major_locator(matplotlib.ticker.MultipleLocator(5))
		axes.yaxis.set_minor_locator(matplotlib.ticker.MultipleLocator(1))
		axes.tick_params(which = "both")
		axes.grid(True, which = "both")
		axes.set_xlim((0, 15))
		axes.set_ylim((0, 15))

		axes = fig.add_axes((0.1, 0.1, 0.85, 0.15))
		axes.set_xlabel("Applied Pull-Up Voltage (volts)")
		axes.set_ylabel("Residual (volts)")
		axes.plot(self.vpul_ramp_x, self.vpul_ramp_y - self.round_v(model(self.vpul_ramp_x)), label = "Data w.r.t.\\@ Applied")
		axes.plot(self.vpul_ramp_x, poly(self.vpul_ramp_x) - self.vpul_ramp_y, color = "r", alpha = 0.5, label = "Cal.\\@ w.r.t.\\@ Data")
		axes.plot(self.vpul_ramp_x, poly(self.vpul_ramp_x) - self.round_v(poly(self.vpul_ramp_x)), alpha = 0.5, label = "Cal.\\@ w.r.t.\\@ Exepcted")
		axes.xaxis.set_major_locator(matplotlib.ticker.MultipleLocator(5))
		axes.xaxis.set_minor_locator(matplotlib.ticker.MultipleLocator(1))
		axes.tick_params(which = "both")
		axes.grid(True, which = "both")
		axes.set_xlim((0, 15))
		axes.set_ylim((-0.35, +0.15))
		fig.savefig("channel%02d_vpul_ramp.png" % self.channel.channel)


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
		R = self.vtst_measure_r(5)

		# disable channel
		self.channel.config = allpro88.PINCON.DISABLE

		failed = not (5400 * 0.8 <= R <= 5400. * 1.2)	# 5400 kOhm +/- 20%
		print("channel %d pull-down resistance:  %.0f Ohm%s" % (self.channel.channel, R, "" if not failed else "\t<-- FAILED"))


	def test_logicl(self):
		"""
		The TTL low driver is a 50 Ohm resistor to ground.  This
		test uses a VTST current ramp to test for this resistance.
		"""
		# enable VTST and logic low modes together.  measure
		# resistance to ground.  don't let current exceed 10 mA
		self.channel.config = allpro88.PINCON.VTST | allpro88.PINCON.LOGICL
		R1 = self.vtst_measure_r(10)

		# enable pull-up and logic low modes together.  set VPUL to
		# 25 V (calibrated) and measure voltage on pin.  the
		# pull-up output impedance is 2700 Ohm, the TTL low driver
		# is a 50 Ohm resistor to ground, so we should observe
		# 25 V / (2700 Ohm + 50 Ohm) * 50 Ohm = 0.45 V on the pin.
		self.channel.config = allpro88.PINCON.PULLUP | allpro88.PINCON.LOGICL
		self.programmer.vpul = allpro88.volt(22.0)
		self.programmer.load_dacs()
		V = self.measure_v()
		self.programmer.vpul = 0
		self.programmer.load_dacs()

		failed = False
		print("channel %d logic low V test:  %g V%s" % (self.channel.channel, V, "" if not failed else "\t<-- FAILED"))

		# disable channel
		self.channel.config = allpro88.PINCON.DISABLE

		failed = False
		print("channel %d logic low pull-down resistance:  %.0f Ohm%s" % (self.channel.channel, R1, "" if not failed else "\t<-- FAILED"))


	def test_vdac_ramp(self):
		"""
		Each channel has its own 8-bit DAC controlling a high
		current constant-voltage linear power supply.  This test
		ramps the DAC from minimum to maximum and measures the
		voltage at each setting.  This is used to compute a
		polynomial calibration curve for the VDAC circuit.
		Finally, the measured data is tested to confirm it agrees
		with the calibration model within an allowed tolerance.
		"""
		# configure for VDAC output.  enable the pull-down driver
		# (5.4 kOhm to ground) so the output sees a load, otherwise
		# the voltage drop across the final diode in the driver
		# circuit isn't measured properly.  at the maximum output
		# voltage, a bit less than 1/8 W is being dissipated by the
		# pull-down resistor, which hopefully is safe.  turn on the
		# bypass capacitor to reduce noise
		self.channel.vdac = 0
		self.programmer.load_dacs()
		self.channel.bypass = True
		self.channel.config = allpro88.PINCON.VDAC | allpro88.PINCON.PULLDN

		# run the DAC from 0 to 255 inclusively and measure the
		# output voltage
		self.vdac_ramp_x = numpy.arange(256)
		self.vdac_ramp_y = numpy.zeros(256)
		for dac in tqdm(self.vdac_ramp_x, desc = "VDAC"):
			self.channel.vdac = dac
			self.programmer.load_dacs()
			# let things settle to get a good measurement
			time.sleep(0.010)
			self.vdac_ramp_y[dac] = self.measure_v()

		# disable output
		self.channel.vdac = 0
		self.programmer.load_dacs()
		self.channel.bypass = False
		self.channel.config = allpro88.PINCON.DISABLE

		# report deviation from calibration model
		expected = self.round_v(numpy.fromiter((self.channel.vdac.cal(x, self.channel) for x in self.vdac_ramp_x), "double"))
		max_residual = abs(self.vdac_ramp_y[1:] - expected[1:]).max()
		rms_residual = ((self.vdac_ramp_y[1:] - expected[1:])**2.).mean()**0.5
		# allow 1 VTH DAC count of measurement error
		failed = max_residual > 0.12	# volts
		print("channel %d VDAC ramp max residual = %.3g V, RMS residual = %.3g V%s" % (self.channel.channel, max_residual, rms_residual, "" if not failed else "\t<-- FAILED"))

		# derive updated calibration model and report what its
		# accuracy would have been
		poly = numpy.polynomial.Polynomial.fit(self.vdac_ramp_x[12:], self.vdac_ramp_y[12:], 2, w = dacfitweights[12:]).convert()
		self.cal_data = {
			"poly": tuple(map(float, poly.coef)),
			"min": float(numpy.median(self.vdac_ramp_y[:5]))
		}
		def model(dac):
			return numpy.maximum(self.cal_data["min"], poly(dac))
		print("\tupdated calibration model:  max(%.3g, %s)" % (self.cal_data["min"], poly))
		expected = self.round_v(model(self.vdac_ramp_x))
		max_residual = abs(self.vdac_ramp_y[1:] - expected[1:]).max()
		rms_residual = ((self.vdac_ramp_y[1:] - expected[1:])**2.).mean()**0.5
		# allow 1 VTH DAC count of measurement error
		failed = max_residual > 0.12	# volts
		print("\tupdated model's max residual = %.3g V, RMS residual = %.3g V%s" % (max_residual, rms_residual, "" if not failed else "\t<-- FAILED"))

		# plot the results
		fig = figure.Figure()
		FigureCanvas(fig)
		axes = fig.add_axes((0.1, 0.3, 0.85, 0.65))
		axes.set_title("Channel %02d Voltage vs.\\@ DAC" % self.channel.channel)
		axes.set_ylabel("Voltage (volts)")
		axes.scatter(self.vdac_ramp_x, self.vdac_ramp_y, marker = ".", color = "k", label = "Data")
		axes.plot(self.vdac_ramp_x, model(self.vdac_ramp_x), label = "Calibration model")
		axes.xaxis.set_major_locator(matplotlib.ticker.MultipleLocator(32))
		axes.xaxis.set_minor_locator(matplotlib.ticker.MultipleLocator(4))
		axes.yaxis.set_major_locator(matplotlib.ticker.MultipleLocator(5))
		axes.yaxis.set_minor_locator(matplotlib.ticker.MultipleLocator(1))
		axes.tick_params(which = "both")
		axes.grid(True, which = "both")
		axes.set_xlim((0, 256))
		axes.set_ylim((0, 26))

		axes = fig.add_axes((0.1, 0.1, 0.85, 0.15))
		axes.set_xlabel("DAC Value (count)")
		axes.set_ylabel("Residual (volts)")
		axes.plot(self.vdac_ramp_x, model(self.vdac_ramp_x) - self.vdac_ramp_y, label = "Observed residual")
		axes.plot(self.vdac_ramp_x, model(self.vdac_ramp_x) - self.round_v(model(self.vdac_ramp_x)), alpha = 0.5, label = "Exepcted residual")
		axes.xaxis.set_major_locator(matplotlib.ticker.MultipleLocator(32))
		axes.xaxis.set_minor_locator(matplotlib.ticker.MultipleLocator(4))
		axes.tick_params(which = "both")
		axes.grid(True, which = "both")
		axes.set_xlim((0, 256))
		axes.set_ylim((-0.15, +0.15))
		fig.savefig("channel%02d_vdac_ramp.png" % self.channel.channel)


	def test_vtst(self):
		"""
		VTST is a variable constant-current/constant-voltage
		supply.

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
		idac = list(range(9, -1, -1))
		v = [self.measure_v() for self.programmer.itst in idac]
		R, Vec = scipy.stats.linregress(idac, v)[:2]
		R *= 1000.
		failed = not (0.4 * 0.8 <= Vec <= 0.4 * 1.2)	# 0.4 V +/- 20%
		print("channel %d VTST Vec: %.3g V%s" % (self.channel.channel, Vec, "" if not failed else "\t<-- FAILED"))
		failed = not (68. * 0.8 <= R <= 68 * 1.2)	# 68 Ohm +/- 20%
		print("channel %d VTST base pull-down resistance: %.3g Ohm%s" % (self.channel.channel, R, "" if not failed else "\t<-- FAILED"))

		# plot the results
		fig = figure.Figure()
		FigureCanvas(fig)
		axes = fig.gca()
		axes.set_title("Channel %02d VTST Base R" % self.channel.channel)
		axes.set_xlabel("I (milliamperes)")
		axes.set_ylabel("Voltage (volts)")
		axes.scatter(idac, v, marker = ".", color = "k")
		axes.xaxis.set_major_locator(matplotlib.ticker.MultipleLocator(5))
		axes.xaxis.set_minor_locator(matplotlib.ticker.MultipleLocator(1))
		axes.tick_params(which = "both")
		axes.grid(True, which = "both")
		#axes.set_xlim((0, 256))
		#axes.set_ylim((0, 26))
		fig.savefig("channel%02d_vtst_ramp.png" % self.channel.channel)

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


def parse_command_line():
	parser = argparse.ArgumentParser(
		description = "ALLPRO88 Self Test"
	)
	parser.add_argument("-c", "--channel", metavar = "number", type = int, choices = range(88), action = "append", help = "Test only this channel (integer in [0, 87] inclusively).  May be specified multiples times.  If not specified, all installed channels are tested in sequence.")
	parser.add_argument("--calibration-filename", metavar = "filename", default = "calibration.dat", help = "Set the name of the file from which to load (and, optionally, to which to write) the calibration model.  The programmer interface library's default is to search for and load a calibration file named \"allpro88_cal_XXXX.yml\" in the directories listed in the ALLPRO88_CAL_PATH environment variable, where \"XXXX\" is the programmer's serial number.  After constructing the calibration file, to use it as the default for the given unit it will need to be renamed accordingly and placed in the search path.")
	parser.add_argument("-w", "--write-calibration", action = "store_true", help = "Overwrite the calibration file with a new calibration model derived from the measurements made during the self test.")
	parser.add_argument("-p", "--power-supplies", action = "store_true", help = "Calibrate main power supplies.  This requires probing the primary DIN connector, which requires the socket module to be removed.  Because the pin decoupling capacitors are installed in the socket module, and because the socket module cannot be installed or removed while the power is turned on, when this option is enabled the pin driver tests that rely on the decoupling capacitors for stable voltage measurements will not give accurate results.  Fully calibrating the system, both main power supplies and pin drivers, requires two passes.  Do not attempt to re-install the socket module with the unit powered!")
	options = parser.parse_args()
	return options


options = parse_command_line()


try:
	with open(options.calibration_filename) as calfile:
		calibration = yaml.unsafe_load(calfile)
	assert type(calibration) is dict
except FileNotFoundError as e:
	print("warning:  %s" % str(e))
	print("intializing new calibration")
	# initialize with sensible default power supply calibration curves
	calibration = {
		"serial": None,
		"vadj": {
			"poly":	(0.5, 0.118)
		},
		"vpul": {
			"poly":	(0., 25.5 / 256),
			# the following are properties of the
			# pin-driver circuits that place the power
			# supply voltage onto a pin.  they are
			# averages of component properties across
			# all pin drivers to provide a typical (but
			# not pin specific) correction for the
			# calibration model.  they are measured by
			# the pin driver calibration routines.  for
			# now we set them to typical values for
			# these components.
			"diode_vf": 0.180,	# Schottky Vf
			"trans_vf": 0.550	# PNP E-B Vf
		},
		"vsr": {
			"poly":	(0., 25.5 / 256)
		},
		"vth": {
			"poly":	(0., 25.5 / 256)
		},
		"vtst": {
			"poly":	(0., 25.5 / 256)
		}
	}

with allpro88.allpro88(cal_data = calibration if calibration != {} else None) as programmer:
	# record serial number and timestamp
	calibration["serial"] = programmer.serial_number
	calibration["time"] = datetime.datetime.now(datetime.UTC).isoformat()

	# turn on power supplies
	programmer.pcr_enable = True

	# calibrate main power supplies.  these require an external
	# voltmeter, and user participation unless the meter can be read by
	# this script.  after these power supplies are calibrated, the unit
	# can self-calibrate all remaining circuits.
	if options.power_supplies:
		with hioki3801.hioki3801() as meter:
			pwr_sweep = power_supply_sweep(programmer, meter = meter)
		calibration.update({
			"vadj": {
				"poly":	tuple(map(float, pwr_sweep.vadj_model.coef))
			},
			"vpul": {
				# this is a model of the power supply's
				# output
				"poly":	tuple(map(float, pwr_sweep.vpul_model.coef)),
				# the following are properties of the
				# pin-driver circuits that place the power
				# supply voltage onto a pin.  they are
				# averages of component properties across
				# all pin drivers to provide a typical (but
				# not pin specific) correction for the
				# calibration model.  they are measured by
				# the pin driver calibration routines.  for
				# now we set them to typical values for
				# these components.
				"diode_vf": 0.180,	# Schottky Vf
				"trans_vf": 0.550	# PNP E-B Vf
			},
			"vsr": {
				"poly":	tuple(map(float, pwr_sweep.vsr_model.coef))
			},
			"vth": {
				"poly":	tuple(map(float, pwr_sweep.vth_model.coef))
			},
			"vtst": {
				"poly":	tuple(map(float, pwr_sweep.vtst_model.coef))
			}
		})
		# save what we've got so we can skip this step if any part
		# of what follows fails and we have to try again.
		if options.write_calibration:
			with open(options.calibration_filename, "w") as calfile:
				yaml.dump(calibration, calfile)
		# install calibration curves so that channel calibrations
		# are computed correctly
		programmer.set_calibration(calibration)

	# VADJ = max
	programmer.vadj = 255

	vpul_diode_vf = []
	vpul_trans_vf = []
	for channel in ((channel.channel for channel in programmer.channels_installed) if options.channel is None else options.channel):
		calibration_name = "channel%02d" % channel
		calibration[calibration_name] = {}

		test_suite = channel_driver_test_suite(programmer, programmer.channels[channel])
		print("channel %d --> pin driver group %d, DAC U%d, hybrid H%d, hybrid channel %d" % ((channel,) + programmer.channels[channel].physical))
		if programmer.socket_module is not None:
			try:
				print("channel %d --> DIP48 pin %d" % (channel, programmer.socket_module.pin_lookup("DIP48", channel)))
			except KeyError:
				print("channel %d --> DIP48 no connection" % channel)

		test_suite.test_logich()

		test_suite.test_vpul(calibration["vpul"]["diode_vf"])
		vpul_diode_vf.append(test_suite.vpul_diode_vf)
		vpul_trans_vf.append(test_suite.vpul_trans_vf)

		test_suite.test_vdac_ramp()
		calibration[calibration_name]["vdac"] = test_suite.cal_data

		test_suite.test_vtst()

		test_suite.test_pulldn()

		test_suite.test_logicl()

		print("\n")

	vpul_diode_vf = float(numpy.median(vpul_diode_vf))
	vpul_trans_vf = float(numpy.median(vpul_trans_vf))
	print("VPUL median reverse protection diode Vf:  %.3g V" % vpul_diode_vf)
	print("VPUL median drive transistor Vf:  %.3g V" % vpul_trans_vf)
	calibration["vpul"]["diode_vf"] = vpul_diode_vf
	calibration["vpul"]["trans_vf"] = vpul_trans_vf


if options.write_calibration:
	print("writing new calibration model to \"%s\"" % options.calibration_filename)
	with open(options.calibration_filename, "w") as calfile:
		yaml.dump(calibration, calfile)
