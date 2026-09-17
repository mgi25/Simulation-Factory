# company/youtube — what is tracked, and what is not

## The mapping is a definition, so it lives in git

`video_assignments.json` maps a YouTube video id to the deliverable it is. That
is not a measurement and nothing can re-derive it: the platform does not know
which of our deliverables a video is, and reading it off a title would be a
guess wearing the authority of a record. It is decided once, by whoever made the
video, and **every stored observation depends on it to still mean anything** —
lose the mapping and the readings become numbers about nothing.

`company/workforce/store.py` already drew this line and this module follows it:

> definitions live in git, they are reviewed, and they change when someone
> decides the company works differently. Everything the store writes is state.

So:

```text
tracked (git)                      untracked (never in git)
  identity mapping                   OAuth client JSON
  company/youtube/video_assignments.json
                                     refresh and access tokens
                                     fetched API artifacts
                                     analytics runtime state (--state-dir)
                                     the evidence envelope
                                     transient logs
```

## One editable source of truth

`python -m company.youtube ingest <artifact>` reads `video_assignments.json` by
default. `--assignments <path>` still accepts a file, for a mapping that is not
yet company knowledge — but there is deliberately **no** copy of this mapping
under a state directory. Two editable copies disagree eventually, and the one
that gets edited is whichever the operator happened to have open.

Add a video by editing the tracked file and having the change reviewed. An id
that is not CEO-confirmed has no row: absent, never present-and-blank.

## The sharp edge

Nothing refuses two videos mapped to one `deliverable_id` — a re-upload really
is the same deliverable. The first video wins the deliverable record and both
videos' readings attach to it, so a typo produces a clean import and a quietly
wrong record whose `production_refs` names one video while holding another's
readings. The diff is the only place to catch it, which is the other reason this
file is reviewed rather than edited in place.
