import allpro88


class bus(object):
	def __init__(self, pin_numbers, min_word = None, max_word = None):
		self.min_word = 0 if min_word is None else min_word
		self.max_word = 2**len(pin_numbers) - 1 if max_word is None else max_word
		self.pin_numbers = tuple((1 << i, pin_number) for i, pin_number in enumerate(pin_numbers))

	def __get__(self, obj, objtype = None):
		data = 0
		for bit, pin_number in self.pin_numbers:
			if obj.socket[pin_number]:
				data |= bit
		return data

	def __set__(self, obj, word):
		# check type compatibility and range
		word = int(word)
		if not (self.min_word <= word <= self.max_word):
			raise ValueError("0x%X <= word <= 0x%X: 0x%X" % (self.min_word, self.max_word, word))
		for bit, pin_number in self.pin_numbers:
			obj.socket[pin_number].config = allpro88.PINCON.LOGICH if (word & bit) else allpro88.PINCON.LOGICL
