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
        self.highlights = {}


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
        if not buffer.api.live_updates(True):
            raise Exception("Couldn't turn on live updates for buffer %d" % bufnr)
        BUFFERS[bufnr] = BufferInfo(buffer, bufnr)
        return

    raise Exception("unexpected request {!r}: {!r}".format(name, args))


def handle_notification(nvim, name, args):
    try:
        if name == 'LiveUpdateStart':
            bufnr, lines, more = args
            assert bufnr in BUFFERS
            info = BUFFERS[bufnr]
            assert not info.locked
            info.lines += lines
            if not more:
                info.locked = True
            if MYREGEX is not None and HLGROUP is not None:
                addhighlights(info)
            return

        if name == 'LiveUpdate':
            bufnr, firstline, numreplaced, linedata = args
            info = BUFFERS[bufnr]
            # remove existing highlights on the lines getting replaced
            if numreplaced:
                removehighlights(info, firstline, numreplaced)
            # swap in the new lines
            info.lines[firstline:firstline+numreplaced] = linedata
            if len(linedata):
                addhighlights(info, firstline, len(linedata))
            return

        if name == 'LiveUpdateEnd':
            bufnr = args[0]
            # try and re-add the live updates
            try:
                buffer = BUFFERS[bufnr]
            except:
                return
            if not buffer.nbuf.api.live_updates(True):
                BUFFERS.pop(bufnr)
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
