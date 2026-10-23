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
-- Package of the bench components of openspacehdl (library osh_tb): the command and result records of
-- the RMAP initiator of the far ends, the procedures of the generated smoke test (RMAP commands, link
-- up, test end) and the address-dependent test data of the memory responder osh_tb_axi_mem.
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

library uvvm_vvc_framework;
    use uvvm_vvc_framework.ti_vvc_framework_support_pkg.all;

library vunit_lib;
    context vunit_lib.vunit_run_context;

---------------------------------------------------------------------------------------------------
-- Package Header
---------------------------------------------------------------------------------------------------
package osh_tb_pkg is

    -- Most data bytes of one RMAP command of the far ends
    constant C_OSH_RMAP_MAX_BYTES : positive := 64;

    type t_osh_byte_array is array (natural range <>) of std_logic_vector(7 downto 0);
    subtype t_osh_rmap_data is t_osh_byte_array(0 to C_OSH_RMAP_MAX_BYTES - 1);

    -- Command to the RMAP initiator of a far end. A change of Req starts the command; Write selects a
    -- verified write with reply (instruction command field "1111"), else an incrementing read with
    -- reply ("0011"); Len data bytes of Data are written, or Len bytes are read.
    type t_osh_rmap_cmd is record
        Req   : std_logic;
        Write : std_logic;
        Tla   : std_logic_vector(7 downto 0);
        Key   : std_logic_vector(7 downto 0);
        Addr  : std_logic_vector(39 downto 0);
        Len   : natural range 0 to C_OSH_RMAP_MAX_BYTES;
        Data  : t_osh_rmap_data;
    end record;

    -- Result of a command: Ack takes the value of Req when the command is complete. Status is the
    -- status of the reply, Error the local error of the initiator (0 none, 1 data error, 2 timeout, 3
    -- Transaction Identifier in use), Len and Data the data bytes of a read reply.
    type t_osh_rmap_res is record
        Ack    : std_logic;
        Status : std_logic_vector(7 downto 0);
        Error  : natural range 0 to 3;
        Len    : natural range 0 to C_OSH_RMAP_MAX_BYTES;
        Data   : t_osh_rmap_data;
    end record;

    -- The commands and results of the far ends of a system, one element per far end
    type t_osh_rmap_cmd_array is array (natural range <>) of t_osh_rmap_cmd;
    type t_osh_rmap_res_array is array (natural range <>) of t_osh_rmap_res;

    constant C_OSH_RMAP_CMD_IDLE : t_osh_rmap_cmd := (
        Req   => '0',
        Write => '0',
        Tla   => x"FE",
        Key   => x"00",
        Addr  => (others => '0'),
        Len   => 0,
        Data  => (others => x"00")
    );

    constant C_OSH_RMAP_RES_IDLE : t_osh_rmap_res := (
        Ack    => '0',
        Status => x"00",
        Error  => 0,
        Len    => 0,
        Data   => (others => x"00")
    );

    -- Time a far end may take for one command, from the request to the result (the reply timeout
    -- of its initiator is 1 ms)
    constant C_OSH_RMAP_TIMEOUT : time := 2 ms;

    -- Sends a command to a far end and waits for its result. When no result arrives within timeout,
    -- the procedure raises a TB_ERROR alert and returns result with Error 2.
    procedure osh_rmap_transfer (
        signal   cmd     : inout t_osh_rmap_cmd;
        signal   res     : in    t_osh_rmap_res;
        constant write   : in    boolean;
        constant tla     : in    std_logic_vector(7 downto 0);
        constant key     : in    std_logic_vector(7 downto 0);
        constant addr    : in    unsigned;
        constant data    : in    t_osh_byte_array;
        constant len     : in    natural;
        variable result  : out   t_osh_rmap_res;
        constant msg     : in    string;
        constant timeout : in    time := C_OSH_RMAP_TIMEOUT);

    -- Writes data with RMAP and checks that the reply has the status expected and no local error
    procedure osh_rmap_write (
        signal   cmd      : inout t_osh_rmap_cmd;
        signal   res      : in    t_osh_rmap_res;
        constant tla      : in    std_logic_vector(7 downto 0);
        constant key      : in    std_logic_vector(7 downto 0);
        constant addr     : in    unsigned;
        constant data     : in    t_osh_byte_array;
        constant msg      : in    string;
        constant expected : in    std_logic_vector(7 downto 0) := x"00");

    -- Reads len bytes with RMAP and checks that the reply has the status expected, no local error and
    -- len data bytes
    procedure osh_rmap_read (
        signal   cmd      : inout t_osh_rmap_cmd;
        signal   res      : in    t_osh_rmap_res;
        constant tla      : in    std_logic_vector(7 downto 0);
        constant key      : in    std_logic_vector(7 downto 0);
        constant addr     : in    unsigned;
        constant len      : in    natural;
        variable data     : out   t_osh_byte_array;
        constant msg      : in    string;
        constant expected : in    std_logic_vector(7 downto 0) := x"00");

    -- Reads a 32-bit register with RMAP (4 bytes, the first from the lowest address) and checks the
    -- status 0 and the value
    procedure osh_rmap_check_word (
        signal   cmd   : inout t_osh_rmap_cmd;
        signal   res   : in    t_osh_rmap_res;
        constant tla   : in    std_logic_vector(7 downto 0);
        constant key   : in    std_logic_vector(7 downto 0);
        constant addr  : in    unsigned;
        constant value : in    std_logic_vector(31 downto 0);
        constant msg   : in    string);

    -- Waits until a far end reports its link up; a TB_ERROR alert when it does not within timeout
    procedure osh_await_link_up (
        signal   up      : in std_logic;
        constant timeout : in time;
        constant msg     : in string);

    -- Start of a test case of a system testbench: waits for the UVVM engine of the VVCs, turns off the
    -- log of positive checks, and turns off the warning that UVVM raises once when a time stamp of the
    -- log has more decimals than it shows. Clocks whose period is not a whole number of tenths of a
    -- nanosecond (the 156.25 MHz lane clock of SpaceFibre) cause that warning; it concerns the format of
    -- the log only, and osh_test_end would count it as an unexpected alert.
    procedure osh_test_start;

    -- End of a test case: reports the alert counters, fails the simulation (severity failure) when they
    -- differ from the expected alerts (an unexpected alert, or an expected one that did not occur) and
    -- ends the test with VUnit
    procedure osh_test_end (signal runner : inout runner_sync_t);

    -- Test data of a memory byte: a CRC-8 (polynomial x^8 + x^2 + x + 1) over seed and the 64-bit
    -- address. Two addresses that differ in one bit always give different values, so the data repeats
    -- with no address period; another seed gives another pattern.
    function osh_mem_byte (
        addr : unsigned;
        seed : natural) return std_logic_vector;

    -- n bytes of test data from addr on
    function osh_mem_bytes (
        addr : unsigned;
        n    : natural;
        seed : natural) return t_osh_byte_array;

end package;

---------------------------------------------------------------------------------------------------
-- Package Body
---------------------------------------------------------------------------------------------------
package body osh_tb_pkg is

    procedure osh_rmap_transfer (
        signal   cmd     : inout t_osh_rmap_cmd;
        signal   res     : in    t_osh_rmap_res;
        constant write   : in    boolean;
        constant tla     : in    std_logic_vector(7 downto 0);
        constant key     : in    std_logic_vector(7 downto 0);
        constant addr    : in    unsigned;
        constant data    : in    t_osh_byte_array;
        constant len     : in    natural;
        variable result  : out   t_osh_rmap_res;
        constant msg     : in    string;
        constant timeout : in    time := C_OSH_RMAP_TIMEOUT) is
        variable Cmd_v : t_osh_rmap_cmd;
        variable Res_v : t_osh_rmap_res;
    begin
        check_value(len <= C_OSH_RMAP_MAX_BYTES, TB_FAILURE, "at most " & integer'image(C_OSH_RMAP_MAX_BYTES)
                                                                & " bytes per RMAP command", "osh_rmap_transfer");
        Cmd_v       := cmd;
        Cmd_v.Req   := not cmd.Req;
        Cmd_v.Write := '0';

        if write then
            Cmd_v.Write := '1';
        end if;

        Cmd_v.Tla   := tla;
        Cmd_v.Key   := key;
        Cmd_v.Addr  := std_logic_vector(resize(addr, 40));
        Cmd_v.Len   := len;
        Cmd_v.Data  := (others => x"00");

        if write then

            for I in 0 to len - 1 loop
                Cmd_v.Data(I) := data(data'low + I);
            end loop;

        end if;

        cmd <= Cmd_v;
        wait until res.Ack = Cmd_v.Req for timeout;

        if res.Ack /= Cmd_v.Req then
            alert(TB_ERROR, msg & ": no result from the far end within " & to_string(timeout), "osh_rmap_transfer");
            Res_v       := C_OSH_RMAP_RES_IDLE;
            Res_v.Error := 2;
            result      := Res_v;
        else
            result := res;
        end if;

    end procedure;

    procedure osh_rmap_write (
        signal   cmd      : inout t_osh_rmap_cmd;
        signal   res      : in    t_osh_rmap_res;
        constant tla      : in    std_logic_vector(7 downto 0);
        constant key      : in    std_logic_vector(7 downto 0);
        constant addr     : in    unsigned;
        constant data     : in    t_osh_byte_array;
        constant msg      : in    string;
        constant expected : in    std_logic_vector(7 downto 0) := x"00") is
        variable Res_v : t_osh_rmap_res;
    begin
        osh_rmap_transfer(cmd, res, true, tla, key, addr, data, data'length, Res_v, msg);
        check_value(Res_v.Error, 0, ERROR, msg & ": local error of the initiator", "osh_rmap_write");
        check_value(Res_v.Status, expected, ERROR, msg & ": status of the write reply", "osh_rmap_write");
    end procedure;

    procedure osh_rmap_read (
        signal   cmd      : inout t_osh_rmap_cmd;
        signal   res      : in    t_osh_rmap_res;
        constant tla      : in    std_logic_vector(7 downto 0);
        constant key      : in    std_logic_vector(7 downto 0);
        constant addr     : in    unsigned;
        constant len      : in    natural;
        variable data     : out   t_osh_byte_array;
        constant msg      : in    string;
        constant expected : in    std_logic_vector(7 downto 0) := x"00") is
        variable Res_v  : t_osh_rmap_res;
        variable None_v : t_osh_byte_array(0 to 0) := (others => x"00");
    begin
        osh_rmap_transfer(cmd, res, false, tla, key, addr, None_v, len, Res_v, msg);
        check_value(Res_v.Error, 0, ERROR, msg & ": local error of the initiator", "osh_rmap_read");
        check_value(Res_v.Status, expected, ERROR, msg & ": status of the read reply", "osh_rmap_read");

        if expected = x"00" then
            check_value(Res_v.Len, len, ERROR, msg & ": data bytes of the read reply", "osh_rmap_read");
        end if;

        for I in 0 to len - 1 loop
            data(data'low + I) := Res_v.Data(I);
        end loop;

    end procedure;

    procedure osh_rmap_check_word (
        signal   cmd   : inout t_osh_rmap_cmd;
        signal   res   : in    t_osh_rmap_res;
        constant tla   : in    std_logic_vector(7 downto 0);
        constant key   : in    std_logic_vector(7 downto 0);
        constant addr  : in    unsigned;
        constant value : in    std_logic_vector(31 downto 0);
        constant msg   : in    string) is
        variable Data_v : t_osh_byte_array(0 to 3);
        variable Word_v : std_logic_vector(31 downto 0);
    begin
        osh_rmap_read(cmd, res, tla, key, addr, 4, Data_v, msg);
        Word_v := Data_v(3) & Data_v(2) & Data_v(1) & Data_v(0);
        check_value(Word_v, value, ERROR, msg, "osh_rmap_check_word");
    end procedure;

    procedure osh_await_link_up (
        signal   up      : in std_logic;
        constant timeout : in time;
        constant msg     : in string) is
    begin

        if up /= '1' then
            wait until up = '1' for timeout;
        end if;

        if up /= '1' then
            alert(TB_ERROR, msg & ": link not up within " & to_string(timeout), "osh_await_link_up");
        else
            log(ID_SEQUENCER, msg & ": link up", "osh_await_link_up");
        end if;

    end procedure;

    procedure osh_test_start is
    begin
        await_uvvm_initialization(VOID);
        disable_log_msg(ID_POS_ACK);
        shared_warned_time_stamp_trunc := true;
    end procedure;

    procedure osh_test_end (signal runner : inout runner_sync_t) is
        variable Mismatch_v : boolean := false;
    begin
        report_alert_counters(FINAL);

        -- The end status of UVVM (shared_uvvm_status) is not used: a test end that signals a mismatch with
        -- alert(TB_ERROR) cannot stop a test that raised the TB_ERROR stop limit (a negative test with
        -- increment_expected_alerts_and_stop_limit), and VUnit then passes it. The counters are compared here,
        -- and a mismatch ends the simulation with severity failure.
        for L in WARNING to TB_FAILURE loop

            if L /= MANUAL_CHECK and get_alert_counter(L, REGARD) /= get_alert_counter(L, EXPECT) then
                Mismatch_v := true;
                log(ID_SEQUENCER, t_alert_level'image(L) & ": " & integer'image(get_alert_counter(L, REGARD))
                                  & " alerts, " & integer'image(get_alert_counter(L, EXPECT)) & " expected",
                    "osh_test_end");
            end if;

        end loop;

        -- A failure ends the simulation, whatever the stop limits of the test
        assert not Mismatch_v
            report "osh_test_end: the alerts of the test differ from the expected alerts (summary above)"
            severity failure;
        test_runner_cleanup(runner);
    end procedure;

    function osh_mem_byte (
        addr : unsigned;
        seed : natural) return std_logic_vector is
        constant Msg_c : unsigned(71 downto 0) := resize(addr, 64) & to_unsigned(seed mod 256, 8);
        variable Crc_v : std_logic_vector(7 downto 0) := x"FF";
        variable Fb_v  : std_logic;
    begin

        for I in Msg_c'high downto 0 loop
            Fb_v  := Crc_v(7) xor Msg_c(I);
            Crc_v := Crc_v(6 downto 0) & '0';

            if Fb_v = '1' then
                Crc_v := Crc_v xor x"07";
            end if;

        end loop;

        return Crc_v;
    end function;

    function osh_mem_bytes (
        addr : unsigned;
        n    : natural;
        seed : natural) return t_osh_byte_array is
        variable Res_v : t_osh_byte_array(0 to n - 1);
    begin

        for I in 0 to n - 1 loop
            Res_v(I) := osh_mem_byte(resize(addr, 64) + I, seed);
        end loop;

        return Res_v;
    end function;

end package body;
