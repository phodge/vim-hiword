#!/usr/bin/env python3
import os
import re
from functools import partial

import neovim


MYREGEX = None
SOURCEID = 0
HLGROUP = None
BUFFERS = {}


class BufferInfo(object):
    def __init__(self, nbuf, bufnr):
        self.nbuf = nbuf
        self.bufnr = bufnr
        self.lines = []
        self.locked = False
        self.pending = {}
        self.pushing = False
        self.pushbroken = False

    def flaglines(self, firstline, numremoved, numadded):
        # lets say that firstline is 1 (line 2), and we already have pending
        # changes for lines 0,
        # 1, 2, 3
        # numremoved is 1, meaning that the line was DELETED
        # deletebefore will be 2
        deletebefore = firstline + numremoved
        # numadded is 0, meaning shuffle is -1
        shuffle = numadded - numremoved
        # this means every linenr BEFORE 1 stays the same,
        # every linenr >= deletebefore needs to be shuffled by -1, and anything
        # else disappears

        # SCENARIO B:
        # firstline is 3 (line 4), numremoved is 1, numadded is 1
        # shuffle will be 0
        # deletebefore will be 3

        newpending = list(range(firstline, firstline + numadded))
        for linenr in self.pending:
            if linenr < firstline:
                # every pending line before line 1 stays the same
                newpending.append(linenr)
            elif linenr >= deletebefore:
                # the pending changes for lines 2 and 3 now become pending
                # changes for lines 1 and 2
                newpending.append(linenr + shuffle)
            else:
                # the linenr falls between linenr and deletebefore, so we
                # discard it (add it separately)
                pass

        self.pending = newpending

    def pushhighlights(self, nvim):
        # don't push highlights when we're already pushing highlights
        if self.pushing:
            return

        # lets throw in an arbitrary sleep to give the user time to push lines
        # down
        #import time
        #time.sleep(3)

        try:
            self.pushing = True
            self._push(nvim)
        finally:
            self.pushing = False

    def _push(self, nvim):
        global SOURCEID
        # if we don't have a SOURCEID, we need to get one now
        if SOURCEID == 0:
            SOURCEID = self.nbuf.api.add_highlight(SOURCEID, 'Error',
                                                   0, 1, 2)
            self.nbuf.api.clear_highlight(SOURCEID, 0, -1)

        # push all pending highlights
        while len(self.pending):
            linenr = self.pending[0]
            realline = linenr + 1

            trytick = self.tick
            methods = [
                # this will fail if the ticks aren't sync'd
                ['nvim_eval',
                 ['b:changedtick == %d || nr2char()' % trytick]],
                # clear highlighting for the current line
                ['nvim_buf_clear_highlight',
                 [self.nbuf, SOURCEID, linenr, linenr + 1]]
            ]

            # work out highlighting for this line
            for m in MYREGEX.finditer(self.lines[linenr]):
                start, end = m.span()
                methods.append(['nvim_buf_add_highlight',
                                [self.nbuf, SOURCEID, HLGROUP,
                                 linenr, start, end]])

            # SO: the things that can happen suring call_atomic() are:
            # - another LiveUpdate is received first.
            #   - if this happens, we're ok because the call_atomic is going to
            #     fail
            assert not self.pushbroken
            retvals, errors = nvim.api.call_atomic(methods)

            # if we have self.pushbroken, that means we received a LiveUpdate
            # while sending our new HL text so we need to try and send it out
            # again
            if self.pushbroken:
                self.pushbroken = False
                continue

            if errors is not None:
                # the first expr involving b:changedtick is the only one that
                # should fail ...
                assert errors[0] == 0, "Only the first api call should fail"
                # so if the b:changedtick check failed, it means there is
                # another LiveUpdate on the way with new buffer changes, so we
                # stop trying to push changes and wait for the next LiveUpdate
                return

            # b:changedtick hadn't changed, so we can be certain that our
            # HL push was done correctly, THEREFORE we can pop this line
            self.pending.pop(0)


def removehighlights(info, start, num):
    if SOURCEID == 0:
        return
    info.nbuf.api.clear_highlight(SOURCEID, start, start + num)


def addhighlights(info, start=0, num=None):
    global SOURCEID
    if num is None:
        stop = len(info.lines)
    else:
        stop = start + num
    regex = MYREGEX
    for linenr in range(start, stop):
        # add a highlight of the nth characher in the line
        linedata = info.lines[linenr]
        for m in regex.finditer(linedata):
            start, end = m.span()
            SOURCEID = info.nbuf.api.add_highlight(SOURCEID, HLGROUP,
                                                   linenr, start, end)


def handle_request(nvim, name, args):
    global MYREGEX, HLGROUP

    if name == 'YourWord':
        assert len(args) == 1
        assert MYREGEX is None
        word = args[0]
        assert isinstance(word, str)
        assert word.isalnum(), "Word must be alphanumeric"
        MYREGEX = re.compile(r'\b{}\b'.format(word))

        if HLGROUP is not None:
            for info in BUFFERS.values():
                addhighlights(info)
        return

    if name == 'YourHighlight':
        assert len(args) == 1
        HLGROUP = args[0]
        if MYREGEX is not None:
            for info in BUFFERS.values():
                addhighlights(info)
        return

    if name == 'AddBuffer':
        assert len(args) == 1
        bufnr = args[0]
        buffer = nvim.buffers[bufnr]
        try:
            buffer.api.live_updates(True)
        except:
            raise Exception("Couldn't turn on live updates for buffer %d"
                            % bufnr)
        BUFFERS[bufnr] = BufferInfo(buffer, bufnr)
        return

    raise Exception("unexpected request {!r}: {!r}".format(name, args))


def handle_notification(nvim, name, args):
    try:
        if name == 'LiveUpdateStart':
            buf, tick, lines, more = args
            bufnr = buf.number
            assert bufnr in BUFFERS
            info = BUFFERS[bufnr]
            assert not info.locked
            info.tick = tick
            info.lines += lines
            if not more:
                info.locked = True
            if MYREGEX is not None and HLGROUP is not None:
                addhighlights(info)
            return

        if name == 'LiveUpdateTick':
            buf, tick = args
            assert tick is not None
            bufnr = buf.number
            info = BUFFERS[bufnr]
            info.tick = tick
            # if we are part-way through pushing a HL change, mark it as broken
            if info.pushing:
                info.pushbroken = True
            return

        if name == 'LiveUpdate':
            buf, tick, firstline, numreplaced, linedata = args
            bufnr = buf.number
            info = BUFFERS[bufnr]
            # NOTE: 'inccommand' will cause a LiveUpdate to come through with
            # b:changedtick of None ... this is because it updates the text
            # which is displayed on screen, but doesn't actually update the
            # buffer contents
            if tick is not None:
                info.tick = tick
            # swap in the new line data
            info.lines[firstline:firstline+numreplaced] = linedata
            if info.pushing:
                info.pushbroken = True
            info.flaglines(firstline, numreplaced, len(linedata))
            if not info.pushing:
                info.pushhighlights(nvim)
            #if len(linedata):
                #addhighlights(info, firstline, len(linedata))
            return

        if name == 'LiveUpdateEnd':
            bufnr = args[0].number
            BUFFERS.pop(bufnr, None)
            return

        raise Exception("Unexpected event {!r}: {!r}".format(name, args))

    except Exception as err:
        error_cb(nvim, str(err))
        raise


def error_cb(nvim, message):
    with open(os.environ['HOME'] + '/.nvimlog', 'a') as f:
        f.write('ERROR: %s\n' % (message, ))  # noqa


def main():
    nvim = neovim.attach('stdio')

    # create buffer objects for all current vim buffers, tell neovim to send us
    # buffer events
    for buffer in nvim.buffers:
        bufnr = buffer.number
        buffer.api.live_updates(True)
        BUFFERS[bufnr] = BufferInfo(buffer, bufnr)

    # set up RPC hooks
    nvim.run_loop(partial(handle_request, nvim),
                  partial(handle_notification, nvim),
                  err_cb=partial(error_cb, nvim))


if __name__ == '__main__':
    try:
        main()
    except Exception:
        with open(os.environ['HOME'] + '/.nvimlog', 'a') as f:
            import sys
            import traceback
            f.write("".join(traceback.format_exception(*sys.exc_info())))
