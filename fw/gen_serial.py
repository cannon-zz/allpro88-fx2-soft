#!/usr/bin/env python3

#
# example use:
#
# $ uuidgen | python3 gen_serial.py
#
# the first line of text will be used, any others that follow will be
# discarded, and that line's leading and trailing whitespace will be
# removed.
#

import string
import sys

# printable ascii characters, no whitespace and no slashes
allowed = set(string.printable) - set(string.whitespace) - set("/\\")

for line in sys.stdin.readlines():
	print("_string4:")
	print("\t.db\tstring4end-_string4\n\t.db\tDSCR_STRING_TYPE")
	for char in line.strip():
		assert char in allowed
		print("\t.ascii\t'%s'\n\t.db\t0" % char)
	print("string4end:")
	break

sys.exit()
