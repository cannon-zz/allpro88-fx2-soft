# Copyright (C) 2026  Kipp Cannon
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation; either version 3 of the License, or (at your
# option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General
# Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.


import functools
import io
import itertools
import math
import os
import tarfile
import yaml
import zipfile


import allpro88
import allpro88.devices
import allpro88.paths


def geomean(*vals):
	"""
	Return the geometric mean of the arguments.
	"""
	return math.exp(sum(math.log(val) for val in vals) / len(vals))


#
# =============================================================================
#
#                                   Metadata
#
# =============================================================================
#


#
# logic families (not neccessarily supported, just here to keep a list).
# See Texas Instruments, "Logic Guide", Application Note SDYU001AC, June
# 2015.
#


class logic_family:
	def __init__(self, description, Vcc_min, Vcc_max, Vih_min, Vil_max, Voh_min, Vol_max):
		if Vcc_min <= 0. or Vcc_max <= 0. or Vih_min <= 0. or Vil_max <= 0. or Voh_min <= 0. or Vol_max <= 0.:
			raise ValueError("require non-negative voltages")
		if Vcc_min > Vcc_max or Vih_min < Vil_max or Voh_min < Vol_max:
			raise ValueError("voltages out of order")
		self.description = description
		self.Vcc_min = Vcc_min
		self.Vcc_max = Vcc_max
		self.Vih_min = Vih_min
		self.Vil_max = Vil_max
		self.Voh_min = Voh_min
		self.Vol_max = Vol_max

# FIXME:  although some entries are from published specifications, many in
# the following table are an invention.  they have not been obtained from
# published specifications, and in some cases the limits of the operating
# supply voltages are known to be wrong.  at this time, the input and
# output threshold limit voltages are fixed for 5 V parts even where the
# part is said to have other valid operating voltages.  the logic tester
# code does not at this time have the ability to test parts at anything
# other than a fixed 5 V supply voltage, and how to encode the relationship
# between threshold voltages and supply voltage for parts that operate over
# a wide range of voltges will have to wait until I have a need for that
# feature and can see how it should work.  it's not clear to me that it
# matters:  how often is it necessary to test a failed part over a range of
# supply voltages to know that it has failed?

#               Vcc_min, Vcc_max, Vih_min, Vil_max, Voh_min, Vol_max
logic_families = {
	"CMOS":		logic_family("CMOS (1968)",
		5.0,     5.0,     2.0,     0.8,     2.4,     0.4),
	"C2MOS":	logic_family("Toshiba clocked CMOS (1973)",
		2.0,     8.0,     4.0,     1.0,     4.7,     0.1),
	"CMOS AC":	logic_family("advanced CMOS",
		3.0,     5.0,     3.5,     1.0,     4.7,     0.1),
	"CMOS ACT":	logic_family("advanced CMOS (TTL compatible)",
		5.0,     5.0,     2.0,     0.8,     4.7,     0.1),
	"CMOS AHC":	logic_family("advanced high speed CMOS",
		5.0,     5.0,     3.5,     1.5,     4.7,     0.1),
	"CMOS AHTC":	logic_family("advanced high speed CMOS (TTL compatible)",
		5.0,     5.0,     2.0,     0.8,     4.7,     0.1),
	"CMOS ABT":	logic_family("advanced bipolar CMOS (1991)",
		5.0,     5.0,     2.0,     0.8,     4.7,     0.1),
	"CMOS ALVC":	logic_family("advanced low-voltage CMOS",
		5.0,     5.0,     2.0,     0.8,     4.7,     0.1),
	"CMOS AUC":	logic_family("advanced ultra low voltage CMOS",
		5.0,     5.0,     2.0,     0.8,     4.7,     0.1),
	"CMOS AUP":	logic_family("advanced ultra low power CMOS",
		5.0,     5.0,     2.0,     0.8,     4.7,     0.1),
	"CMOS AVC":	logic_family("advanced very low voltage CMOS",
		5.0,     5.0,     2.0,     0.8,     4.7,     0.1),
	"CMOS BCT":	logic_family("bipolar CMOS (1986)",
		5.0,     5.0,     2.0,     0.8,     4.7,     0.1),
	"CMOS FCT":	logic_family("fast CMOS (1988)",
		5.0,     5.0,     2.0,     0.8,     4.7,     0.1),
	"CMOS HC":	logic_family("high speed CMOS",
		2.0,     5.0,     3.5,     1.0,     4.7,     0.1),
	"CMOS HCT":	logic_family("high speed CMOS (TTL compatible)",
		5.0,     5.0,     2.0,     0.8,     4.7,     0.1),
	"CMOS HCS":	logic_family("high speed CMOS (Schmitt trigger inputs)",
		5.0,     5.0,     2.0,     0.8,     4.7,     0.1),
	"CMOS LV-A":	logic_family("low voltage",
		5.0,     5.0,     2.0,     0.8,     4.7,     0.1),
	"CMOS LV-AT":	logic_family("low voltage (TTL compatible)",
		5.0,     5.0,     2.0,     0.8,     4.7,     0.1),
	"CMOS LVxT":	logic_family("low voltage translating logic",
		5.0,     5.0,     2.0,     0.8,     4.7,     0.1),
	"CMOS LVC":	logic_family("low voltage CMOS",
		5.0,     5.0,     2.0,     0.8,     4.7,     0.1),
	"CMOS LVT":	logic_family("low voltage CMOS",
		5.0,     5.0,     2.0,     0.8,     4.7,     0.1),
	"TTL":		logic_family("TTL (1966)",
		5.0,     5.0,     2.0,     0.8,     2.4,     0.4),
	"TTL ALS":	logic_family("advanced low-power Schottky (1980)",
		5.0,     5.0,     2.0,     0.8,     2.5,     0.5),
	"TTL AS":	logic_family("advanced Schottky (1982)",
		5.0,     5.0,     2.0,     0.8,     2.5,     0.5),
	"TTL F":	logic_family("fast Schottky (1978)",
		5.0,     5.0,     2.0,     0.8,     2.7,     0.5),
	"TTL H":	logic_family("high speed TTL",
		5.0,     5.0,     2.0,     0.8,     2.4,     0.4),
	"TTL L":	logic_family("low power TTL",
		5.0,     5.0,     2.0,     0.7,     2.4,     0.4),
	"TTL LS":	logic_family("low-power Schottky (1971)",
		5.0,     5.0,     2.0,     0.8,     2.7,     0.5),
	"TTL S":	logic_family("Schottky (1969)",
		5.0,     5.0,     2.0,     0.8,     2.7,     0.5),
}


#
# pin types
#


pin_types = {
	"V":	"supply voltage",
	"G":	"supply return",
	"X":	"no connection",
	"I":	"input",
	"O":	"output"
}


#
# =============================================================================
#
#                                  Logic Chip
#
# =============================================================================
#


class logic_chip:
	# compatible socket module
	socket_module = "AP88 PLCC"

	def __init__(self, name = None, description = None, socket_name = None, pinout_vector_table = None, progress_bar = None):
		"""
		name:  the name of the part without the logic family, e.g.,
		\"7400\".

		description:  brief human-readable description of the part.

		socket_name:  one of the valid socket names defined for
		self.socket_module, e.g., \"DIP14\".

		pinout_vector_table:  a sequence of the form

		(pinout, (vector, vector, ..., vector), pinout, (...), ...)

		progress_bar:  an optional tqdm compatible progress bar.
		at this time, only .reset() and .update() will be called.

		the pinouts and vectors are strings, all equal in length to
		the number of pins the socket socket_name has.  each
		character in a pinout string is a character selected from
		pin_types, and defines the function of that pin, in order.
		NOTE:  pin numbers are counted from 1, while character
		index in a Python string is counted from 0, so don't forget
		to add 1 to the string index when matching pin functions
		from the pinout string with pin numbers in the socket.
		each pinout string is followed by a sequence of test vector
		strings specifying pin states.  the socket channel drivers
		will be configured according to the first pinout, and the
		test vectors in the sequence that follows it applied one by
		one, first setting the states of input pins then testing
		the states of output pins.  the order in which input pins
		are set is undefined, so if some pins must change states
		before others then a sequence of test vectors must be
		provided to affect the input state changes in the required
		order.  when the vector sequence is complete, the channel
		drivers are configured according to the next pinout, the
		next sequence of test vectors applied in order, and so on
		until the entire sequence is exhausted.  at the end of a
		test vector sequence, the channel drivers are left in their
		final states.

		in each test vector, power supply and no-connection pins
		must be "-";  an input must be one of "0", "1" and will be
		driven low or high respectively;  an output must be one of
		"0" or "1" indicating that the part will drive it low or
		high, respectively, "X" indicating the part will leave it
		floating, or a "U" indicating that the part will drive it
		low or high (not floating) but which it will be is unknown
		(used for testing ROMs).

		the power and no-connection pins must be the same in all
		pinouts.  the part will not be power cycled when switched
		from one pinout configuration to the next, only the I/O pin
		channel drivers are reconfigured.

		parts with fixed inputs and outputs will have only a single
		pinout and test vector sequence.  parts whose inputs and
		outputs are configurable, for example bidirectional bus
		transceivers, can be tested by providing multiple pinouts.
		often more than one pinout is required for each
		configuration to safely sequence such parts between
		configruations.  it is essential that the final vector for
		each pinout leave the part in a state that is safe for the
		next poinout's channel driver configuration, and it might
		require more than one pinout change applied in a sequence
		to affect the reconfiguration safely.  recall that input
		pins have their states set in a random order.

		for example, consider the case of a bidirectional bus
		transceiver with tri-state I/Os.   because the order in
		which input pins are set cannot be controlled, when the
		first test vector is applied, it's not guaranteed that the
		direction and enable pins will be set before the ALLPRO88
		begins driving voltages onto what will be the "input" side
		of the part's data I/O pins.  depending on how the part
		behaves with its direction and enable select pins floating,
		this could lead to a situation in which both the part and
		the ALLPRO88 channel drivers are driving voltages onto the
		same pins leading to a short-circuit risk.  a sequence of
		pinout configurations can be used to initialize the part
		safely.  the part should begin in a disabled configuration,
		starting with a pinout in which the enable and direction
		select pins are inputs and set in the first test vector as
		needed to tri-state the bus I/O pins, which are all marked
		as outputs in the pinout and set to the "X" state in that
		first vector.  next a pinout corresponding to the part
		being configured for one direction or another is given in
		which the data I/O pins are now inputs or outputs as needed
		but for the first test vector of the new pinout the part
		remains disabled with the output pins still in the "X"
		state but now "0"/"1" input states given for the input pins
		--- since the part is stll disabled it is safe for the
		ALLPRO88 to drive those pins.  finally in the second test
		vector for the new pinout the part is enabled and the
		output states marked accordingly.  to change directionm, in
		the final vector of the sequence the part is again disabled
		and the outputs marked with "X".  that is followed by a new
		pinout and single test vector like the first one:  all I/O
		pins are marked as outputs, and the single test vector
		keeps the part disabled and requires all data I/O pins to
		be "X".  that leaves all I/O pin channel drivers disabled
		and the part also tri-stating its I/Os, making it safe to
		change the state of the direction select pin on the part
		without risking a short-circuit by both the ALLPRO88 and
		the part driving the same pins to incompatible voltages.
		"""
		#
		# part description from database
		#

		self.name = name
		self.description = description
		self.socket_name = socket_name
		self.pinout_vector_table = pinout_vector_table

		#
		# optional progress bar shown during test (some parts take
		# a while to test, and it's helpful to know that something
		# is happening)
		#

		self.progress_bar = progress_bar

		#
		# temporarily hold configuration information for the pinout
		# being tested
		#

		self.inputs = {}
		self.outputs = {}

		#
		# allow an empty part to be defined.  otherwise, if we
		# continue below all inputs must be valid
		#

		if name is None:
			return

		#
		# configuration validation
		#

		if not self.pinout_vector_table:
			raise ValueError("empty pinout_vector_table")
		if len(self.pinout_vector_table) & 1:
			raise ValueError("invalid pinout_vector_table")

		non_io_pins = self.non_io_pins(self.pinout_vector_table[0])
		for pinout, vectors in self.pinout_and_vectors:
			# check for invalid pin types, missing power
			# supply pins, or incompatible pinout
			if set(pinout) > set(pin_types):
				raise ValueError("unrecognized pin types %s in pinout" % ", ".join(set(pinout) - set(pin_types)))
			if "V" not in pinout:
				raise ValueError("no power supply pin (V) in pinout \"%s\"" % pinout)
			if "G" not in pinout:
				raise ValueError("no power supply return pin (G) in pinout \"%s\"" % pinout)
			if self.non_io_pins(pinout) != non_io_pins:
				raise ValueError("power supply and/or non-connected pins in wrong position in pinout \"%s\"" % pinout)

			# confirm consistency of vectors with pinout
			n = len(pinout)
			non_signal_pins = set(i for i, pin_type in enumerate(pinout, 1) if pin_type in ("V", "G", "X"))
			input_pins = set(i for i, pin_type in enumerate(pinout, 1) if pin_type == "I")
			output_pins = set(i for i, pin_type in enumerate(pinout, 1) if pin_type == "O")
			if non_signal_pins | input_pins | output_pins != set(range(1, n + 1)):
				# impossible
				raise RuntimeError
			for vector in vectors:
				if len(vector) != n:
					raise ValueError("incorrect vector length \"%s\":  require %d pins" % (vector, n))
				# strings indexed from 0, pins counted from 1
				if set(vector[i - 1] for i in non_signal_pins) != set("-") or \
				   set(vector[i - 1] for i in input_pins) > set("01") or \
				   set(vector[i - 1] for i in output_pins) > set("01X"):
					raise ValueError("vector \"%s\" invalid state for input, output, or non-signal pin in pinout \"%s\"" % (vector, pinout))


	@property
	def pinout_and_vectors(self):
		return itertools.batched(self.pinout_vector_table, 2)


	@staticmethod
	def non_io_pins(pinout):
		"""
		Replace all I/O pins in a pinout with "-".  Used to test if
		two pinouts have the same number of pins and if power and
		no-connection pins are in the same positions.
		"""
		for pin_type in set(pin_types) - {"V", "G", "X"}:
			pinout = pinout.replace(pin_type, "-")
		return pinout


	def to_yaml_string(self):
		return yaml.safe_dump((
			("format", 1),
			("name", self.name),
			("description", self.description),
			("socket_name", self.socket_name),
			("pinout_vector_table", self.pinout_vector_table),
		), sort_keys = False)


	@classmethod
	def from_yaml_string(cls, string):
		kwargs = dict(yaml.safe_load(string))
		fmt = kwargs.pop("format", None)
		if fmt != 1:
			# hmm.  that's odd ...
			raise RuntimeError
		return cls(**kwargs)


	def set_logic_family(self, logic_family_name):
		try:
			self.logic_family = logic_families[logic_family_name]
		except KeyError:
			raise ValueError("unknown logic family \"%s\"" % logic_family_name)


	@property
	def voltage(self):
		"""
		The geometric mean of the lowest and highest allowed supply
		voltages rounded to 1 digit to the right of the decimal.
		"""
		# FIXME:  hard-coded for 5 V parts until we can figure out
		# how threshold voltages are generically related to vcc
		assert self.logic_family.Vcc_min <= 5. <= self.logic_family.Vcc_max
		return 5.
		return round(geomean(self.logic_family.Vcc_min, self.logic_family.Vcc_max), 1)


	@property
	def voltage_maps(self):
		# define a voltage map using the 0th pinout
		# NOTE;  VPUL must be set.  the test code uses pull-up channel
		# driver for logic 1
		voltage_map = {"VPUL": self.voltage}
		for i, pin_type in enumerate(self.pinout_vector_table[0], 1):
			if pin_type == "V":
				voltage_map[i] = self.voltage
			elif pin_type == "G":
				voltage_map[i] = 0.
		return {"default": voltage_map}


	def config(self, programmer):
		self.programmer = programmer
		self.socket = programmer.socket_module.sockets[self.socket_name]
		if len(self.socket) != len(self.pinout_vector_table[0]):
			raise ValueError("socket %s has %d pins, this part's pinout has %d" % (self.socket_name, len(self.socket), len(self.pinout_vector_table[0])))
		# NOTE:  vth is not used, pin states are determined by
		# voltage measurements
		self.power = allpro88.devices.power(self.programmer, self.socket, self.voltage_maps)
		return self


	def __enter__(self):
		self.power.on()
		return self


	def __exit__(self, exc_type, exc_val, exc_tb):
		self.power.off()
		for channel in self.inputs.values():
			channel.config = allpro88.PINCON.DISABLE
		# done.  if an exception has occurred, continue processing
		return False


	def set_pinout(self, pinout):
		self.inputs = {}
		self.outputs = {}
		for i, pin_type in enumerate(pinout, 1):
			if pin_type in ("V", "G", "X"):
				# power or not connected
				continue
			elif pin_type == "I":
				# input
				self.inputs[i] = self.socket[i]
			elif pin_type == "O":
				# output
				self.outputs[i] = self.socket[i]
				self.outputs[i].config = allpro88.PINCON.DISABLE
			else:
				raise ValueError("invalid pinout \"%s\"" % pinout)
		return self


	def read_inputs(self, n = 3):
		"""
		Returns a dictionary containing the voltages measured on
		each of the input pins.  Confirms that the pull-up and
		pull-down channel drivers are setting the input states
		correctly, that the part does not have shorts on its input
		pins.
		"""
		voltages = dict((i, channel.measure_v(n)) for i, channel in self.inputs.items())
		self.power.reset_vth()
		return voltages


	def read_outputs(self, n = 3):
		"""
		Returns two dictionaries containing the voltages measured
		on each of the output pins with, respectively, pull-up and
		pull-down resistors applied.  By measuring the voltage with
		pull-up and pull-down resistors applied the ability of the
		part's output to drive a load can be tested, to some
		extent, but also floating output pins can be detected.
		"""
		# FIXME:  instead of applying pull-up and pull-down
		# resistors to each output individually and then leaving
		# them floating when not being probed, it might be a better
		# test to apply pull-up resistors to all outputs
		# simultaneously, measure their voltages, then apply
		# pull-down resistors to all outputs simultaneously and
		# measure their voltages in case loading all outputs
		# simultaneously affects the behaviour
		voltages_pull_up = {}
		voltages_pull_dn = {}
		for i, channel in self.outputs.items():
			channel.config = allpro88.PINCON.PULLUP
			voltages_pull_up[i] = channel.measure_v(n)
			channel.config = allpro88.PINCON.PULLDN
			voltages_pull_dn[i] = channel.measure_v(n)
			channel.config = allpro88.PINCON.DISABLE
		self.power.reset_vth()
		return voltages_pull_up, voltages_pull_dn


	def apply_vector_sequence(self, vectors):
		# FIXME:  the plan is to progressively increase the input_0
		# voltage and decrease the input_1 voltage until the part
		# fails a run-through of its test vectors, to measure the
		# highest allowed logic-low and lowest allowed logic high
		# input voltages.

		# NOTE:  PULLDN driver has too much resistance to ground to
		# pull pins of some TLL logic families to a logic low
		# state.  plain TTL, F, and S series have been obsered to
		# fail
		input_0 = allpro88.PINCON.LOGICL
		input_1 = allpro88.PINCON.PULLUP

		failed_vector_indexes = []
		state_0_highest = {}
		state_1_lowest = {}

		for vector_index, vector in enumerate(vectors):
			state = ["-"] * len(vector)

			# set input pin states.  remember:  pins are counted
			# from 1, strings are indexed from 0
			for pin_number, channel in self.inputs.items():
				if vector[pin_number - 1] == "0":
					channel.config = input_0
				elif vector[pin_number - 1] == "1":
					channel.config = input_1
				else:
					raise ValueError("invalid state \"%s\" for input pin %d in vector \"%s\"" % (state[pin_number - 1], pin_number, vector))

			# read-back the input voltages.  helps diagnose the
			# cause of a failure by testing for shorts on input
			# pins.
			for pin_number, voltage in self.read_inputs().items():
				state[pin_number - 1] = "0" if voltage <= self.logic_family.Vil_max else "1" if voltage >= self.logic_family.Vih_min else "?"

			# read output states
			voltages_pull_up, voltages_pull_dn = self.read_outputs()

			for pin_number in self.outputs:
				voltage_pull_up = voltages_pull_up[pin_number]
				voltage_pull_dn = voltages_pull_dn[pin_number]

				state_is_0 = voltage_pull_up <= self.logic_family.Vol_max
				state_is_1 = voltage_pull_dn >= self.logic_family.Voh_min
				state_is_X = voltage_pull_dn <= self.logic_family.Vol_max and voltage_pull_up >= self.logic_family.Voh_min

				state[pin_number - 1] = "?" if sum((state_is_0, state_is_1, state_is_X)) != 1 else "0" if state_is_0 else "1" if state_is_1 else "X"

				if vector[pin_number - 1] == "0" or (vector[pin_number - 1] == "U" and state_is_0):
					state_0_highest[pin_number] = max(state_0_highest.get(pin_number, 0.0), voltage_pull_up)
				elif vector[pin_number - 1] == "1" or (vector[pin_number - 1] == "U" and state_is_1):
					state_1_lowest[pin_number] = min(state_1_lowest.get(pin_number, math.inf), voltage_pull_dn)
				elif vector[pin_number - 1] != "X":
					raise ValueError("invalid output state \"%s\" for pin %d in vector \"%s\"" % (vector[pin_number - 1], pin_number, vector))

				# if the expected state was "U", and we did
				# observe a definite logic state, then
				# replace that state with the "U" code so
				# the test vector comparison passes
				if vector[pin_number - 1] == "U" and state[pin_number - 1] in "01":
					state[pin_number - 1] = "U"

			state = "".join(state)
			if state != vector:
				failed_vector_indexes.append((vector_index, vector, state))

			if self.progress_bar is not None:
				self.progress_bar.update()

		return failed_vector_indexes, state_0_highest, state_1_lowest


	def test(self):
		results = {}
		state_0_highest = {}
		state_1_lowest = {}
		if self.progress_bar is not None:
			self.progress_bar.reset(sum(len(vectors) for pinout, vectors in self.pinout_and_vectors))
		for pinout, vectors in self.pinout_and_vectors:
			self.set_pinout(pinout)
			failed_vector_indexes, this_state_0_highest, this_state_1_lowest = self.apply_vector_sequence(vectors)
			results[pinout] = failed_vector_indexes
			for pin_number, voltage in this_state_0_highest.items():
				state_0_highest[pin_number] = max(state_0_highest.get(pin_number, 0.0), voltage)
			for pin_number, voltage in this_state_1_lowest.items():
				state_1_lowest[pin_number] = min(state_1_lowest.get(pin_number, math.inf), voltage)
		return results, state_0_highest, state_1_lowest


#
# =============================================================================
#
#                                   Database
#
# =============================================================================
#


class database:
	filename = os.path.join(allpro88.paths.ALLPRO88_DATA_PATH, "logic_tester_database.tar.gz")

	def __init__(self, filename = None):
		"""
		Access the parts database.  If filename is None (the
		default) then the default database file

		%s

		is used.
		""" % type(self).filename
		if filename is not None:
			self.filename = filename
		self.contents = tarfile.open(self.filename)

	def get_part(self, name):
		"""
		Return a logic_chip instance for the part named name.
		"""
		return logic_chip.from_yaml_string(self.contents.extractfile(os.path.join("logic_tester_database", "%s.yml" % name)))

	@property
	def parts(self):
		"""
		Generator yielding sequence of all part names in the
		database.
		"""
		for name in self.contents.getnames():
			if not name.endswith(".yml"):
				continue
			path, name = os.path.split(name)
			name, _ = os.path.splitext(name)
			yield name


#
# =============================================================================
#
#                    Circuit Cellar IC Tester Compatibility
#
# =============================================================================
#


class circuit_cellar_logic_chip:
	"""
	Code to work with the test vector database supplied with the
	Circuit Cellar IC Tester by Seven A. Ciarcia published in the
	November and December 1987 issues of BYTE Magazine.  At the time of
	writing, the part database is available in a Google Drive owned by
	circuitcellar.com

	https://drive.google.com/open?id=1xeU29a9ZSZfGGtYFe625S9jttg_Ra2Oy

	The part test vector files are in the "ictpc.zip" file in the
	zzzz-BYTE/BYTE-Nov-Dec-1987.zip archive.

	This class represents one entry in the Circuit Cellar IC Tester
	part database.

	NOTE:  online sources I have read claim the database contained over
	600 parts, but the file downloaded from the source above contains
	only 238, a count which includes 20 parts that are duplicates of
	others.  There might be another version out there.
	"""
	def __init__(self):
		# name of the part
		self.name = None
		# brief human-readable description
		self.description = None
		# if this is a clone of another part, the name of that part
		self.clone = None
		# number of pins
		self.socket_size = None
		# pin number for the power supply return pin
		self.pin_G = None
		# pin number for the power supply pin
		self.pin_V = None
		# mapping character position to pin type
		self.pin_types = {}
		# mapping character position to pin number
		self.pin_numbers = {}
		# sequence of (stimulus, response) pairs.  each stimulus
		# and response is a dictionary mapping pin number to state.
		self.vectors = []

		# other internal data not from the database
		self.progress_bar = None

	@classmethod
	def from_tst(cls, fobj):
		"""
		Generator to parse the "test vector definition modules" in
		a .TST file into a sequence of circuit_cellar_logic_chip
		objects.
		"""
		self = cls()
		stimulus = {}
		response = {}
		for line in fobj:
			# remove comment text
			i = line.find("*")
			if i >= 0:
				comment = line[i + 1:]
				comment = comment.strip()
				line = line[:i]
			else:
				comment = None

			# remove leading and trailing whitespace and MSDOS
			# CTRL-Z EOF mark
			line = line.strip().strip(chr(0x1a))

			# if blank, ignore
			if not line:
				continue

			# select command

			# part name.  must be first command.  name is
			# everything after the command minus any comments
			# and minus leading and trailing whitespace
			if line[0] == "#":
				assert self.name is None
				self.name = line[1:].strip()
				# assume the comment text on this line, if
				# present, is the part description
				self.description = comment
				continue
			assert self.name is not None

			# equivalent part
			if line[0] == "C":
				self.clone = line[1:].strip()
				continue

			if self.clone is None:
				# socket and power pins.  must be second
				# command
				if line[0] == "S":
					assert self.socket_size is None
					self.socket_size, self.pin_G, self.pin_V = map(int, line.split()[1:])
					assert self.socket_size > 1 and not (self.socket_size & 1)
					assert 1 <= self.pin_G <= self.socket_size and 1 <= self.pin_V <= self.socket_size
					continue
				assert self.socket_size is not None

				# pin functions.  must be third command.
				# position of pin type character sets the
				# column in which to find the pin number
				# and pin state in subsequent lines
				if line[0] == "F":
					assert not self.pin_types
					for i, pin_type in enumerate(line[1:], 1):
						if pin_type in "IOT":
							self.pin_types[i] = pin_type
						elif pin_type.isspace():
							continue
						else:
							assert False
					assert len(self.pin_types) + 2 <= self.socket_size
					continue
				assert self.pin_types

				# pin numbers.  must be fourth column.  a
				# pin number is a 1 or 2 digit integer, one
				# of whose digits falls in the column for
				# that pin
				if line[0] == "P":
					assert not self.pin_numbers
					for i in self.pin_types:
						self.pin_numbers[i] = int(line[max(1, i - 1): i + 2])
					continue
				assert self.pin_numbers

				# stimulus & response pairs.  any number of
				# these, but must come in pairs in that
				# order.  pin states that are blank are
				# carried over from whatever line set the
				# state previously.
				if line[0] == "I":
					count = 0
					for i, pin_number in self.pin_numbers.items():
						if i < len(line) and line[i] in "01":
							stimulus[pin_number] = int(line[i])
							count += 1
					assert count == len(line[1:].split())
					# make sure all pins have states
					# set
					assert len(stimulus) == len(self.pin_types)
					continue
				if line[0] == "R":
					response = dict(stimulus)
					count = 0
					for i, pin_number in self.pin_numbers.items():
						if i < len(line) and line[i] in "01X":
							response[pin_number] = line[i] if line[i] == "X" else int(line[i])
							count += 1
					assert count == len(line[1:].split())
					self.vectors.append((dict(stimulus), dict(response)))
					continue

			# end of part.  yeild and reset for next part
			if line[0] == "E":
				yield self
				self = cls()
				stimulus = {}
				response = {}
				continue

			# no other character is valid
			assert False

	@property
	def socket_name(self):
		return "DIP%d" % self.socket_size

	@property
	def pinout(self):
		"""
		Return a pinout specification string compatible with the
		pinout strings used by logic_chip.
		"""
		# FIXME:  circuit cellar definitions include a "T" pin type
		# for "tri-state", which are used for pins that can be
		# inputs or outputs
		pins = ["X"] * self.socket_size
		pins[self.pin_G - 1] = "G"
		pins[self.pin_V - 1] = "V"
		for i, pin_number in self.pin_numbers.items():
			pins[pin_number - 1] = self.pin_types[i]
		return "".join(pins)

	def set_logic_family(self, logic_family_name):
		# Circuit Cellar IC Tester is for 5 V parts only
		assert logic_family_name == "TTL LS"

		try:
			self.logic_family = logic_families[logic_family_name]
		except KeyError:
			raise ValueError("unknown logic family \"%s\"" % logic_family_name)

	@property
	def voltage(self):
		assert self.logic_family.Vcc_min <= 5. <= self.logic_family.Vcc_max
		return 5.

	@property
	def vth(self):
		return round(geomean(self.logic_family.Vih_min, self.logic_family.Vil_max), 1)

	@property
	def voltage_maps(self):
		# NOTE;  VPUL must be set.  the test code uses pull-up
		# channel driver for logic 1
		return {
			"default": {
				"VPUL": self.voltage,
				self.pin_G: 0.,
				self.pin_V: self.voltage
			}
		}

	def config(self, programmer):
		self.programmer = programmer
		self.socket = programmer.socket_module.sockets[self.socket_name]
		self.power = allpro88.devices.power(self.programmer, self.socket, self.voltage_maps, vth = self.vth)
		return self

	def __enter__(self):
		self.power.on()
		return self

	def __exit__(self, exc_type, exc_val, exc_tb):
		self.power.off()
		for channel in self.socket.values():
			channel.config = allpro88.PINCON.DISABLE
		# done.  if an exception has occurred, continue processing
		return False

	def test(self):
		"""
		Software emulation of the stimulus-response circuit in
		Figure 1 of Part I of the Circuit Cellar IC Tester
		description in BYTE Magazine, November 1987.

		Returns None on success, or if the part fails returns the
		tuple

		(index, stimulus, expected_response, observed_response)

		where index is the (stimulus, response) pair that failed
		counted from 0.
		"""
		# NOTE:  PULLDN driver has too much resistance to ground to
		# pull pins of some TLL logic families to a logic low
		# state.  plain TTL, F, and S series have been obsered to
		# fail.  using the TTL low driver, with only 50 Ohm to
		# ground, could damage parts when applied to active-high
		# output pins.  for now, only CMOS and low-power TTL parts
		# (L, LS, etc.) will work
		input_0 = allpro88.PINCON.PULLDN
		input_1 = allpro88.PINCON.PULLUP

		if self.progress_bar is not None:
			self.progress_bar.reset(len(self.vectors))

		for i, (stimulus, expected_response) in enumerate(self.vectors):
			# apply the stimulus vector to the pins of the
			# part.  all pins are driven, including the part's
			# output pins, but via pull-up and pull-down
			# channel drivers, so the part's input pins should
			# take on logic high and low voltages while the
			# part's output pins overpower the pull-up and
			# pull-down resistors and decide the voltages.
			for pin, state in stimulus.items():
				self.socket[pin].config = input_1 if state else input_0

			# read the state of each pin of the stimulus.  the
			# channel drivers for the pins whose states are
			# found to not agree with the stimulus vector are
			# switched to match the measured state.
			observed_response = {}
			for pin in stimulus:
				observed_response[pin] = state = bool(self.socket[pin])
				if state != stimulus[pin]:
					self.socket[pin].config = input_1 if state else input_0

			# compare observed to expected response
			if observed_response != expected_response:
				for pin in stimulus:
					self.socket[pin].config = allpro88.PINCON.DISABLE
				return i, stimulus, expected_response, observed_response

			if self.progress_bar is not None:
				self.progress_bar.update()

		return None


class circuit_cellar_database:
	"""
	Interface allowing retrieval of individual parts from the Circuit
	Cellar IC Tester parts database.  To use this, find and download
	the "ictpc.zip" file and place it in %s.
	""" % allpro88.paths.ALLPRO88_DATA_PATH

	filename = os.path.join(allpro88.paths.ALLPRO88_DATA_PATH, "ictpc.zip")

	def __init__(self, filename = None):
		"""
		Access the parts database.  If filename is None (the
		default) then the default database file

		%s

		is used.
		""" % type(self).filename
		if filename is not None:
			self.filename = filename
		self.contents = {}
		archive = zipfile.ZipFile(self.filename)
		for filename in archive.namelist():
			if not filename.endswith(".TST"):
				continue
			self.contents.update((part.name, part) for part in circuit_cellar_logic_chip.from_tst(io.TextIOWrapper(archive.open(filename))))

	def get_part(self, name):
		"""
		Return a circuit_cellar_logic_chip instance for the part
		named name.
		"""
		part = self.contents[name]
		while part.clone:
			part = self.contents[part.clone]
		return part

	@property
	def parts(self):
		"""
		Generator yielding sequence of all part names in the
		database.
		"""
		return self.contents.keys()
