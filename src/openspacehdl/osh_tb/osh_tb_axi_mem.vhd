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
-- AXI4 memory responder of the system testbenches: the slave at an external AXI4 master interface of
-- the system (for example the memory interface of an RMAP target). It serves the write and the read
-- channels independently, one transaction per channel at a time, with INCR, FIXED and WRAP bursts,
-- narrow transfers and byte strobes. Its memory covers SizeBytes_g bytes from Base_g on and starts
-- with osh_mem_byte(address, Seed_g); an access to any byte outside answers DECERR (no byte is
-- written). The testbench reaches the memory through the shared variable osh_mem
-- (osh_tb_memvar_pkg, index Instance_g). A burst that breaks the AXI4 rules raises a TB_ERROR alert:
-- WLast on another beat than the last, an INCR burst that crosses a 4 KB boundary, a WRAP burst of
-- another length than 2, 4, 8 or 16 beats or with an unaligned address, and a beat size wider than
-- the bus.
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

library work;
    use work.osh_tb_pkg.all;
    use work.osh_tb_memvar_pkg.all;

---------------------------------------------------------------------------------------------------
-- Entity
---------------------------------------------------------------------------------------------------
entity osh_tb_axi_mem is
    generic (
        Instance_g     : natural range 0 to 7 := 0;
        AddrWidth_g    : positive range 12 to 64 := 32;
        DataWidth_g    : positive              := 32;     -- 8 to 1024, a power of two
        Base_g         : natural               := 0;
        SizeBytes_g    : positive              := 16384;
        Seed_g         : natural               := 1;
        ReadLatency_g  : natural               := 2;      -- cycles from the address to the first read beat
        WriteLatency_g : natural               := 2       -- cycles from the last write beat to the response
    );
    port (
        Clk           : in    std_logic;
        Rst           : in    std_logic;
        S_Axi_AwAddr  : in    std_logic_vector(AddrWidth_g - 1 downto 0);
        S_Axi_AwLen   : in    std_logic_vector(7 downto 0);
        S_Axi_AwSize  : in    std_logic_vector(2 downto 0);
        S_Axi_AwBurst : in    std_logic_vector(1 downto 0);
        S_Axi_AwValid : in    std_logic;
        S_Axi_AwReady : out   std_logic := '0';
        S_Axi_WData   : in    std_logic_vector(DataWidth_g - 1 downto 0);
        S_Axi_WStrb   : in    std_logic_vector(DataWidth_g / 8 - 1 downto 0);
        S_Axi_WLast   : in    std_logic;
        S_Axi_WValid  : in    std_logic;
        S_Axi_WReady  : out   std_logic := '0';
        S_Axi_BResp   : out   std_logic_vector(1 downto 0) := "00";
        S_Axi_BValid  : out   std_logic := '0';
        S_Axi_BReady  : in    std_logic;
        S_Axi_ArAddr  : in    std_logic_vector(AddrWidth_g - 1 downto 0);
        S_Axi_ArLen   : in    std_logic_vector(7 downto 0);
        S_Axi_ArSize  : in    std_logic_vector(2 downto 0);
        S_Axi_ArBurst : in    std_logic_vector(1 downto 0);
        S_Axi_ArValid : in    std_logic;
        S_Axi_ArReady : out   std_logic := '0';
        S_Axi_RData   : out   std_logic_vector(DataWidth_g - 1 downto 0) := (others => '0');
        S_Axi_RResp   : out   std_logic_vector(1 downto 0) := "00";
        S_Axi_RLast   : out   std_logic := '0';
        S_Axi_RValid  : out   std_logic := '0';
        S_Axi_RReady  : in    std_logic
    );
end entity;

---------------------------------------------------------------------------------------------------
-- Architecture
---------------------------------------------------------------------------------------------------
architecture sim of osh_tb_axi_mem is

    constant Bytes_c : positive := DataWidth_g / 8;
    constant Scope_c : string   := "osh_tb_axi_mem(" & integer'image(Instance_g) & ")";
    constant Okay_c  : std_logic_vector(1 downto 0) := "00";
    constant DecErr_c : std_logic_vector(1 downto 0) := "11";

    subtype Addr_t is unsigned(63 downto 0);

    function isPow2 (n : positive) return boolean is
        variable P_v : positive := 1;
    begin

        while P_v < n loop
            P_v := 2 * P_v;
        end loop;

        return P_v = n;
    end function;

    -- a rounded down to a multiple of n (a / n * n of numeric_std would have twice the width of a)
    function align (
        a : Addr_t;
        n : positive) return Addr_t is
    begin
        return a - (a mod n);
    end function;

    function hex (a : Addr_t) return string is
    begin
        return to_hstring(std_logic_vector(a));
    end function;

    -- Address of beat n (0 = first) of a burst, AXI4 rules (ARM IHI 0022, A3.4.1)
    function beatAddr (
        start : Addr_t;
        len   : natural;
        size  : natural;
        burst : std_logic_vector(1 downto 0);
        n     : natural) return Addr_t is
        constant Num_c     : natural := 2 ** size;
        constant Aligned_c : Addr_t  := align(start, Num_c);
        constant Total_c   : natural := Num_c * (len + 1);
        variable Low_v     : Addr_t;
        variable A_v       : Addr_t;
    begin

        if n = 0 or burst = "00" then
            return start;
        end if;

        A_v := Aligned_c + to_unsigned(n * Num_c, 64);

        if burst = "10" then
            Low_v := align(start, Total_c);

            if A_v >= Low_v + Total_c then
                A_v := A_v - Total_c;
            end if;

        end if;

        return A_v;
    end function;

    -- Checks of a burst against the AXI4 rules; true when every byte of it is in the memory
    impure function checkBurst (
        start : Addr_t;
        len   : natural;
        size  : natural;
        burst : std_logic_vector(1 downto 0);
        what  : string) return boolean is
        constant Num_c  : natural := 2 ** size;
        variable Last_v : Addr_t;
        variable Ok_v   : boolean := true;
        variable A_v    : Addr_t;
    begin

        if Num_c > Bytes_c then
            alert(TB_ERROR, what & ": beat size " & integer'image(Num_c) & " bytes on a bus of "
                            & integer'image(Bytes_c), Scope_c);
        end if;

        if burst = "01" then
            Last_v := align(start, Num_c) + to_unsigned(Num_c * (len + 1) - 1, 64);

            if start(63 downto 12) /= Last_v(63 downto 12) then
                alert(TB_ERROR, what & ": INCR burst from 0x" & hex(start) & " crosses a 4 KB boundary",
                      Scope_c);
            end if;

        elsif burst = "10" then

            if not (len = 1 or len = 3 or len = 7 or len = 15) then
                alert(TB_ERROR, what & ": WRAP burst of " & integer'image(len + 1) & " beats", Scope_c);
            end if;

            if start mod Num_c /= 0 then
                alert(TB_ERROR, what & ": WRAP burst at the unaligned address 0x" & hex(start), Scope_c);
            end if;

        elsif burst = "11" then
            alert(TB_ERROR, what & ": reserved burst type", Scope_c);
        end if;

        for N in 0 to len loop
            A_v := beatAddr(start, len, size, burst, N);

            for B in 0 to Num_c - 1 loop

                if not osh_mem.contains(Instance_g, align(A_v, Num_c) + B) then
                    Ok_v := false;
                end if;

            end loop;

        end loop;

        return Ok_v;
    end function;

begin

    -- Generics checked at elaboration
    assert DataWidth_g >= 8 and DataWidth_g <= 1024 and isPow2(DataWidth_g)
        report Scope_c & ": DataWidth_g must be a power of two from 8 to 1024"
        severity failure;

    p_init : process is
    begin
        osh_mem.init(Instance_g, to_unsigned(Base_g, 64), SizeBytes_g, Seed_g);
        wait;
    end process;

    -----------------------------------------------------------------------------------------------
    -- Write channel
    -----------------------------------------------------------------------------------------------
    p_write : process is
        variable Start_v : Addr_t;
        variable Len_v   : natural;
        variable Size_v  : natural;
        variable Burst_v : std_logic_vector(1 downto 0);
        variable Ok_v    : boolean;
        variable A_v     : Addr_t;
        variable Lane_v  : natural;
        variable Low_v   : natural;
        variable High_v  : natural;
    begin
        S_Axi_AwReady <= '0';
        S_Axi_WReady  <= '0';
        S_Axi_BValid  <= '0';

        loop
            -- Address
            S_Axi_AwReady <= '1';
            wait until rising_edge(Clk) and S_Axi_AwValid = '1' and Rst = '0';
            S_Axi_AwReady <= '0';
            Start_v       := resize(unsigned(S_Axi_AwAddr), 64);
            Len_v         := to_integer(unsigned(S_Axi_AwLen));
            Size_v        := to_integer(unsigned(S_Axi_AwSize));
            Burst_v       := S_Axi_AwBurst;
            Ok_v          := checkBurst(Start_v, Len_v, Size_v, Burst_v, "write");

            -- Data beats
            S_Axi_WReady <= '1';

            for N in 0 to Len_v loop
                wait until rising_edge(Clk) and S_Axi_WValid = '1';

                if (S_Axi_WLast = '1') /= (N = Len_v) then
                    alert(TB_ERROR, "write from 0x" & hex(Start_v) & ": WLast " & std_logic'image(S_Axi_WLast)
                                    & " on beat " & integer'image(N + 1) & " of " & integer'image(Len_v + 1), Scope_c);
                end if;

                A_v    := beatAddr(Start_v, Len_v, Size_v, Burst_v, N);
                Low_v  := to_integer(A_v mod Bytes_c);
                High_v := to_integer(align(A_v, 2 ** Size_v) mod Bytes_c) + 2 ** Size_v - 1;

                if Ok_v then

                    for L in Low_v to minimum(High_v, Bytes_c - 1) loop
                        Lane_v := L;

                        if S_Axi_WStrb(Lane_v) = '1' then
                            osh_mem.write8(Instance_g, align(A_v, Bytes_c) + Lane_v,
                                           S_Axi_WData(8 * Lane_v + 7 downto 8 * Lane_v));
                        end if;

                    end loop;

                end if;

            end loop;

            S_Axi_WReady <= '0';

            -- Response
            for I in 1 to WriteLatency_g loop
                wait until rising_edge(Clk);
            end loop;

            S_Axi_BResp <= DecErr_c;

            if Ok_v then
                S_Axi_BResp <= Okay_c;
            end if;

            S_Axi_BValid <= '1';
            wait until rising_edge(Clk) and S_Axi_BReady = '1';
            S_Axi_BValid <= '0';
        end loop;

    end process;

    -----------------------------------------------------------------------------------------------
    -- Read channel
    -----------------------------------------------------------------------------------------------
    p_read : process is
        variable Start_v : Addr_t;
        variable Len_v   : natural;
        variable Size_v  : natural;
        variable Burst_v : std_logic_vector(1 downto 0);
        variable Ok_v    : boolean;
        variable A_v     : Addr_t;
        variable Word_v  : std_logic_vector(DataWidth_g - 1 downto 0);
    begin
        S_Axi_ArReady <= '0';
        S_Axi_RValid  <= '0';
        S_Axi_RLast   <= '0';

        loop
            S_Axi_ArReady <= '1';
            wait until rising_edge(Clk) and S_Axi_ArValid = '1' and Rst = '0';
            S_Axi_ArReady <= '0';
            Start_v       := resize(unsigned(S_Axi_ArAddr), 64);
            Len_v         := to_integer(unsigned(S_Axi_ArLen));
            Size_v        := to_integer(unsigned(S_Axi_ArSize));
            Burst_v       := S_Axi_ArBurst;
            Ok_v          := checkBurst(Start_v, Len_v, Size_v, Burst_v, "read");

            for I in 1 to ReadLatency_g loop
                wait until rising_edge(Clk);
            end loop;

            for N in 0 to Len_v loop
                A_v := beatAddr(Start_v, Len_v, Size_v, Burst_v, N);

                -- The whole bus word of the beat; the master takes the lanes of the transfer
                for L in 0 to Bytes_c - 1 loop
                    Word_v(8 * L + 7 downto 8 * L) := osh_mem.read8(Instance_g, align(A_v, Bytes_c) + L);
                end loop;

                S_Axi_RData <= Word_v;
                S_Axi_RResp <= DecErr_c;
                S_Axi_RLast <= '0';

                if Ok_v then
                    S_Axi_RResp <= Okay_c;
                end if;

                if N = Len_v then
                    S_Axi_RLast <= '1';
                end if;

                S_Axi_RValid <= '1';
                wait until rising_edge(Clk) and S_Axi_RReady = '1';
            end loop;

            S_Axi_RValid <= '0';
            S_Axi_RLast  <= '0';
        end loop;

    end process;

end architecture;
