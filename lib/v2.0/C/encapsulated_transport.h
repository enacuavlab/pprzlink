/*
 * Copyright (C) 2025 Mael FEURGARD <mael.feurgard@enac.fr>
 *
 * This file is part of paparazzi.
 *
 * paparazzi is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 2, or (at your option)
 * any later version.
 *
 * paparazzi is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with paparazzi; see the file COPYING.  If not, see
 * <http://www.gnu.org/licenses/>.
 *
 */

/**
 * @file pprzlink/encapsulated_transport.h
 * Allow messages to be split in smaller parts, be sent, received, then reassembled. This may be required is the
 * transmission device does not allow messages as large as the maximum allowed by the protocol (currently 256 bytes)
 */

#ifndef ENCAPSULATED_TRANSPORT_H
#define ENCAPSULATED_TRANSPORT_H

#include <inttypes.h>
#include <stdbool.h>
#include <string.h>
#include "pprzlink/pprzlink_transport.h"
#include "pprzlink/pprzlink_device.h"


// Encapsulation structure for splitting messages 
typedef struct {
  uint8_t msg_uid;    ///< Current message unique id (to avoid overlap between subsequent transmissions)
  uint8_t part_total; ///< Total number of parts for this message
  uint8_t part_id;    ///< Part ID (from 0 to part_total-1)
  
  uint8_t content_size; ///< Content size
  void* content;        ///< Actual content
} encapsulated_msg;

enum EncapsulatedReceptionPhase {
  ENCAPSULATED_NEW,
  ENCAPSULATED_ONGOING,
  ENCAPSULATED_DONE
};

struct encapsulated_transport {
  // -- generic reception interface
  struct transport_rx trans_rx;
  uint8_t msg_buf_rx[TRANSPORT_PAYLOAD_LEN];///< Storage buffer at reception
  uint8_t writing_head_rx;                  ///< Reading and writing offset for the rx buffer
  uint8_t payload_len_rx;                   ///< Total size of the message
  encapsulated_msg msg_part;                ///< Storage for the last message part seen
  enum EncapsulatedReceptionPhase phase;    ///< Finite State Machine for recombining message parts at reception 
  // -- generic transmission interface
  struct transport_tx trans_tx;
  // -- specific packeted transport variables
  uint8_t msg_buf_tx[TRANSPORT_PAYLOAD_LEN];///< Storage buffer before slicing for sending
  uint8_t writing_head_tx,reading_head_tx;  ///< Reading and writing offset for the tx buffer
  uint8_t payload_len_tx;                   ///< Total size of the message
  uint8_t msg_uid;                          ///< Local ID to identify the message currently being sent


  // -- underlying transport structure
  uint8_t under_max_size;
  struct transport_rx *under_trans_rx;
  struct transport_tx *under_trans_tx;
  void* underlying_transport; // Of type `struct XXX_transport* trans` matching the actual underlying transport
  check_and_parse_t check_and_parse;
};


extern void encapsulated_init(struct encapsulated_transport*, // The structure to be initialized
  void* underlying_transport,           // Of type `struct XXX_transport* trans` matching the actual underlying transport, already initialized
  uint8_t under_max_size,               // Maximum available size for a message in the underlying structure
  struct transport_rx *under_trans_rx,  // Underlying rx, taken from the transport structure
  struct transport_tx *under_trans_tx,  // Underlying tx, taken from the transport structure
  check_and_parse_t check_and_parse);   // Check and parse function, used to parse the messages to be reassembled


extern void encapsulated_check_and_parse(struct link_device *dev, struct encapsulated_transport *trans, uint8_t *buf, bool *msg_available);

#endif