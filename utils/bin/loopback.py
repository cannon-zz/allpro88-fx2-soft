# Copyright (C) 2022-2024  Kipp Cannon
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


import random
from tqdm import tqdm
from . import allpro88

with allpro88.allpro88() as programmer:
	for i in tqdm(range(100000), desc = "loopback test"):
		snd = random.randint(0, 0xffff)
		rcv = programmer.echo(snd)
		assert rcv == snd

	for i in tqdm(range(100000), desc = "port read speed test"):
		# device address 0x0280 is the socket board ID
		programmer.read_addr(0x0280)

	programmer.pcr_enable = True
	for i in tqdm(range(70000), desc = "voltage read speed test"):
		# my unit only has 48 channels installed
		programmer.channels[random.randint(0, 47)].measure_v()
	programmer.pcr_enable = False
