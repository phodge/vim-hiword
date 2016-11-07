Hiword
======

This is an experimental plugin to test the liveupdate feature of neovim.


Setup
-----

Install with your preferred plugin manager, and then drop something like this in your `.vimrc`:

    fun! <SID>Hiwords()
      if exists(':Hiword')
        syntax off
        Hiword Conditional if
        Hiword Conditional else
        Hiword Conditional elseif
        Hiword Statement elseif
        " and so on
      endif
    endfun
    " run Hiword commands when vim has finished loading the plugin
    au! VimEnter * call <SID>Hiwords()
    " run Hiword commands right now if they are ready (for example when the
    " user sources this file)
    call <SID>Hiwords()

Each `Hiword` command spawns a new python process using `jobstart()`. Each
python process will monitor the contents of every buffer using the live update
feature and highlighting for a single word. E.g., if you call `Hiword` with 20
different words then 20 python processes will be spawned, all of them watching
every single buffer for updates.

!!!FIXME!!!
-----------

So this tool has a pretty obvious race condition where it can receive a
LiveUpdate notification, spend some time working out the new highlights for the
line that needs changing, and then by the time it sends API calls to neovim
specifying which lines to modify hl for, the user has already added a new line
above the one that was originally changed meaning the line numbers in the API
call are all wrong. :-(

The solution is to write out the main loop logic like this:

    def mainloop():
        pending_highlights = []
        while pending_highlights or nvim.wait_for_message():
            while nvim.have_messages():
                # process any LiveUpdate messages coming in from neovim
                pending_highlights += handle_notifications()
            # lock nvim so the user can't make any buffer changes
            with nvim.lock_buffer(bufnr):
                if not nvim.have_messages():
                    # send the HL updates to neovim now
                    send_highlights(pending_highlights)
                    pending_highlights = []
