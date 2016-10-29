Hiword
======

This is an experimental plugin to test the liveupdate feature of neovim.

Install with your preferred plugin manager, and then drop something like this in your `.vimrc`:

    au! VimEnter * if exists(':Hiword') | call <SID>Hiwords() | endif
    fun! <SID>Hiwords()
      syntax off
      Hiword Conditional if
      Hiword Conditional else
      Hiword Conditional elseif
      Hiword Statement elseif
      " and so on
    endfun

Each `Hiword` command spawns a new python process using `jobstart()`. Each
python process will monitor the contents of every buffer using the live update
feature and highlighting for a single word. E.g., if you call `Hiword` with 20
different words then 20 python processes will be spawned, all of them watching
every single buffer for updates.
