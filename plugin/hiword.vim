" we must have neovim's api_info() function to get started
if ! exists('*api_info')
  finish
endif

" check to see if the liveupdate feature is available
if ! exists('s:has_liveupdate')
  let s:has_liveupdate = 0
  for s:func in api_info()["functions"]
    if get(s:func, "name") == "nvim_buf_live_updates"
      let s:has_liveupdate = 1
      break
    endif
  endfor
endif

if ! s:has_liveupdate
  finish
endif
com! -nargs=+ -bar Hiword call <SID>AddWord(<f-args>)
com! -nargs=0 -bar HiwordPoll call <SID>PollAll()

aug Hiword
aug end
au! BufWinEnter * call <SID>RegisterMe()

let s:pyscript = expand('<sfile>:p:h:h').'/hiword.py'

if ! exists('s:helpers')
  let s:helpers = {}
endif

fun! <SID>AddWord(hlgroup, word)
  if len(get(s:helpers, a:word, []))
    " kill the old job
    let l:oldjob = s:helpers[a:word][0]
    call jobstop(l:oldjob)
    call remove(s:helpers, a:word)
  endif

  " make sure the hlgroup is valid
  if ! hlexists(a:hlgroup)
    echoerr printf('Invalid hlgroup %s', a:hlgroup)
    return
  endif

  let l:helper = 0
  try
    " start up a helper to handle this word
    let l:helper = jobstart([s:pyscript], {"rpc": v:true})
    let s:helpers[a:word] = [l:helper, a:hlgroup]
    " tell the helper its word
    call rpcrequest(l:helper, 'YourWord', a:word)
    let l:response = rpcrequest(l:helper, 'YourHighlight', a:hlgroup)
  catch
    if l:helper
      " kill the helper
      silent! call jobstop(l:helper)
      " remove the word from our dict
      if len(get(s:helpers, a:word, []))
        silent! call remove(s:helpers, a:word)
      endif
    endif
    echoerr v:exception
    return
  endtry

  call <SID>PollAll()
endfun

fun! <SID>PollAll()
  " clean up any helpers that are no longer running
  for l:word in keys(s:helpers)
    let [l:helper, l:hlgroup] = s:helpers[l:word]
    let l:state = jobwait([l:helper], 0)[0]
    if l:state == -2 || l:state == -3
      call remove(s:helpers, l:word)
      echoerr printf("Helper %d for '%s' has died", l:helper, l:word)
      return
    endif
  endfor
endfun

fun! <SID>RegisterMe()
  for [l:helper, l:hlgroup] in values(s:helpers)
    call rpcrequest(l:helper, 'AddBuffer', bufnr(""))
  endfor
endfun
