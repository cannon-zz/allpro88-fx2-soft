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
import itertools
import math
import os
import tarfile
import yaml


import allpro88
import allpro88.devices
import allpro88.paths


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
		2.0,     8.0,     4.0,     1.0,     4.9,     0.1),
	"CMOS AC":	logic_family("advanced CMOS",
		3.0,     5.0,     3.5,     1.0,     4.9,     0.1),
	"CMOS ACT":	logic_family("advanced CMOS (TTL compatible)",
		5.0,     5.0,     2.0,     0.8,     4.9,     0.1),
	"CMOS AHC":	logic_family("advanced high speed CMOS",
		5.0,     5.0,     3.5,     1.5,     4.9,     0.1),
	"CMOS AHTC":	logic_family("advanced high speed CMOS (TTL compatible)",
		5.0,     5.0,     2.0,     0.8,     4.9,     0.1),
	"CMOS ABT":	logic_family("advanced bipolar CMOS (1991)",
		5.0,     5.0,     2.0,     0.8,     4.9,     0.1),
	"CMOS ALVC":	logic_family("advanced low-voltage CMOS",
		5.0,     5.0,     2.0,     0.8,     4.9,     0.1),
	"CMOS AUC":	logic_family("advanced ultra low voltage CMOS",
		5.0,     5.0,     2.0,     0.8,     4.9,     0.1),
	"CMOS AUP":	logic_family("advanced ultra low power CMOS",
		5.0,     5.0,     2.0,     0.8,     4.9,     0.1),
	"CMOS AVC":	logic_family("advanced very low voltage CMOS",
		5.0,     5.0,     2.0,     0.8,     4.9,     0.1),
	"CMOS BCT":	logic_family("bipolar CMOS (1986)",
		5.0,     5.0,     2.0,     0.8,     4.9,     0.1),
	"CMOS FCT":	logic_family("fast CMOS (1988)",
		5.0,     5.0,     2.0,     0.8,     4.9,     0.1),
	"CMOS HC":	logic_family("high speed CMOS",
		2.0,     5.0,     3.5,     1.0,     4.9,     0.1),
	"CMOS HCT":	logic_family("high speed CMOS (TTL compatible)",
		5.0,     5.0,     2.0,     0.8,     4.9,     0.1),
	"CMOS HCS":	logic_family("high speed CMOS (Schmitt trigger inputs)",
		5.0,     5.0,     2.0,     0.8,     4.9,     0.1),
	"CMOS LV-A":	logic_family("low voltage",
		5.0,     5.0,     2.0,     0.8,     4.9,     0.1),
	"CMOS LV-AT":	logic_family("low voltage (TTL compatible)",
		5.0,     5.0,     2.0,     0.8,     4.9,     0.1),
	"CMOS LVxT":	logic_family("low voltage translating logic",
		5.0,     5.0,     2.0,     0.8,     4.9,     0.1),
	"CMOS LVC":	logic_family("low voltage CMOS",
		5.0,     5.0,     2.0,     0.8,     4.9,     0.1),
	"CMOS LVT":	logic_family("low voltage CMOS",
		5.0,     5.0,     2.0,     0.8,     4.9,     0.1),
	"TTL":		logic_family("TTL (1966)",
		5.0,     5.0,     2.0,     0.8,     2.4,     0.4),
	"TTL ALS":	logic_family("advanced low-power Schottky (1980)",
		5.0,     5.0,     2.0,     0.8,     2.5,     0.5),
	"TTL AS":	logic_family("advanced Schottky (1982)",
		5.0,     5.0,     2.0,     0.8,     2.7,     0.5),
	"TTL F":	logic_family("fast Schottky (1978)",
		5.0,     5.0,     2.0,     0.8,     2.7,     0.5),
	"TTL H":	logic_family("high speed TTL",
		5.0,     5.0,     2.0,     0.8,     2.7,     0.5),
	"TTL L":	logic_family("low power TTL",
		5.0,     5.0,     2.0,     0.8,     2.7,     0.5),
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
		name:  the name of the part, e.g., \"74LS00\".

		description:  brief human-readable description of the part.

		socket_name:  one of the valid socket names defined for
		self.socket_module.

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
		"0", "1" or "X" indicating that the part will drive it low
		or high or leave it floating, respectively.

		the power and no-connection pins must be the same in all
		pinouts.  the part will not be power cycled when switched
		from one pinout configuration to the next, only the I/O pin
		channel drivers are reconfigured.

		parts with fixed inputs and outputs will have only a single
		pintout and test vector sequence.  parts whose inputs and
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
			pass
		return cls(**kwargs)


	def set_logic_family(self, logic_family_name):
		try:
			self.logic_family = logic_families[logic_family_name]
		except KeyError:
			raise ValueError("unknown logic family \"%s\"" % logic_family_name)

		# define a voltage map using the 0th pinout
		# FIXME:  code only works with 5 V logic
		assert self.voltage == 5.0, self.voltage
		self.voltage_maps = {"default": {"VPUL": self.voltage}}
		for i, pin_type in enumerate(self.pinout_vector_table[0], 1):
			if pin_type == "V":
				self.voltage_maps["default"][i] = self.voltage
			elif pin_type == "G":
				self.voltage_maps["default"][i] = 0.


	@property
	def voltage(self):
		return round(math.exp(0.5 * (math.log(self.logic_family.Vcc_min) + math.log(self.logic_family.Vcc_max))), 1)


	def config(self, programmer):
		self.programmer = programmer
		self.socket = programmer.socket_module.sockets[self.socket_name]
		if len(self.socket) != len(self.pinout_vector_table[0]):
			raise ValueError("socket %s has %d pins, this part's pinout has %d" % (self.socket_name, len(self.socket), len(self.pinout_vector_table[0])))
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
		# FIXME:  temporarily hard-coded for TTL parts
		# FIXME:  the plan is to progressively increase the input_0
		# voltage and decrease the input_1 voltage until the part
		# fails a run-through of its test vectors, to measure the
		# highest allowed logic-low and lowest allowed logic high
		# input voltages.
		input_0 = allpro88.PINCON.LOGICL
		input_1 = allpro88.PINCON.LOGICH

		failed_vector_indexes = []
		state_0_highest = {}
		state_1_lowest = {}

		for vector_index, vector in enumerate(vectors):
			state = ["-"] * len(vector)

			# remember:  pins are counted from 1, strings are
			# indexed from 0
			for pin_number, channel in self.inputs.items():
				state[pin_number - 1] = vector[pin_number - 1]
				if state[pin_number - 1] == "0":
					channel.config = input_0
				elif state[pin_number - 1] == "1":
					channel.config = input_1
				else:
					raise ValueError("invalid state \"%s\" for input pin %d in vector \"%s\"" % (state[pin_number - 1], pin_number, vector))

			voltages_pull_up, voltages_pull_dn = self.read_outputs()

			for pin_number in self.outputs:
				voltage_pull_up = voltages_pull_up[pin_number]
				voltage_pull_dn = voltages_pull_dn[pin_number]

				state_is_0 = voltage_pull_up <= self.logic_family.Vol_max
				state_is_1 = voltage_pull_dn >= self.logic_family.Voh_min
				state_is_X = voltage_pull_dn <= self.logic_family.Vol_max and voltage_pull_up >= self.logic_family.Voh_min

				state[pin_number - 1] = "?" if sum((state_is_0, state_is_1, state_is_X)) != 1 else "0" if state_is_0 else "1" if state_is_1 else "X"

				if vector[pin_number - 1] == "0":
					state_0_highest[pin_number] = max(state_0_highest.get(pin_number, 0.0), voltage_pull_up)
				elif vector[pin_number - 1] == "1":
					state_1_lowest[pin_number] = min(state_1_lowest.get(pin_number, math.inf), voltage_pull_dn)
				elif vector[pin_number - 1] != "X":
					raise ValueError("invalid output state \"%s\" for pin %d in vector \"%s\"" % (vector[pin_number - 1], pin_number, vector))

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
		if filename is not None:
			self.filename = filename
		self.contents = tarfile.open(self.filename)

	def get_part(self, name):
		return logic_chip.from_yaml_string(self.contents.extractfile(os.path.join("logic_tester_database", "%s.yml" % name)))

	@property
	def parts(self):
		for name in self.contents.getnames():
			if not name.endswith(".yml"):
				continue
			path, name = os.path.split(name)
			name, _ = os.path.splitext(name)
			yield name
