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
-- Packets of the far ends that are not RMAP: sending and checking them through the queues of
-- osh_tb_link_pkg, and the Space Packets with their CPTP header that the stream checks of the generated
-- testbench build and expect (CCSDS 133.0-B-2 section 4.1.3, ECSS-E-ST-50-53C section 5.3).
--
-- Documentation: docs/design.md of openspacehdl, section 6.3

---------------------------------------------------------------------------------------------------
-- Libraries
---------------------------------------------------------------------------------------------------
library ieee;
    use ieee.std_logic_1164.all;
    use ieee.numeric_std.all;

library uvvm_util;
    context uvvm_util.uvvm_util_context;

library bitvis_vip_axistream;
    use bitvis_vip_axistream.axistream_bfm_pkg.t_user_array;

library work;
    use work.osh_tb_pkg.all;
    use work.osh_tb_linkvar_pkg.all;

---------------------------------------------------------------------------------------------------
-- Package Header
---------------------------------------------------------------------------------------------------
package osh_tb_stream_pkg is

    -- Puts a packet into the send queue of far end far, virtual channel vc (0 on SpaceWire)
    procedure osh_link_send (
        constant far  : in natural;
        constant vc   : in natural;
        constant data : in t_osh_byte_array;
        constant msg  : in string);

    -- Waits until the receive queue of far end far, virtual channel vc holds a packet; a TB_ERROR alert
    -- when none arrives within timeout. found tells whether one arrived; the packet stays in the queue.
    procedure osh_link_wait (
        constant far     : in  natural;
        constant vc      : in  natural;
        constant timeout : in  time;
        variable found   : out boolean;
        constant msg     : in  string);

    -- Waits for the next packet and checks it against expected: its length, every byte and its end of
    -- packet (EOP). The packet is removed from the queue.
    procedure osh_link_check (
        constant far      : in natural;
        constant vc       : in natural;
        constant expected : in t_osh_byte_array;
        constant timeout  : in time;
        constant msg      : in string);

    -- Packet Primary Header of a Space Packet (CCSDS 133.0-B-2 4.1.3): version 000, packet type
    -- (true: telecommand), secondary header flag, APID, sequence flags 11 (unsegmented), sequence count
    -- and the Packet Data Length of a data field of data_bytes bytes
    function osh_space_packet_header (
        apid       : natural;
        tc         : boolean;
        shf        : boolean;
        count      : natural;
        data_bytes : positive) return t_osh_byte_array;

    -- A Space Packet: its header and the data field
    function osh_space_packet (
        apid  : natural;
        tc    : boolean;
        shf   : boolean;
        count : natural;
        data  : t_osh_byte_array) return t_osh_byte_array;

    -- CPTP header of a packet without Target SpaceWire Address (ECSS-E-ST-50-53C 5.3): Target Logical
    -- Address, Protocol Identifier 0x02, Reserved 0x00, User Application value
    function osh_cptp_header (
        tla : std_logic_vector(7 downto 0);
        ua  : std_logic_vector(7 downto 0)) return t_osh_byte_array;

    -- The packets of a chain of ocr_framer and ocr_core (dense output) through an spp_core: CPTP packets
    -- with the header tla, ua, Space Packets of APID apid, telemetry, without secondary header, counted
    -- from count; each carries one chunk as IV || AAD || ciphertext || tag. The procedure checks every
    -- packet until the one with the last chunk: the CPTP header, the Packet Primary Header (Packet Data
    -- Length = 32 + chunk bytes - 1), the IV of the deterministic construction (fixed field iv_fixed,
    -- invocation counter iv_count + chunk number, GCM 8.2.1) and the position of the chunk in the first
    -- byte of the AAD (bits 7:6: "01" first, "00" middle, "10" last, "11" the only chunk). With
    -- total_bytes > 0 the chunks are those of one message of total_bytes bytes cut into chunks of
    -- chunk_bytes, and their number and lengths are checked as well. chunks returns the packets taken.
    procedure osh_link_check_chunks (
        constant far         : in  natural;
        constant vc          : in  natural;
        constant tla         : in  std_logic_vector(7 downto 0);
        constant ua          : in  std_logic_vector(7 downto 0);
        constant apid        : in  natural;
        constant count       : in  natural;
        constant iv_fixed    : in  std_logic_vector(31 downto 0);
        constant iv_count    : in  std_logic_vector(63 downto 0);
        constant chunk_bytes : in  positive;
        constant total_bytes : in  natural;
        constant max_chunks  : in  positive;
        constant timeout     : in  time;
        variable chunks      : out natural;
        constant msg         : in  string);

    -- The bytes of t_osh_byte_array as the t_slv_array of UVVM (for the AXI4-Stream VVCs)
    function osh_slv_bytes (data : t_osh_byte_array) return t_slv_array;

    -- n user words of the AXI4-Stream VVCs with the same value
    function osh_axis_user (
        n     : positive;
        value : std_logic_vector) return t_user_array;

    -- n samples of bits bits from sample first on, as words of the AXI4-Stream VVC (whole bytes, the
    -- sample in the low bits): sample i is the low bits of osh_mem_byte(i, seed + 1) & osh_mem_byte(i, seed),
    -- so every sample depends on every bit of its index
    function osh_samples (
        first : natural;
        n     : positive;
        bits  : positive;
        seed  : natural) return t_slv_array;

end package;

---------------------------------------------------------------------------------------------------
-- Package Body
---------------------------------------------------------------------------------------------------
package body osh_tb_stream_pkg is

    -- Time between two looks at a queue
    constant C_POLL : time := 100 ns;

    procedure osh_link_send (
        constant far  : in natural;
        constant vc   : in natural;
        constant data : in t_osh_byte_array;
        constant msg  : in string) is
    begin
        osh_link.push_tx(far, vc, data);
        log(ID_SEQUENCER, msg & ": " & integer'image(data'length) & " bytes to far end " & integer'image(far)
                          & ", virtual channel " & integer'image(vc), "osh_link_send");
    end procedure;

    procedure osh_link_wait (
        constant far     : in  natural;
        constant vc      : in  natural;
        constant timeout : in  time;
        variable found   : out boolean;
        constant msg     : in  string) is
        constant End_c : time := now + timeout;
    begin

        while osh_link.rx_count(far, vc) = 0 and now < End_c loop
            wait for C_POLL;
        end loop;

        found := osh_link.rx_count(far, vc) > 0;

        if osh_link.rx_count(far, vc) = 0 then
            alert(TB_ERROR, msg & ": no packet at far end " & integer'image(far) & ", virtual channel "
                            & integer'image(vc) & " within " & to_string(timeout), "osh_link_wait");
        end if;

    end procedure;

    procedure osh_link_check (
        constant far      : in natural;
        constant vc       : in natural;
        constant expected : in t_osh_byte_array;
        constant timeout  : in time;
        constant msg      : in string) is
        variable Found_v : boolean;
        variable Len_v   : natural;
        variable Bad_v   : natural := 0;
    begin
        osh_link_wait(far, vc, timeout, Found_v, msg);

        if Found_v then
            Len_v := osh_link.rx_length(far, vc);
            check_value(Len_v, expected'length, ERROR, msg & ": packet length", "osh_link_check");
            check_value(osh_link.rx_eep(far, vc), false, ERROR, msg & ": end of packet", "osh_link_check");

            for I in 0 to minimum(Len_v, expected'length) - 1 loop

                if osh_link.rx_byte(far, vc, I) /= expected(expected'low + I) then
                    Bad_v := Bad_v + 1;

                    if Bad_v = 1 then
                        alert(ERROR, msg & ": byte " & integer'image(I) & " is 0x"
                                     & to_hstring(osh_link.rx_byte(far, vc, I)) & ", expected 0x"
                                     & to_hstring(expected(expected'low + I)), "osh_link_check");
                    end if;

                end if;

            end loop;

            if Bad_v = 0 and Len_v = expected'length then
                log(ID_SEQUENCER, msg & ": " & integer'image(Len_v) & " bytes as expected", "osh_link_check");
            end if;

            osh_link.pop_rx(far, vc);
        end if;

    end procedure;

    function osh_space_packet_header (
        apid       : natural;
        tc         : boolean;
        shf        : boolean;
        count      : natural;
        data_bytes : positive) return t_osh_byte_array is
        variable H_v : unsigned(47 downto 0) := (others => '0');
    begin
        H_v(47 downto 45) := "000";

        if tc then
            H_v(44) := '1';
        end if;

        if shf then
            H_v(43) := '1';
        end if;

        H_v(42 downto 32) := to_unsigned(apid mod 2048, 11);
        H_v(31 downto 30) := "11";
        H_v(29 downto 16) := to_unsigned(count mod 16384, 14);
        H_v(15 downto 0)  := to_unsigned(data_bytes - 1, 16);
        return (std_logic_vector(H_v(47 downto 40)), std_logic_vector(H_v(39 downto 32)),
                std_logic_vector(H_v(31 downto 24)), std_logic_vector(H_v(23 downto 16)),
                std_logic_vector(H_v(15 downto 8)), std_logic_vector(H_v(7 downto 0)));
    end function;

    function osh_space_packet (
        apid  : natural;
        tc    : boolean;
        shf   : boolean;
        count : natural;
        data  : t_osh_byte_array) return t_osh_byte_array is
        variable P_v : t_osh_byte_array(0 to data'length + 5);
    begin
        P_v(0 to 5) := osh_space_packet_header(apid, tc, shf, count, data'length);

        for I in 0 to data'length - 1 loop
            P_v(6 + I) := data(data'low + I);
        end loop;

        return P_v;
    end function;

    function osh_cptp_header (
        tla : std_logic_vector(7 downto 0);
        ua  : std_logic_vector(7 downto 0)) return t_osh_byte_array is
    begin
        return (tla, x"02", x"00", ua);
    end function;

    procedure osh_link_check_chunks (
        constant far         : in  natural;
        constant vc          : in  natural;
        constant tla         : in  std_logic_vector(7 downto 0);
        constant ua          : in  std_logic_vector(7 downto 0);
        constant apid        : in  natural;
        constant count       : in  natural;
        constant iv_fixed    : in  std_logic_vector(31 downto 0);
        constant iv_count    : in  std_logic_vector(63 downto 0);
        constant chunk_bytes : in  positive;
        constant total_bytes : in  natural;
        constant max_chunks  : in  positive;
        constant timeout     : in  time;
        variable chunks      : out natural;
        constant msg         : in  string) is
        constant Head_c   : natural := 4 + 6;  -- CPTP header and Packet Primary Header
        constant Expect_c : natural := (total_bytes + chunk_bytes - 1) / chunk_bytes;
        variable Found_v  : boolean;
        variable N_v      : natural := 0;
        variable Len_v    : natural;
        variable Data_v   : natural;
        variable Iv_v     : std_logic_vector(95 downto 0);
        variable Pos_v    : std_logic_vector(1 downto 0);
        variable Want_v   : std_logic_vector(1 downto 0);
        variable Head_v   : t_osh_byte_array(0 to 5);
    begin

        loop
            osh_link_wait(far, vc, timeout, Found_v, msg & ", chunk " & integer'image(N_v));
            exit when not Found_v;
            Len_v := osh_link.rx_length(far, vc);
            check_value(Len_v > Head_c + 32, ERROR, msg & ": packet " & integer'image(N_v) & " of "
                                                    & integer'image(Len_v) & " bytes", "osh_link_check_chunks");
            exit when Len_v <= Head_c + 32;
            Data_v := Len_v - Head_c - 32;
            Head_v := osh_space_packet_header(apid, false, false, count + N_v, Len_v - Head_c);

            for I in 0 to 3 loop
                check_value(osh_link.rx_byte(far, vc, I), osh_cptp_header(tla, ua)(I), ERROR,
                            msg & ": CPTP header byte " & integer'image(I), "osh_link_check_chunks");
            end loop;

            for I in 0 to 5 loop
                check_value(osh_link.rx_byte(far, vc, 4 + I), Head_v(I), ERROR,
                            msg & ": Packet Primary Header byte " & integer'image(I) & " of chunk "
                            & integer'image(N_v), "osh_link_check_chunks");
            end loop;

            -- IV of the deterministic construction: fixed field, invocation counter + chunk number
            Iv_v := iv_fixed & std_logic_vector(unsigned(iv_count) + N_v);

            for I in 0 to 11 loop
                check_value(osh_link.rx_byte(far, vc, Head_c + I), Iv_v(95 - 8 * I downto 88 - 8 * I), ERROR,
                            msg & ": IV byte " & integer'image(I) & " of chunk " & integer'image(N_v),
                            "osh_link_check_chunks");
            end loop;

            -- AAD: the position of the chunk in bits 7:6 of its first byte, all other bits '0'
            Pos_v := osh_link.rx_byte(far, vc, Head_c + 12)(7 downto 6);
            check_value(osh_link.rx_byte(far, vc, Head_c + 12)(5 downto 0) & osh_link.rx_byte(far, vc, Head_c + 13)
                        & osh_link.rx_byte(far, vc, Head_c + 14) & osh_link.rx_byte(far, vc, Head_c + 15),
                        std_logic_vector(to_unsigned(0, 30)), ERROR, msg & ": AAD bits of chunk " & integer'image(N_v),
                        "osh_link_check_chunks");

            if N_v = 0 then
                check_value(Pos_v = "01" or Pos_v = "11", ERROR, msg & ": position of the first chunk",
                            "osh_link_check_chunks");
            else
                check_value(Pos_v = "00" or Pos_v = "10", ERROR, msg & ": position of chunk " & integer'image(N_v),
                            "osh_link_check_chunks");
            end if;

            if total_bytes > 0 then
                -- One message of total_bytes bytes: its chunks, their positions and lengths
                Want_v := "00";

                if N_v = 0 then
                    Want_v(0) := '1';
                end if;

                if N_v = Expect_c - 1 then
                    Want_v(1) := '1';
                end if;

                check_value(Pos_v, Want_v, ERROR, msg & ": position of chunk " & integer'image(N_v),
                            "osh_link_check_chunks");
                check_value(Data_v, minimum(chunk_bytes, total_bytes - minimum(total_bytes, N_v * chunk_bytes)), ERROR,
                            msg & ": bytes of chunk " & integer'image(N_v), "osh_link_check_chunks");
            else
                check_value(Data_v <= chunk_bytes, ERROR, msg & ": bytes of chunk " & integer'image(N_v),
                            "osh_link_check_chunks");
            end if;

            osh_link.pop_rx(far, vc);
            N_v := N_v + 1;
            exit when Pos_v(1) = '1' or N_v >= max_chunks;
        end loop;

        if total_bytes > 0 then
            check_value(N_v, Expect_c, ERROR, msg & ": chunks of the message", "osh_link_check_chunks");
        end if;

        log(ID_SEQUENCER, msg & ": " & integer'image(N_v) & " chunks", "osh_link_check_chunks");
        chunks := N_v;
    end procedure;

    function osh_slv_bytes (data : t_osh_byte_array) return t_slv_array is
        variable Res_v : t_slv_array(0 to data'length - 1)(7 downto 0);
    begin

        for I in 0 to data'length - 1 loop
            Res_v(I) := data(data'low + I);
        end loop;

        return Res_v;
    end function;

    function osh_axis_user (
        n     : positive;
        value : std_logic_vector) return t_user_array is
        variable Res_v : t_user_array(0 to n - 1) := (others => (others => '0'));
    begin

        for I in 0 to n - 1 loop
            Res_v(I)(value'length - 1 downto 0) := value;
        end loop;

        return Res_v;
    end function;

    function osh_samples (
        first : natural;
        n     : positive;
        bits  : positive;
        seed  : natural) return t_slv_array is
        constant W_c   : positive := 8 * ((bits + 7) / 8);
        variable Res_v : t_slv_array(0 to n - 1)(W_c - 1 downto 0) := (others => (others => '0'));
        variable S_v   : std_logic_vector(15 downto 0);
    begin

        for I in 0 to n - 1 loop
            S_v := osh_mem_byte(to_unsigned(first + I, 64), seed + 1) & osh_mem_byte(to_unsigned(first + I, 64), seed);
            Res_v(I)(minimum(bits, 16) - 1 downto 0) := S_v(minimum(bits, 16) - 1 downto 0);
        end loop;

        return Res_v;
    end function;

end package body;
