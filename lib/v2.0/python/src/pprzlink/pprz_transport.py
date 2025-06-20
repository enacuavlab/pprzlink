#
# This file is part of PPRZLINK.
# 
# PPRZLINK is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# PPRZLINK is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with PPRZLINK.  If not, see <https://www.gnu.org/licenses/>.
#

"""
Paparazzi transport encoding utilities

"""

from __future__ import absolute_import, division
import typing
import struct
from pprzlink.message import PprzMessage
from pprzlink.abstract_transport import AbstractTransport,UnpackedMessage

from enum import IntEnum


STX = 0x99

class PprzParserState(IntEnum):
    WaitSTX = 1
    GotSTX = 2
    GotLength = 3
    GotPayload = 4
    GotCRC1 = 5

class PprzTransport(AbstractTransport):
    """parser for binary Paparazzi messages"""
    def __init__(self, msg_class='telemetry'):
        self.msg_class = msg_class
        self.reset_parser()

    def reset_parser(self):
        self.state = PprzParserState.WaitSTX
        self.length = 0
        self.buf = bytearray()
        self.ck_a = 0
        self.ck_b = 0
        self.idx = 0

    def parse_byte(self, c):
        """parse new byte, return True when a new full message is available"""
        b = struct.unpack("<B", c)[0]
        if self.state == PprzParserState.WaitSTX:
            if b == STX:
                self.state = PprzParserState.GotSTX
        elif self.state == PprzParserState.GotSTX:
            self.length = b - 4
            if self.length < 0:
                self.state = PprzParserState.WaitSTX
                return False
            self.buf = bytearray(self.length)
            self.ck_a = b % 256
            self.ck_b = b % 256
            self.idx = 0
            self.state = PprzParserState.GotLength
        elif self.state == PprzParserState.GotLength:
            self.buf[self.idx] = b
            self.ck_a = (self.ck_a + b) % 256
            self.ck_b = (self.ck_b + self.ck_a) % 256
            self.idx += 1
            if self.idx == self.length:
                self.state = PprzParserState.GotPayload
        elif self.state == PprzParserState.GotPayload:
            if self.ck_a == b:
                self.state = PprzParserState.GotCRC1
            else:
                self.state = PprzParserState.WaitSTX
        elif self.state == PprzParserState.GotCRC1:
            self.state = PprzParserState.WaitSTX
            if self.ck_b == b:
                """New message available"""
                return True
        else:
            self.state = PprzParserState.WaitSTX
        return False

    def unpack(self) -> UnpackedMessage:
        """Unpack the last received message"""
        return self.unpack_pprz_msg(self.buf)
    
    def unpack_raw(self) -> bytes | None:
        return self.buf

    @staticmethod
    def calculate_checksum(data:bytes) -> typing.Tuple[int,int]:
        ck_a = 0
        ck_b = 0
        for c in data:
            ck_a = (ck_a + c) & 0xFF
            ck_b = (ck_b + ck_a) & 0xFF
        return ck_a, ck_b

    def pack_data(self, sender: int, data: bytes, receiver: int = 0, component: int = 0) -> bytes:
        length = 4 + len(data)
        output  = struct.pack("<BB",STX,length) + data
        (ck_a, ck_b) = self.calculate_checksum(output[1:]) # The STX does not count when computing checksum
        output += struct.pack("<BB",ck_a,ck_b)
        return output


