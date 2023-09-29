import sys
from tqdm import tqdm
from . import allpro88
from . import devices


class D_flip_flop(object):
	# FIXME:  this is hard-coded for TTL I/O
	def __init__(self, programmer, socket, D_pin, clk_pin, S_pin, R_pin, Q_pin, Qbar_pin):
		self.programmer = programmer
		self.socket = socket

		self.D_pin = D_pin
		self.clk_pin = clk_pin
		self.S_pin = S_pin
		self.R_pin = R_pin
		self.Q_pin = Q_pin
		self.Qbar_pin = Qbar_pin

		# inputs
		self.D_flag = allpro88.flag_ttl(self.socket, self.D_pin)
		self.clk_flag = allpro88.flag_ttl(self.socket, self.clk_pin)
		self.S_flag = allpro88.flag_ttl(self.socket, self.S_pin)
		self.R_flag = allpro88.flag_ttl(self.socket, self.R_pin)
		# outputs
		self.Q_flag = allpro88.flag_ttl(self.socket, self.Q_pin, default = None)
		self.Qbar_flag = allpro88.flag_ttl(self.socket, self.Qbar_pin, default = None)

	D = devices.flag_proxy("D_flag")
	clk = devices.flag_proxy("clk_flag")
	S = devices.flag_proxy("S_flag")
	R = devices.flag_proxy("R_flag")
	Q = devices.flag_proxy("Q_flag")
	Qbar = devices.flag_proxy("Qbar_flag")

	def check_Q(self, val, Qbar_val = None):
		val = bool(val)
		Q = self.Q
		if Q != val:
			raise ValueError("Q:  expected %s, got %s" % (val, Q))
		Qbar = self.Qbar
		if Qbar_val is None:
			# default expected value is inverse of Q's expected
			# value
			Qbar_val = not Q
		if Qbar != Qbar_val:
			raise ValueError("Qbar:  expected %s, got %s" % (Qbar_val, Qbar))
		return Q

	def test(self):
		# reset
		self.R = True
		# all inputs low
		self.D = self.clk = self.S = self.R = False
		# is Q false?
		self.check_Q(False)
		# clock 512 bits into D, confirm output
		for i in tqdm(range(1024), desc = "testing D and clk"):
			self.D = i & 2
			self.clk = i & 1
			if i & 1:
				self.check_Q(i & 2)
		# repeatedly play with set and reset
		previous = self.Q
		for i in tqdm(range(1024), desc = "testing S and R"):
			self.S = i & 1
			self.R = i & 2
			Q_expected, Qbar_expected = {
				0:	(previous, not previous),	# !S, !R
				1:	(True, False),	# S, !R
				2:	(False, True),	# !S, R
				3:	(True, True),	# S, R
			}[i & 3]
			self.check_Q(Q_expected, Qbar_expected)
			previous = False


class CD4013B(object):
	"""
	Dual D flip-flop.
	"""
	def __init__(self, programmer, Vdd = 5.0):
		self.programmer = programmer
		self.socket = programmer.socket_module.sockets["DIP14"]
		# power pins
		self.power = devices.power(self.programmer, self.socket, {
			"default": {
				7:	0,
				14:	Vdd
			}
		})
		# two D type flip-flops
		self.flip_flops = [
			D_flip_flop(self.programmer, self.socket, 5, 3, 6, 4, 1, 2),
			D_flip_flop(self.programmer, self.socket, 9, 11, 8, 10, 13, 12)
		]

	def __enter__(self):
		self.power.on()
		return self

	def __exit__(self, exc_type, exc_val, exc_tb):
		self.power.off()
		# done.  if an exception has occured, continue processing
		return False

	def test(self):
		for i, flip_flop in enumerate(self.flip_flops, 1):
			print("testing flip flop %d" % i)
			flip_flop.test()


with allpro88.allpro88() as programmer:
	with CD4013B(programmer) as device:
		device.test()
