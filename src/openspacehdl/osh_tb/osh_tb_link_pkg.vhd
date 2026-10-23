---------------------------------------------------------------------------------------------------
-- Copyright (c) 2026 Julian Schneider
--
-- Permission is hereby granted, free of charge, to any person obtaining a copy of this software and
-- associated documentation files (the "Software"), to deal in the Software without restriction,
-- including without limitation the rights to use, copy, modify, merge, publish, distribute,
-- sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is
-- furnished to do so, subject to the following conditions:
--
-- The above copyright notice and this permission notice shall be included in all copies or substantial
-- portions of the Software.
--
-- THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT
-- NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
-- NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES
-- OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
-- CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
---------------------------------------------------------------------------------------------------

---------------------------------------------------------------------------------------------------
-- Description
---------------------------------------------------------------------------------------------------
-- Packet queues of the far ends for the traffic that is not RMAP: a protected type with a receive and a
-- send queue per far end (Index_g of the far end) and virtual channel (0 on SpaceWire). A far end
-- appends every packet it receives to the receive queue and sends every packet of the send queue; the
-- testbench takes and puts packets with the procedures of osh_tb_stream_pkg. The object itself is the
-- shared variable osh_link of osh_tb_linkvar_pkg (a shared variable of a protected type is declared after
-- the protected body, in a package of its own).
--
-- Documentation: docs/design.md of openspacehdl, section 6.3

---------------------------------------------------------------------------------------------------
-- Libraries
---------------------------------------------------------------------------------------------------
library ieee;
    use ieee.std_logic_1164.all;

library work;
    use work.osh_tb_pkg.all;

---------------------------------------------------------------------------------------------------
-- Package Header
---------------------------------------------------------------------------------------------------
package osh_tb_link_pkg is

    -- Far ends and virtual channels of the queues
    constant C_OSH_LINK_FAR_ENDS : positive := 8;
    constant C_OSH_LINK_VCS      : positive := 32;
    -- Longest packet of a queue in bytes
    constant C_OSH_LINK_MAX_BYTES : positive := 65536;

    type t_osh_link is protected
        -- Appends a packet to a queue; eep: the packet ended with an error end of packet
        procedure push_rx (
            far  : natural;
            vc   : natural;
            data : t_osh_byte_array;
            eep  : boolean);
        procedure push_tx (
            far  : natural;
            vc   : natural;
            data : t_osh_byte_array);
        -- Packets waiting in a queue
        impure function rx_count (
            far : natural;
            vc  : natural) return natural;
        impure function tx_count (
            far : natural;
            vc  : natural) return natural;
        -- Length and end marker of the first packet of a queue; the queue must not be empty
        impure function rx_length (
            far : natural;
            vc  : natural) return natural;
        impure function rx_eep (
            far : natural;
            vc  : natural) return boolean;
        impure function tx_length (
            far : natural;
            vc  : natural) return natural;
        -- Byte i of the first packet of a queue
        impure function rx_byte (
            far : natural;
            vc  : natural;
            i   : natural) return std_logic_vector;
        impure function tx_byte (
            far : natural;
            vc  : natural;
            i   : natural) return std_logic_vector;
        -- Removes the first packet of a queue
        procedure pop_rx (
            far : natural;
            vc  : natural);
        procedure pop_tx (
            far : natural;
            vc  : natural);
    end protected;

end package;

---------------------------------------------------------------------------------------------------
-- Package Body
---------------------------------------------------------------------------------------------------
package body osh_tb_link_pkg is

    type t_osh_link is protected body

        type t_bytes_ptr is access t_osh_byte_array;
        type t_packet;
        type t_packet_ptr is access t_packet;
        type t_packet is record
            Data : t_bytes_ptr;
            Eep  : boolean;
            Succ : t_packet_ptr;
        end record;
        type t_queue is record
            First : t_packet_ptr;
            Last  : t_packet_ptr;
            Count : natural;
        end record;
        type t_queues is array (0 to C_OSH_LINK_FAR_ENDS - 1, 0 to C_OSH_LINK_VCS - 1) of t_queue;

        variable Rx_v : t_queues;
        variable Tx_v : t_queues;

        procedure push (
            q    : inout t_queue;
            data : t_osh_byte_array;
            eep  : boolean) is
            variable P_v : t_packet_ptr;
        begin
            P_v      := new t_packet;
            P_v.Data := new t_osh_byte_array(0 to data'length - 1);
            P_v.Eep  := eep;

            for I in 0 to data'length - 1 loop
                P_v.Data(I) := data(data'low + I);
            end loop;

            if q.Last = null then
                q.First := P_v;
            else
                q.Last.Succ := P_v;
            end if;

            q.Last  := P_v;
            q.Count := q.Count + 1;
        end procedure;

        procedure pop (q : inout t_queue) is
            variable P_v : t_packet_ptr;
        begin
            P_v     := q.First;
            q.First := P_v.Succ;

            if q.First = null then
                q.Last := null;
            end if;

            q.Count := q.Count - 1;
            deallocate(P_v.Data);
            deallocate(P_v);
        end procedure;

        procedure push_rx (
            far  : natural;
            vc   : natural;
            data : t_osh_byte_array;
            eep  : boolean) is
        begin
            push(Rx_v(far, vc), data, eep);
        end procedure;

        procedure push_tx (
            far  : natural;
            vc   : natural;
            data : t_osh_byte_array) is
        begin
            push(Tx_v(far, vc), data, false);
        end procedure;

        impure function rx_count (
            far : natural;
            vc  : natural) return natural is
        begin
            return Rx_v(far, vc).Count;
        end function;

        impure function tx_count (
            far : natural;
            vc  : natural) return natural is
        begin
            return Tx_v(far, vc).Count;
        end function;

        impure function rx_length (
            far : natural;
            vc  : natural) return natural is
        begin
            return Rx_v(far, vc).First.Data'length;
        end function;

        impure function rx_eep (
            far : natural;
            vc  : natural) return boolean is
        begin
            return Rx_v(far, vc).First.Eep;
        end function;

        impure function tx_length (
            far : natural;
            vc  : natural) return natural is
        begin
            return Tx_v(far, vc).First.Data'length;
        end function;

        impure function rx_byte (
            far : natural;
            vc  : natural;
            i   : natural) return std_logic_vector is
        begin
            return Rx_v(far, vc).First.Data(i);
        end function;

        impure function tx_byte (
            far : natural;
            vc  : natural;
            i   : natural) return std_logic_vector is
        begin
            return Tx_v(far, vc).First.Data(i);
        end function;

        procedure pop_rx (
            far : natural;
            vc  : natural) is
        begin
            pop(Rx_v(far, vc));
        end procedure;

        procedure pop_tx (
            far : natural;
            vc  : natural) is
        begin
            pop(Tx_v(far, vc));
        end procedure;

    end protected body;

end package body;
