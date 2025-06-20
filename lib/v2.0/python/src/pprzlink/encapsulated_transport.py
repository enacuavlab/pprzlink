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

import struct
import typing
from enum import IntEnum
from dataclasses import dataclass

from .message import PprzMessage
from .abstract_transport import AbstractTransport,UnpackedMessage



class EncaspulatedTransport(AbstractTransport):
    
    @dataclass
    class EncapsulatedMessage:
        """
        Encapsulation structure for splitting messages 
        """
        
        msg_uid:int         # Current message unique id (to avoid overlap between subsequent transmissions)
        part_total:int      # Total number of parts for this message
        part_id:int         # Part ID (from 0 to part_total-1)
        content_size:int    # Content size
        content:bytes       # Actual content
        
    
    def __init__(self,max_size:int,underlying:AbstractTransport) -> None:
        assert max_size > 4
        self.max_size = max_size
        self.under_trans = underlying
        self.capsules:typing.Dict[int,EncaspulatedTransport.EncapsulatedMessage] = dict()
        
    
    def parse_byte(self, c: bytes) -> bool:
        under = self.under_trans.parse_byte(c)
        if under:
            data = self.under_trans.unpack_raw()
            if data is not None:
                self._parse_capsule(data)
            
        
    
    def _parse_capsule(self,buf:bytes):
        cap = EncaspulatedTransport.EncapsulatedMessage(
            buf[0],
            buf[1],
            buf[2],
            buf[3],
            buf[4:]
        )
        
            
    
    def unpack(self) -> typing.Optional[UnpackedMessage]:
        pass 

    def pack_data(self,sender:int, data:bytes, receiver:int=0, component:int=0) -> bytes:
        pass

    