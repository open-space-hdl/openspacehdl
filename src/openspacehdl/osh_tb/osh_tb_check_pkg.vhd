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
-- Checks of the generated smoke test that need the memory of osh_tb_axi_mem: the RMAP memory check of
-- an RMAP target whose memory interface is external.
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
-- Package Header
---------------------------------------------------------------------------------------------------
package osh_tb_check_pkg is

    -- Bytes of the memory check and of the neighbours checked on each side
    constant C_OSH_MEM_CHECK_BYTES : positive := 16;

    -- Memory check over RMAP of a target whose memory is the osh_tb_axi_mem instance mem (initial data of
    -- the seed fill): writes C_OSH_MEM_CHECK_BYTES bytes of osh_mem_bytes(addr, n, seed) at addr with RMAP
    -- and reads them back with RMAP; through the backdoor, the window must hold them and the
    -- C_OSH_MEM_CHECK_BYTES bytes before and after it must still hold the initial data. The values depend
    -- on every address bit; seed must differ from fill. The smoke test starts the window 4 bytes before a
    -- 4 KB boundary, so the target has to split its burst there.
    procedure osh_rmap_memory_check (
        signal   cmd  : inout t_osh_rmap_cmd;
        signal   res  : in    t_osh_rmap_res;
        constant tla  : in    std_logic_vector(7 downto 0);
        constant key  : in    std_logic_vector(7 downto 0);
        constant addr : in    unsigned;
        constant mem  : in    natural;
        constant fill : in    natural;
        constant seed : in    natural;
        constant msg  : in    string);

end package;

---------------------------------------------------------------------------------------------------
-- Package Body
---------------------------------------------------------------------------------------------------
package body osh_tb_check_pkg is

    procedure osh_rmap_memory_check (
        signal   cmd  : inout t_osh_rmap_cmd;
        signal   res  : in    t_osh_rmap_res;
        constant tla  : in    std_logic_vector(7 downto 0);
        constant key  : in    std_logic_vector(7 downto 0);
        constant addr : in    unsigned;
        constant mem  : in    natural;
        constant fill : in    natural;
        constant seed : in    natural;
        constant msg  : in    string) is
        constant N_c    : positive                         := C_OSH_MEM_CHECK_BYTES;
        constant A_c    : unsigned(63 downto 0)            := resize(addr, 64);
        constant Data_c : t_osh_byte_array(0 to N_c - 1) := osh_mem_bytes(A_c, N_c, seed);
        variable Rd_v   : t_osh_byte_array(0 to N_c - 1);
        variable B_v    : unsigned(63 downto 0);
    begin
        check_value(seed /= fill, TB_FAILURE, msg & ": the data must differ from the initial data",
                    "osh_rmap_memory_check");
        osh_rmap_write(cmd, res, tla, key, addr, Data_c, msg & ": write");
        osh_rmap_read(cmd, res, tla, key, addr, N_c, Rd_v, msg & ": read back");

        for I in 0 to N_c - 1 loop
            check_value(Rd_v(I), Data_c(I), ERROR, msg & ": read back byte " & integer'image(I),
                        "osh_rmap_memory_check");
            check_value(osh_mem.read8(mem, A_c + I), Data_c(I), ERROR, msg & ": memory byte " & integer'image(I),
                        "osh_rmap_memory_check");
            B_v := A_c - N_c + I;
            check_value(osh_mem.read8(mem, B_v), osh_mem_byte(B_v, fill), ERROR,
                        msg & ": byte " & integer'image(N_c - I) & " before the window unchanged",
                        "osh_rmap_memory_check");
            B_v := A_c + N_c + I;
            check_value(osh_mem.read8(mem, B_v), osh_mem_byte(B_v, fill), ERROR,
                        msg & ": byte " & integer'image(I + 1) & " after the window unchanged",
                        "osh_rmap_memory_check");
        end loop;

    end procedure;

end package body;
