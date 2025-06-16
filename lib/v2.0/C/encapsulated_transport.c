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

#ifndef UNUSED
#define UNUSED __attribute__((unused))
#endif

// Extra fancy min and max macro, taken from:
// https://stackoverflow.com/questions/3437404/min-and-max-in-c
// (These definitions prevent double evaluation of their arguments, thus avoiding issues if someone
// wants to do min(x++,y++) ...)
#define max(a,b) \
  ({ __typeof__ (a) _a = (a); \
      __typeof__ (b) _b = (b); \
    _a > _b ? _a : _b; })

#define min(a,b) \
  ({ __typeof__ (a) _a = (a); \
      __typeof__ (b) _b = (b); \
    _a < _b ? _a : _b; })


#include "encapsulated_transport.h"

/******************** Helper functions ********************/

// The actual size of the capsule header is everything which is not the content pointer
const unsigned int encapsulated_header_size = sizeof(uint8_t)*4;
static unsigned int encapsulated_size(encapsulated_msg* enc_msg)
{
    return encapsulated_header_size + enc_msg->content_size;
}

static struct encapsulated_transport* get_encapsulated_transport(struct pprzling_msg *msg)
{
    return (struct encapsulated_transport*) msg->trans->impl;
}

static struct transport_tx * get_underlyind_tx(struct pprzling_msg *msg)
{
    struct encapsulated_transport* encap_trans = msg->trans->impl;
    return encap_trans->under_trans_tx;
}

static struct transport_rx * get_underlyind_rx(struct pprzling_msg *msg)
{
    struct encapsulated_transport* encap_trans = msg->trans->impl;
    return encap_trans->under_trans_rx;
}

static int send_chunk(struct pprzling_msg *msg, long fd, encapsulated_msg* enc_msg)
{
    // We are going to use the underlying transport, so switch the reference in msg
    struct transport_tx* curr_tx = msg->trans;
    struct transport_tx* under_tx = get_underlyind_tx(msg);
    
    msg->trans = under_tx;

    // Compute encapsulated message length
    uint8_t caps_len = encapsulated_size(enc_msg);
    uint8_t header_content[] = {
        enc_msg->msg_id,
        enc_msg->part_total,
        enc_msg->part_id,
        enc_msg->content_size,
    };

    // Send the encapsulated message
    int enc_msg_sent = under_tx->check_available_space(msg, &fd, caps_len);
    if (enc_msg_sent)
    {
        under_tx->start_message(msg, fd, caps_len);
        under_tx->put_bytes(msg, fd, DL_TYPE_UINT8, DL_FORMAT_ARRAY, header_content, sizeof(header_content));
        under_tx->put_bytes(msg, fd, DL_TYPE_UINT8, DL_FORMAT_ARRAY, enc_msg->content, enc_msg->content_size);
        under_tx->end_message(msg, fd);
    }
    else
    {
        under_tx->overrun(msg);
    }

    // Restore the transmission structure
    msg->trans = curr_tx;

    return enc_msg_sent;
}

/**
 * @brief Performs one step of parsing an encapsulated message and putting in at the correct place in the destination buffer (if correct)
 * 
 * @param encap_trans Encapsulated transport structure, keeping 
 * @param src_buf Source buffer, where message parts are put one by one
 * @param dest_buf Destination buffer, where parts are unpacked and put together
 * @return int: Status of the parsing: -1 is failure (out of order part); 0 is OK, need more parts; 1 is done, full message rebuilt
 */
static int encapsulated_parse_part(struct encapsulated_transport* encap_trans, uint8_t* src_buf, uint8_t* dest_buf)
{
    // Recover header data of the part
    uint8_t msg_id          = buf[0];
    uint8_t part_total      = buf[1];
    uint8_t part_id         = buf[2];
    uint8_t content_size    = buf[3];
    encap_trans->trans_rx.msg_received = false;

    // Check if it is matching
    switch (encap_trans->phase)
    {
        case ENCAPSULATED_NEW:
            encap_trans->msg_part.msg_id            = msg_id;
            encap_trans->msg_part.part_total        = part_total;
            encap_trans->msg_part.part_id           = part_id;
            encap_trans->msg_part.content_size      = content_size;
            encap_trans->trans_rx.msg_received      = content_size;

            
            memcpy(dest_buf,(void*)(src_buf+encapsulated_header_size),content_size);
            encap_trans->writing_head_rx = content_size;

            if (part_id == part_total-1)
            {
                encap_trans->phase = ENCAPSULATED_DONE;
            }
            else
            {
                encap_trans->phase = ENCAPSULATED_ONGOING;
            }
            
            break;

        case ENCAPSULATED_ONGOING:
            encap_trans->msg_part.part_id++;
            encap_trans->trans_rx.msg_received += content_size;
            if (encap_trans->msg_part.part_id != part_id)
            {
                encap_trans->phase = ENCAPSULATED_NEW;
                return -1;
            }

            
            memcpy((void*)(dest_buf+encap_trans->writing_head_rx),
                    (void*)(src_buf+encapsulated_header_size),
                    content_size);

            
            if (part_id == part_total-1)
            {
                encap_trans->phase = ENCAPSULATED_DONE;
            }
            else
            {
                encap_trans->writing_head_rx += encap_msg->content_size;
            }
            break;
    }

    if (encap_trans->phase == ENCAPSULATED_DONE)
    {
        encap_trans->phase = ENCAPSULATED_NEW;
        encap_trans->trans_rx.msg_received = true;
        return 1;
    }
    
    return 0;
}

/******************** Functions required for TX ********************/

static uint8_t size_of(struct pprzlink_msg *msg UNUSED, uint8_t len)
{
    // This is an abstraction above the actual message sending device; returns exact message length
    return len;
}


static int check_available_space(struct pprzlink_msg *msg, long *fd, uint16_t bytes)
{
    // This is an abstraction; the available space is always the maximum allowed size for a message
    return TRANSPORT_PAYLOAD_LEN;
}


static void put_bytes(struct pprzlink_msg *msg, long fd UNUSED,
                      enum TransportDataType type UNUSED, enum TransportDataFormat format UNUSED,
                      const void *bytes, uint16_t len)
{
    struct encapsulated_transport* encap_trans = get_encapsulated_transport(msg);
    memcpy(encap_trans->msg_buf_tx+encap_trans->writing_head_tx,bytes,len);
    encap_trans->writing_head_tx += len;
}


static void put_named_byte(struct pprzlink_msg *msg, long fd UNUSED,
                           enum TransportDataType type UNUSED, enum TransportDataFormat format UNUSED,
                           uint8_t byte, const char *name UNUSED)
{
    struct encapsulated_transport* encap_trans = get_encapsulated_transport(msg);
    encap_trans->msg_buf_tx[encap_trans->writing_head_tx] = byte;
    encap_trans->writing_head_tx++;
}


static void start_message(struct pprzlink_msg *msg, long fd UNUSED, uint8_t payload_len)
{
    struct encapsulated_transport* encap_trans = get_encapsulated_transport(msg);
    encap_trans->writing_head_tx = 0;
    encap_trans->reading_head_tx = 0;
    encap_trans->payload_len_tx = payload_len;
}


static void end_message(struct pprzlink_msg *msg, long fd)
{
    struct encapsulated_transport* encap_trans = get_encapsulated_transport(msg);
    uint8_t encap_max_size = encap_trans->under_max_size;
    uint8_t encap_available_size = encap_max_size-encapsulated_header_size;
    
    uint8_t parts_id = 0;
    uint8_t parts_count = 1+encap_trans->payload_len_tx/(encap_available_size);
    encapsulated_msg encap_msg;
    encap_msg.parts_remaining = parts_count-1;
    encap_msg.msg_id = encap_trans->msg_id;

    int send_status;

    while(encap_trans->reading_head_tx < encap_trans->payload_len_tx)
    {
        encap_msg.content_size = min(encap_available_size, encap_trans->payload_len_tx - encap_trans->reading_head_tx);
        encap_msg.content = (encap_trans->msg_buf_tx+encap_trans->reading_head_tx);

        send_status = send_chunk(msg,fd,&encap_msg);

        encap_trans->reading_head_tx += encap_msg.content_size;
        encap_msg.parts_remaining--;
    }

    encap_trans->msg_id++;
}


static void overrun(struct pprzlink_msg *msg)
{
    struct encapsulated_transport* encap_trans = get_encapsulated_transport(msg);
    encap_trans->writing_head_tx = 0;
    encap_trans->reading_head_tx = 0;

    msg->dev->nb_ovrn++;
}


static void count_bytes(struct pprzlink_msg *msg, uint8_t bytes)
{
    msg->dev->nb_bytes += bytes;
}



/******************** Interface functions ********************/

/**
 * @brief 
 * 
 * @param encap_trans The structure to be initialized
 * @param underlying_transport Of type `struct XXX_transport* trans` matching the actual underlying transport, already initialized
 * @param under_max_size Maximum available size for a message in the underlying structure
 * @param under_trans_rx Underlying rx, taken from the transport structure
 * @param under_trans_tx Underlying tx, taken from the transport structure
 * @param check_and_parse Check and parse function, used to parse the messages to be reassembled
 */
void encapsulated_init(struct encapsulated_transport* encap_trans,
  void* underlying_transport,         
  uint8_t under_max_size,             
  struct transport_rx *under_trans_rx,
  struct transport_tx *under_trans_tx,
  check_and_parse_t check_and_parse)
{ 
    encap_trans->trans_rx.msg_received = false;
    encap_trans->trans_rx.ovrn  = 0;
    encap_trans->trans_rx.error = 0;

    encap_trans->trans_tx.size_of               = (size_of_t) size_of;
    encap_trans->trans_tx.check_available_space = (check_available_space_t) check_available_space;
    encap_trans->trans_tx.put_bytes             = (put_bytes_t) put_bytes;
    encap_trans->trans_tx.put_named_byte        = (put_named_byte_t) put_named_byte;
    encap_trans->trans_tx.start_message         = (start_message_t) start_message;
    encap_trans->trans_tx.end_message           = (end_message_t) end_message;
    encap_trans->trans_tx.overrun               = (overrun_t) overrun;
    encap_trans->trans_tx.count_bytes           = (count_bytes_t) count_bytes;
    encap_trans->trans_tx.impl = (void *)(encap_trans);

    encap_trans->msg_id = 0;

    encap_trans->under_max_size = under_max_size;
    encap_trans->under_trans_rx = under_trans_rx;
    encap_trans->under_trans_tx = under_trans_tx;
    encap_trans->check_and_parse = check_and_parse;
}   

void encapsulated_check_and_parse(struct link_device *dev, struct encapsulated_transport *encap_trans, uint8_t *buf, bool *msg_available)
{
    bool submsg_available = true;

    int subparse_status;
    while(submsg_available)
    {
        encap_trans->check_and_parse(dev,encap_trans->underlying_transport,encap_trans->msg_buf_rx,&submsg_available);
        if (submsg_available)
        {
            subparse_status = encapsulated_parse_part(encap_trans, encap_trans->msg_buf_rx,encap_trans->trans_rx.payload);
            if (subparse_status == 1)
            {
                memcpy(buf,encap_trans->trans_rx.payload,encap_trans->trans_rx.payload_len);
                *msg_available = true;
                encap_trans->trans_rx.msg_received = false;
            }
            else if (subparse_status < 0)
            {
                encap_trans->trans_tx.error++;
            }
        }

    }
    
}
