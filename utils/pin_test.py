import allpro88
import scipy.stats
import sys
import time
from tqdm import tqdm


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

			for i in range(10):
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
			expected = -0.54392 + (vdac * 0.100723) + (vdac**2. * 0.000000000497)
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

		# assume 10 mA is required for the VTST gate drive circuit
		vtst_current = 10

		# set VTST voltage limit to max, and start with current
		# limit set to 0
		self.programmer.vtst = 255
		# we seem to need to warm it up a bit ... ?
		self.programmer.itst = vtst_current
		time.sleep(0.1)

		# enable VTST and pull-down modes together
		self.channel.config = allpro88.PINCON.VTST | allpro88.PINCON.PULLDN

		# ramp current, taking voltage readings.  shouldn't be
		# possible to go above 5 mA so don't try
		current = list(range(5))
		voltage = []
		for i in current:
			self.programmer.itst = vtst_current + i
			time.sleep(0.05)
			voltage.append(self.channel.measure_v())

		# turn off VTST and disable channel
		self.channel.config = allpro88.PINCON.DISABLE
		self.programmer.vtst = 0
		self.programmer.itst = 0

		# report resistance
		R = scipy.stats.linregress(current, voltage)[0] * 1000.
		failed = R < 5000.
		print("channel %d pull-down resistance:  %.0f Ohm%s" % (self.channel.channel, R, "" if not failed else "\t<-- FAILED"))


	def test_vdac_ramp(self):
		"""
		Each channel has its own 8-bit DAC controlling a high
		current constant-voltage linear power supply.  This test
		ramps the DAC from minimum to maximum and confirms the
		voltage measured on the channel is within allowed
		tolerance.

		Partial, weak, shorts to ground often do not cause this
		test to fail because the power supply can deliver enough
		current to overcome the short.  Failure of this test for a
		group of 8 channels likely indicates failure of the bus
		interface circuitry.
		"""
		self.channel.config = allpro88.PINCON.VDAC
		max_residual = 0.
		rms_residual = 0.
		for vdac in range(256):
			self.channel.vdac = vdac
			self.programmer.load_dacs()
			expected = max(0., -0.5 + 0.1 * vdac)
			measured = self.channel.measure_v()
			residual = abs(measured - expected)
			if residual > max_residual:
				max_residual = residual
			rms_residual += residual**2.
		rms_residual = rms_residual**0.5 / 256.
		failed = rms_residual > 0.020
		print("channel %d VDAC ramp max residual = %.3g V, RMS residual = %.3g V%s" % (self.channel.channel, max_residual, rms_residual, "" if not failed else "\t<-- FAILED"))
		self.channel.vdac = 0
		self.programmer.load_dacs()
		self.channel.config = allpro88.PINCON.DISABLE


	def test_vtst(self):
		"""
		VTST is a variable constant-current/constant-voltage supply
		used either as a current source or as a probe to test for
		the presence of a part.

		The VTST drive output is delivered to the pin via a FET
		whose gate, when the VTST output is disabled, is held in
		the off state by the VTST voltage itself.  The FET's gate
		is pulled towards ground by an NPN transistor when the VTST
		output is enabled, but the voltage difference between the
		gate and the drain cannot exceed about 12 V, so for high
		VTST voltages a limiting circuit is needed to prevent
		damage to the output transistor.  This circuit consists of
		a 1 kOHm resistor between VTST and the gate, followed by a
		current limiting circuit set to approximately 10 mA so that
		when the VTST output is enabled never more than about 10 V
		(the voltage drop across the 1 kOhm resistor when 10 mA
		flows through it) is between the gate and the VTST source
		voltage.  This gate drive circuitry is in parallel with the
		pin being driven by the VTST output, and must be accounted
		for when using the VTST feature to check for the presence
		of a part.  This circuitry looks like a 1 kOhm resistor to
		ground up to about 10 V, after which it looks like a
		constant current 10 mA load.

		This test measures the properties of the gate drive
		circuitry, measuring the resistance to ground and the
		constant current limit by varying the VTST driving voltage
		and current limit DACs, and measuring the actual voltage
		that appears on the output.

		Unfortunately, even though the gate voltage limiting
		circuit interacts with measurements of the pin made using
		this feature, the circuit's properties are not precisely
		defined.  The characteristics of the circuit vary from
		channel to channel, and change noticably with temperatures
		as the programmer warms up.  It is recommended that the
		results of this test not be taken too seriously until the
		programmer has been allowed a 20 min or longer warm up
		period.
		"""
		self.channel.config = allpro88.PINCON.VTST

		# measure the resistance to ground in the gate drive
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
		R = scipy.stats.linregress(idac, [self.channel.measure_v() for self.programmer.itst in idac])[0] * 1000.
		self.programmer.itst = 0	# reset to 0
		print("channel %d VTST gate drive resistance: %.3g Ohm" % (self.channel.channel, R))

		# measure the current limit threshold in the gate drive
		# circuit by setting the drive voltage to max and seeing
		# what VTST current limit allows us to achieve that voltage

		self.programmer.vtst = 255
		for current_limit in range(256):
			self.programmer.itst = current_limit
			time.sleep(0.05)
			if self.channel.measure_v() > 20.:
				break
		failed = current_limit > 12
		print("channel %d VTST gate drive current limit: %.3g mA%s" % (self.channel.channel, current_limit, "" if not failed else "\t<-- FAILED"))

		self.programmer.vtst = 0
		self.programmer.itst = 0
		self.channel.config = allpro88.PINCON.DISABLE


with allpro88.allpro88() as programmer:
	print("system ID = 0x%X\nsocket module = %s" % (programmer.system_id, programmer.socket_module.name if programmer.socket_module else "not detected"))

	# turn on power supplies
	programmer.pcr_enable = True

	# VADJ = max
	programmer.vadj = 255

	for channel in range(48):
		test_suite = channel_driver_test_suite(programmer, programmer.channel[channel])
		print("channel %d --> pin driver group %d, DAC U%d, hybrid H%d, hybrid channel %d" % (channel, channel // 8, channel % 8 + 1, (channel % 8) // 2 + 1, (channel % 8) % 2))
		try:
			print("channel %d --> DIP48 pin %d" % (channel, programmer.socket_module.channel_lookup("DIP48", channel)))
		except KeyError:
			print("channel %d --> DIP48 no connection" % channel)

		test_suite.test_logich()

		test_suite.test_vpul_ramp()

		test_suite.test_vdac_ramp()

		test_suite.test_vtst()

		test_suite.test_pulldn()

		print("\n")

	# context manager turns off all power supplies, we don't have to do
	# that here.
