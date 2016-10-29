Hiword
======

This is an experimental plugin to test the liveupdate feature of neovim.

Use it like this:

    au! VimEnter * if exists(':Hiword') | call <SID>Hiwords() | endif
    fun! <SID>Hiwords()
      syntax off
      Hiword Conditional if
      Hiword Conditional else
      Hiword Conditional elseif
      Hiword Statement elseif
      " and so on
    endfun

Each `Hiword` command creates a new python helper which will monitor the
contents of every buffer and highlight just the given word.
