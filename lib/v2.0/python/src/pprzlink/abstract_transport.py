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

from abc import ABC,abstractmethod
import typing
import struct

from pprzlink.message import PprzMessage

UnpackedMessage = tuple[int,PprzMessage,int,int]

class AbstractTransport(ABC):
    @abstractmethod
    def parse_byte(self,c:bytes) -> bool:
        """ Parse ONE byte (length of `c` must be 1)

        Args:
            c (bytes): byte to parse

        Returns:
            bool: True if a message can be unpacked, False otherwise
        """
        ...
        
    def parse_bytes(self,c:bytes) -> list[UnpackedMessage]:
        """ Parse several bytes at once
        If not reimplemented, simply call `parse_byte` on each byte of the input

        Args:
            c (bytes): bytes to parse

        Returns:
            list[UnpackedMessage]: The messages that have been fully parsed and unpacked
        """
        
        output = []
        
        for b in c:
            r = self.parse_byte(bytes(b))
            if r:
                m = self.unpack()
                if m is not None:
                    output.append(m)
        
        return output
    
    @staticmethod
    def unpack_pprz_msg(data:typing.Union[bytes,bytearray]) -> UnpackedMessage:
        """Unpack a raw PPRZ message"""
        sender_id = data[0]
        receiver_id = data[1]
        class_id = data[2] & 0x0F
        component_id = (data[2] & 0xF0) >> 4
        msg_id = data[3]
        msg = PprzMessage(class_id, msg_id)
        msg.binary_to_payload(data[4:])
        return sender_id, msg, receiver_id, component_id
    
    @abstractmethod
    def unpack(self) -> typing.Optional[UnpackedMessage]:
        """ Unpack the content of the internal buffer
        Should only be called right after `parse_byte` returns True

        Returns:
            typing.Optional[UnpackedMessage]: None, if the message is not a Pprz one, or an Unpacked message,
                that is a tuple containing (Sender ID:int, message:PprzMessage, Receiver ID: int, Component ID: int)
        """
        ...
        
    @abstractmethod
    def unpack_raw(self) -> typing.Optional[bytes]:
        """ Return the raw content of the internal buffer, or None if there is no content to be returned
        Should only be called right after `parse_byte` returns True

        Returns:
            typing.Optional[bytes]: Last received content if there is some, None otherwise
        """
        
    @abstractmethod
    def pack_data(self,sender:int, data:bytes, receiver:int=0, component:int=0) -> bytes:
        """ Pack some bytes to be sent

        Args:
            sender (int): ID of the sender
            data (bytes): content
            receiver (int, optional): ID of the receiver. Defaults to 0 (ground station).
            component (int, optional): ID of the component/device used to send the message. Defaults to 0.

        Returns:
            bytes: Packed data ready to be sent to the device
        """
        ...
        
    def pack_pprz_msg(self,sender:int, msg:PprzMessage, receiver:int=0, component:int=0) -> bytes:
        """ Pack a message into bytes ready to be sent

        Args:
            sender (int): ID of the sender
            msg (PprzMessage): Message content
            receiver (int, optional): ID of the receiver. Defaults to 0 (ground station).
            component (int, optional): ID of the component/device used to send the message. Defaults to 0.

        Returns:
            bytes: Packed data ready to be sent to the device
        """
        
        comp_class = ((component & 0x0F) << 4) | (msg.class_id & 0x0F)
        bytes_msg = struct.pack("<BBBB",sender,receiver,comp_class,msg.msg_id) + msg.payload_to_binary()
        return self.pack_data(sender,bytes_msg,receiver,component)
    