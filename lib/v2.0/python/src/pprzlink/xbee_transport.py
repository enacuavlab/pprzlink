# Copyright (C) 2025 Mael FEURGARD <mael.feurgard@enac.fr>
# 
# This file is part of PPRZLINK.
# 
# PPRZLINK is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# 
# PPRZLINK is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with PPRZLINK.  If not, see <https://www.gnu.org/licenses/>.

from enum import IntEnum
import struct
import typing

from .abstract_transport import AbstractTransport,UnpackedMessage
from pprzlink.message import PprzMessage

class XbeeTransport(AbstractTransport):
    XBEE_API_START = 0x7E
    GROUND_STATION_ADDR = 0x0100
    # DEFAULT_TIMEOUT = 0.1

    class RxState(IntEnum):
        WAIT_START = 0
        GET_LEN_1 = 1
        GET_LEN_2 = 2
        GET_FRAME_DATA = 3

    class ATStatus(IntEnum):
        Ok = 0
        Error = 1
        InvalidCmd = 2
        InvalidParam = 3

    class APITypes(IntEnum):
        MODEM_STATUS = 0x8A
        AT_CMD = 0x08
        AT_CMD_QU = 0x09
        AT_CMD_RES = 0x88
        REMOTE_AT_REQ = 0x17
        REMOTE_AT_RES = 0x97
        TX_64 = 0x00
        TX_16 = 0x01
        TX_STATUS = 0x89
        RX_64 = 0x80
        RX_16 = 0x81
        RX_IO_64 = 0x82
        RX_IO_16 = 0x83
    
    
    def __init__(self, msg_class:str='telemetry'):
        self.msg_class = msg_class
        self.rx_state = XbeeTransport.RxState.WAIT_START
        self.bytes_needed = 1
        self._frame_id = 0
        self.responses:dict[int,typing.Any] = {}
        self.buffer = bytearray()
        self.chk = 0
        self.__frame_id = 0
        
    @property
    def frame_id(self) -> int:
        """ A frame id, automatically incremented to ensure uniqueness

        Returns:
            int: a 'locally' unique ID (up to 1 byte)
        """
        r = self.__frame_id
        self.__frame_id = (self.__frame_id+1) & 0xFF
        
        # Avoid 0 as it is considered the 'default' value
        if self.__frame_id == 0:
            self.__frame_id += 1
            
        return r
        
    
    @staticmethod
    def checksum(frame:bytes) -> int:
        return 0xFF - (sum(frame) & 0xFF)
    
    @staticmethod
    def from16(nb: int) -> bytes:
        """ Encode an int on 16 bits (2 bytes), big endian style

        Args:
            nb (int): Python int to convert

        Returns:
            bytes: Int encoded on 2 bytes
        """
        return nb.to_bytes(2, 'big')

    @staticmethod
    def to16(data: bytes) -> int:
        """ Parse two bytes into an int, using big endian encoding

        Args:
            data (bytes): Bytes to parse

        Returns:
            int: Parsed int
        """
        return int.from_bytes(data, 'big')
    
    def parse_byte(self, c: bytes) -> bool:
        output = False
        b = struct.unpack("<B", c)[0]
        if self.rx_state == self.RxState.WAIT_START:
            if b == self.XBEE_API_START:
                self.rx_state = self.RxState.GET_LEN_1
                self.bytes_needed = 2
                self.buffer = bytearray()
        elif self.rx_state == self.RxState.GET_LEN_1:
            self.bytes_needed = (b << 8)
            self.rx_state = self.RxState.GET_LEN_2
        elif self.rx_state == self.RxState.GET_LEN_2:
            self.bytes_needed += b+1 # Add 1 byte for the checksum
            self.rx_state = self.RxState.GET_FRAME_DATA
        elif self.rx_state == self.RxState.GET_FRAME_DATA:
            if self.bytes_needed > 1:
                self.buffer.append(b)
                self.bytes_needed -= 1
            elif self.bytes_needed == 1:
                self.chk = b
                if self.checksum(self.buffer) == self.chk:
                    output = True
                else:
                    print("invalid chk: {}  {}".format(self.checksum(self.buffer), self.chk))
                self.rx_state = self.RxState.WAIT_START
                self.bytes_needed = 1
                
        return output

    
    def unpack_bytes(self,frame:bytes) -> typing.Optional[UnpackedMessage]:
        frame_type = frame[0]
        if frame_type == self.APITypes.MODEM_STATUS.value:
            pass    # TODO
        elif int(frame_type) == self.APITypes.AT_CMD_RES.value:
            frame_id = frame[1]
            at_cmd = frame[2:4]
            status = self.ATStatus(frame[4])
            data = frame[5:]
            self.responses[frame_id] = (status, data)
        elif frame_type == self.APITypes.RX_16.value:
            source_addr = self.to16(frame[1:3])
            rssi = frame[3]
            options = frame[4]
            data = frame[5:]
            
            return self.unpack_pprz_msg(data)
        elif frame_type == self.APITypes.TX_STATUS.value:
            frame_id = frame[1]
            status = frame[2]
            self.responses[frame_id] = status
        else:
            print("unknown frame type:", hex(frame_type))
        
        return None
    
    def unpack(self) -> typing.Optional[UnpackedMessage]:
        return self.unpack_bytes(self.buffer)
    
    def _tx_16_format(self,dest:int,data:bytes,ack:bool=False,options:int=0) -> bytes:
        """ Pack the data in an Xbee TX 16 format

        Args:
            dest (int): Destination Xbee receiver ID
            data (bytes): Data bytes
            ack (bool, optional): Use a nonzero frame id to be able to register an acknowledge. Defaults to False.
            options (int, optional): Xbee options. Defaults to 0.

        Returns:
            bytes: Packed data
        """
        if ack:
            fr_id = self.frame_id
        else:
            fr_id = 0
        return struct.pack(">BBHB",self.APITypes.TX_16.value, fr_id, dest, options) + data
    
    @classmethod
    def _pack_xbee(cls,frame:bytes) -> bytes:
        """ Put the frame (already in some Xbee format) in the Xbee API shape

        Args:
            frame (bytes): Xbee frame

        Returns:
            bytes: Xbee API-compatible frame
        """
        return struct.pack(">BH", cls.XBEE_API_START, len(frame)) + frame + struct.pack("<B", cls.checksum(frame))
    
    def pack_data(self, sender: int, data: bytes, receiver: int = 0, component: int = 0) -> bytes:
        if not (isinstance(receiver, int) and receiver < 0xFFFF):
            raise TypeError("destination invalid")
        
        xbee_dest = receiver
        if receiver == 0xFF:    # broadcast : xbee use 0xFFFF
            xbee_dest = 0xFFFF
        elif receiver == 0:     # ground station
            xbee_dest = self.GROUND_STATION_ADDR
        elif receiver > 0xFF:
            receiver = 0        # for non-drone destinations, assume its ground
        
        frame = self._tx_16_format(xbee_dest,data) # Xbee TX_16 formatting
        
        data = self._pack_xbee(frame) # Xbee transmission formatting
        return data
    
    def at_cmd(self, at:bytes, value:typing.Optional[bytes]=None, resp:bool=True) -> typing.Tuple[bytes,int]:
        """ Create a packet for an Xbee AT command

        Args:
            at (bytes): Command
            value (typing.Optional[bytes], optional): Command arguments if needed. Defaults to None.
            resp (bool, optional): Request for a response. Defaults to True.

        Returns:
            typing.Tuple[bytes,int]: The formatted packet to send, and the associated ID (needed for identifying the response; 0 is no response asked)
        """
        if resp:
            frame_id = self.frame_id
        else:
            frame_id = 0
        cmd = struct.pack("<BB", 0x08, frame_id) + at
        if value is not None:
            cmd += value
            
        return self._pack_xbee(cmd),frame_id