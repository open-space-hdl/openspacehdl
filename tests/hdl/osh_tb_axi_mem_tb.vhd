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
-- Testbench of osh_tb_axi_mem: INCR, FIXED and WRAP bursts, narrow transfers and strobes against the
-- backdoor, the initial test data, DECERR outside the memory, and the alerts of the AXI4 rules
-- (negative tests). A raw AXI4 driver of this bench makes the transactions, also the ones that break
-- the rules.

---------------------------------------------------------------------------------------------------
-- Libraries
---------------------------------------------------------------------------------------------------
library ieee;
    use ieee.std_logic_1164.all;
    use ieee.numeric_std.all;

library vunit_lib;
    context vunit_lib.vunit_run_context;

library uvvm_util;
    context uvvm_util.uvvm_util_context;

library osh_tb;
    use osh_tb.osh_tb_pkg.all;
    use osh_tb.osh_tb_memvar_pkg.all;

---------------------------------------------------------------------------------------------------
-- Entity
---------------------------------------------------------------------------------------------------
entity osh_tb_axi_mem_tb is
    generic (
        runner_cfg : string
    );
end entity;

---------------------------------------------------------------------------------------------------
-- Architecture
---------------------------------------------------------------------------------------------------
architecture sim of osh_tb_axi_mem_tb is

    constant Period_c : time    := 10 ns;
    constant Base_c   : natural := 16#2100#;  -- not on a 4 KB boundary: DECERR and the 4 KB rule apart
    constant Size_c   : natural := 16#2000#;
    constant Seed_c   : natural := 5;

    type WordArray_t is array (natural range <>) of std_logic_vector(31 downto 0);

    signal Clk : std_logic := '0';
    signal Rst : std_logic := '1';

    signal AwAddr  : std_logic_vector(31 downto 0) := (others => '0');
    signal AwLen   : std_logic_vector(7 downto 0)  := (others => '0');
    signal AwSize  : std_logic_vector(2 downto 0)  := (others => '0');
    signal AwBurst : std_logic_vector(1 downto 0)  := "01";
    signal AwValid : std_logic                     := '0';
    signal AwReady : std_logic;
    signal WData   : std_logic_vector(31 downto 0) := (others => '0');
    signal WStrb   : std_logic_vector(3 downto 0)  := (others => '0');
    signal WLast   : std_logic                     := '0';
    signal WValid  : std_logic                     := '0';
    signal WReady  : std_logic;
    signal BResp   : std_logic_vector(1 downto 0);
    signal BValid  : std_logic;
    signal BReady  : std_logic                     := '0';
    signal ArAddr  : std_logic_vector(31 downto 0) := (others => '0');
    signal ArLen   : std_logic_vector(7 downto 0)  := (others => '0');
    signal ArSize  : std_logic_vector(2 downto 0)  := (others => '0');
    signal ArBurst : std_logic_vector(1 downto 0)  := "01";
    signal ArValid : std_logic                     := '0';
    signal ArReady : std_logic;
    signal RData   : std_logic_vector(31 downto 0);
    signal RResp   : std_logic_vector(1 downto 0);
    signal RLast   : std_logic;
    signal RValid  : std_logic;
    signal RReady  : std_logic                     := '0';

begin

    Clk <= not Clk after Period_c / 2;

    i_dut : entity osh_tb.osh_tb_axi_mem
        generic map (
            Instance_g  => 0,
            AddrWidth_g => 32,
            DataWidth_g => 32,
            Base_g      => Base_c,
            SizeBytes_g => Size_c,
            Seed_g      => Seed_c
        )
        port map (
            Clk           => Clk,
            Rst           => Rst,
            S_Axi_AwAddr  => AwAddr,
            S_Axi_AwLen   => AwLen,
            S_Axi_AwSize  => AwSize,
            S_Axi_AwBurst => AwBurst,
            S_Axi_AwValid => AwValid,
            S_Axi_AwReady => AwReady,
            S_Axi_WData   => WData,
            S_Axi_WStrb   => WStrb,
            S_Axi_WLast   => WLast,
            S_Axi_WValid  => WValid,
            S_Axi_WReady  => WReady,
            S_Axi_BResp   => BResp,
            S_Axi_BValid  => BValid,
            S_Axi_BReady  => BReady,
            S_Axi_ArAddr  => ArAddr,
            S_Axi_ArLen   => ArLen,
            S_Axi_ArSize  => ArSize,
            S_Axi_ArBurst => ArBurst,
            S_Axi_ArValid => ArValid,
            S_Axi_ArReady => ArReady,
            S_Axi_RData   => RData,
            S_Axi_RResp   => RResp,
            S_Axi_RLast   => RLast,
            S_Axi_RValid  => RValid,
            S_Axi_RReady  => RReady
        );

    p_main : process is

        -- Write burst: one word per beat, the same strobe on every beat; lastAt: the beat (0-based) with WLast
        procedure axiWrite (
            addr   : natural;
            size   : natural;
            burst  : std_logic_vector(1 downto 0);
            data   : WordArray_t;
            strb   : std_logic_vector(3 downto 0);
            lastAt : integer;
            resp   : out std_logic_vector(1 downto 0)) is
        begin
            AwAddr  <= std_logic_vector(to_unsigned(addr, 32));
            AwLen   <= std_logic_vector(to_unsigned(data'length - 1, 8));
            AwSize  <= std_logic_vector(to_unsigned(size, 3));
            AwBurst <= burst;
            AwValid <= '1';
            wait until rising_edge(Clk) and AwReady = '1';
            AwValid <= '0';

            for N in 0 to data'length - 1 loop
                WData  <= data(data'low + N);
                WStrb  <= strb;
                WLast  <= '0';

                if N = lastAt then
                    WLast <= '1';
                end if;

                WValid <= '1';
                wait until rising_edge(Clk) and WReady = '1';
            end loop;

            WValid <= '0';
            WLast  <= '0';
            BReady <= '1';
            wait until rising_edge(Clk) and BValid = '1';
            BReady <= '0';
            resp   := BResp;
        end procedure;

        procedure axiRead (
            addr  : natural;
            beats : positive;
            size  : natural;
            burst : std_logic_vector(1 downto 0);
            data  : out WordArray_t;
            resp  : out std_logic_vector(1 downto 0)) is
        begin
            ArAddr  <= std_logic_vector(to_unsigned(addr, 32));
            ArLen   <= std_logic_vector(to_unsigned(beats - 1, 8));
            ArSize  <= std_logic_vector(to_unsigned(size, 3));
            ArBurst <= burst;
            ArValid <= '1';
            wait until rising_edge(Clk) and ArReady = '1';
            ArValid <= '0';
            RReady  <= '1';
            resp    := "00";

            for N in 0 to beats - 1 loop
                wait until rising_edge(Clk) and RValid = '1';
                data(data'low + N) := RData;
                check_value(RLast = '1', N = beats - 1, ERROR, "RLast on beat " & integer'image(N + 1));

                if RResp /= "00" then
                    resp := RResp;
                end if;

            end loop;

            RReady <= '0';
        end procedure;

        -- The memory word at addr (aligned), little-endian, through the backdoor
        impure function memWord (addr : natural) return std_logic_vector is
            variable W_v : std_logic_vector(31 downto 0);
        begin

            for B in 0 to 3 loop
                W_v(8 * B + 7 downto 8 * B) := osh_mem.read8(0, to_unsigned(addr + B, 64));
            end loop;

            return W_v;
        end function;

        impure function patWord (
            addr : natural;
            seed : natural) return std_logic_vector is
            variable W_v : std_logic_vector(31 downto 0);
        begin

            for B in 0 to 3 loop
                W_v(8 * B + 7 downto 8 * B) := osh_mem_byte(to_unsigned(addr + B, 64), seed);
            end loop;

            return W_v;
        end function;

        -- Checks that the bytes from first to last still hold the initial test data
        procedure checkUntouched (
            first : natural;
            last  : natural;
            msg   : string) is
        begin

            for A in first to last loop
                check_value(osh_mem.read8(0, to_unsigned(A, 64)), osh_mem_byte(to_unsigned(A, 64), Seed_c), ERROR,
                            msg & " 0x" & to_hstring(std_logic_vector(to_unsigned(A, 16))));
            end loop;

        end procedure;

        variable Resp_v : std_logic_vector(1 downto 0);
        variable Rd_v   : WordArray_t(0 to 15);
        variable A_v    : unsigned(63 downto 0);
        variable F_v    : unsigned(63 downto 0);

    begin
        test_runner_setup(runner, runner_cfg);
        disable_log_msg(ID_POS_ACK);

        while test_suite loop
            Rst <= '1';
            wait for 5 * Period_c;
            wait until rising_edge(Clk);
            Rst <= '0';
            osh_mem.init(0, to_unsigned(Base_c, 64), Size_c, Seed_c);

            if run("test_initial_data") then
                -- Every address bit of the memory changes the byte: 0x2555 against it with one bit inverted
                A_v := to_unsigned(Base_c + 16#555#, 64);

                for K in 0 to 12 loop
                    F_v    := A_v;
                    F_v(K) := not F_v(K);
                    check_value(osh_mem.read8(0, A_v) /= osh_mem.read8(0, F_v), ERROR,
                                "address bit " & integer'image(K));
                end loop;

                check_value(osh_mem_byte(A_v, Seed_c) /= osh_mem_byte(A_v, Seed_c + 1), ERROR,
                            "another seed gives other data");

                -- INCR read of whole bus words
                axiRead(Base_c + 16#100#, 4, 2, "01", Rd_v(0 to 3), Resp_v);
                check_value(Resp_v, "00", ERROR, "read response");

                for N in 0 to 3 loop
                    check_value(Rd_v(N), patWord(Base_c + 16#100# + 4 * N, Seed_c), ERROR,
                                "read word " & integer'image(N));
                end loop;

            elsif run("test_incr_narrow") then
                -- Six single bytes from an unaligned address: exactly these bytes change
                axiWrite(Base_c + 16#101#, 0, "01",
                         (x"000011AA", x"0022BB00", x"33CC0000", x"DD000044", x"000055EE", x"0066FF00"),
                         "1111", 5, Resp_v);
                check_value(Resp_v, "00", ERROR, "write response");
                check_value(osh_mem.read8(0, to_unsigned(Base_c + 16#101#, 64)), x"11", ERROR, "byte 0x101");
                check_value(osh_mem.read8(0, to_unsigned(Base_c + 16#102#, 64)), x"22", ERROR, "byte 0x102");
                check_value(osh_mem.read8(0, to_unsigned(Base_c + 16#103#, 64)), x"33", ERROR, "byte 0x103");
                check_value(osh_mem.read8(0, to_unsigned(Base_c + 16#104#, 64)), x"44", ERROR, "byte 0x104");
                check_value(osh_mem.read8(0, to_unsigned(Base_c + 16#105#, 64)), x"55", ERROR, "byte 0x105");
                check_value(osh_mem.read8(0, to_unsigned(Base_c + 16#106#, 64)), x"66", ERROR, "byte 0x106");
                checkUntouched(Base_c + 16#0F0#, Base_c + 16#100#, "before the burst");
                checkUntouched(Base_c + 16#107#, Base_c + 16#117#, "after the burst");
                axiRead(Base_c + 16#100#, 2, 2, "01", Rd_v(0 to 1), Resp_v);
                check_value(Rd_v(0)(31 downto 8), x"332211", ERROR, "read back word 0");
                check_value(Rd_v(1)(23 downto 0), x"665544", ERROR, "read back word 1");

            elsif run("test_strobes") then
                axiWrite(Base_c + 16#200#, 2, "01", (0 => x"A1B2C3D4"), "0101", 0, Resp_v);
                check_value(memWord(Base_c + 16#200#)(7 downto 0), x"D4", ERROR, "lane 0 written");
                check_value(memWord(Base_c + 16#200#)(23 downto 16), x"B2", ERROR, "lane 2 written");
                check_value(memWord(Base_c + 16#200#)(15 downto 8), patWord(Base_c + 16#200#, Seed_c)(15 downto 8),
                            ERROR, "lane 1 kept");
                check_value(memWord(Base_c + 16#200#)(31 downto 24), patWord(Base_c + 16#200#, Seed_c)(31 downto 24),
                            ERROR, "lane 3 kept");

            elsif run("test_fixed") then
                axiWrite(Base_c + 16#300#, 2, "00", (x"01010101", x"02020202", x"03030303", x"04040404"),
                         "1111", 3, Resp_v);
                check_value(memWord(Base_c + 16#300#), x"04040404", ERROR, "FIXED: the last beat stays");
                checkUntouched(Base_c + 16#304#, Base_c + 16#313#, "after a FIXED burst");
                axiRead(Base_c + 16#300#, 3, 2, "00", Rd_v(0 to 2), Resp_v);

                for N in 0 to 2 loop
                    check_value(Rd_v(N), x"04040404", ERROR, "FIXED read beat " & integer'image(N));
                end loop;

            elsif run("test_wrap") then
                -- WRAP of 4 words from the third word of a 16-byte block: 0x408, 0x40C, 0x400, 0x404
                axiWrite(Base_c + 16#408#, 2, "10", (x"00000003", x"00000004", x"00000001", x"00000002"),
                         "1111", 3, Resp_v);
                axiRead(Base_c + 16#400#, 4, 2, "01", Rd_v(0 to 3), Resp_v);

                for N in 0 to 3 loop
                    check_value(Rd_v(N), std_logic_vector(to_unsigned(N + 1, 32)), ERROR,
                                "WRAP word " & integer'image(N));
                end loop;

                checkUntouched(Base_c + 16#410#, Base_c + 16#41F#, "after the wrap block");
                axiRead(Base_c + 16#40C#, 4, 2, "10", Rd_v(0 to 3), Resp_v);
                check_value(Rd_v(1), x"00000001", ERROR, "WRAP read wraps to the block start");

            elsif run("test_decerr") then
                -- Below the base and across the end: DECERR, nothing written
                axiWrite(Base_c - 4, 2, "01", (x"FFFFFFFF", x"EEEEEEEE"), "1111", 1, Resp_v);
                check_value(Resp_v, "11", ERROR, "write across the base: DECERR");
                checkUntouched(Base_c, Base_c + 7, "a refused write writes nothing");
                axiRead(Base_c + Size_c - 4, 2, 2, "01", Rd_v(0 to 1), Resp_v);
                check_value(Resp_v, "11", ERROR, "read across the end: DECERR");
                check_value(osh_mem.contains(0, to_unsigned(Base_c + Size_c, 64)), false, ERROR, "end of the memory");

            elsif run("test_wlast_alert") then
                -- WLast on the first of two beats: one alert for that beat, one for the last beat without it
                increment_expected_alerts_and_stop_limit(TB_ERROR, 2);
                axiWrite(Base_c + 16#500#, 2, "01", (x"11111111", x"22222222"), "1111", 0, Resp_v);

            elsif run("test_4k_alert") then
                increment_expected_alerts_and_stop_limit(TB_ERROR, 1);
                -- 0x2FF8 to 0x3003 inside the memory, across the 4 KB boundary 0x3000
                axiWrite(16#2FF8#, 2, "01", (x"11111111", x"22222222", x"33333333"), "1111", 2, Resp_v);

            elsif run("test_wrap_alert") then
                increment_expected_alerts_and_stop_limit(TB_ERROR, 1);
                axiRead(Base_c + 16#600#, 3, 2, "10", Rd_v(0 to 2), Resp_v);
            end if;

        end loop;

        osh_test_end(runner);
    end process;

end architecture;
