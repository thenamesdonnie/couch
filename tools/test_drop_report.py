#!/usr/bin/env python3
"""Tests for bb-drop-report, the "why did the picture hitch" tool.

Everything here is synthetic and lives under tmp_path. No live log is read,
no live clock is used: the wall clocks in these fixtures are a fixed fake
epoch, and the CLI tests pin the anchor with BB_CSV_ANCHOR so a test never
depends on when a file happened to be created.

The interesting failures this file is built to catch:

  * a threshold that follows the median off a cliff. A capped-30fps session
    would otherwise report every ordinary frame as a drop;
  * one shader compile reported as five separate drops because it spanned
    five late frames (merging);
  * "CPU/engine" decided from cpu_load. MangoHud's cpu_load is an all-thread
    average, so a saturated emulator reads ~30 and a naive rule would call a
    hard-working machine idle. There is a test that pins this;
  * an event a hair outside the +/- 1.5s window silently deciding a cause,
    or one a hair inside being missed;
  * the whole report dying because the events file is missing or was cut off
    mid-session (the box died). Both must still produce a report.

Run:  couchd/.venv/bin/pytest tools/test_drop_report.py -q
"""
import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, 'bb-drop-report')
_spec = importlib.util.spec_from_loader(
    'bb_drop_report',
    importlib.machinery.SourceFileLoader('bb_drop_report', TOOL))
bdr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bdr)

EPOCH = 1787345975.0        # a fixed fake "now", never time.time()
FRAME60 = 16.67             # a healthy frame at 60fps


# =========================================================================
# fixture builders
# =========================================================================
def csv_text(frametimes, gpu=52.0, cpu=29.5, first_elapsed=455144094):
    """A MangoHud log with the real file's shape: sysinfo pair, frame header,
    a row per frame. gpu/cpu may be a scalar or a per-frame list."""
    n = len(frametimes)
    gpus = gpu if isinstance(gpu, (list, tuple)) else [gpu] * n
    cpus = cpu if isinstance(cpu, (list, tuple)) else [cpu] * n
    lines = [
        'os,cpu,gpu,ram,kernel,driver,cpuscheduler',
        'Ubuntu 24.04.4 LTS,AMD Ryzen 7 5700X3D 8-Core Processor,,32782116,'
        '7.0.0-29-generic,4.6 Mesa 25.2.8,powersave',
        'fps,frametime,cpu_load,gpu_load,cpu_temp,gpu_temp,gpu_core_clock,'
        'gpu_mem_clock,gpu_vram_used,gpu_power,ram_used,elapsed',
    ]
    elapsed = first_elapsed
    for ft, g, c in zip(frametimes, gpus, cpus):
        lines.append(f'{1000.0 / ft:.4f},{ft:.4f},{c},{g},64,50,1530,1258,'
                     f'7.38,70,15.78,{elapsed}')
        elapsed += int(ft * 1e6)
    return '\n'.join(lines) + '\n'


def events_text(entries, start=EPOCH, end=None):
    """entries: list of (wall_epoch, raw log line)."""
    lines = [f'START {start:.3f}']
    for ts, line in entries:
        lines.append(f'{ts:.3f} {line}')
    if end is not None:
        lines.append(f'END {end:.3f}')
    return '\n'.join(lines) + '\n'


COMPILE = '[Render] <Info> Compiling graphics pipeline 0xdeadbeef'
ERROR = '[Vulkan] <Error> buffer_cache: failed to map upload buffer'


def frames_from(frametimes, gpu=52.0, cpu=29.5, anchor=EPOCH):
    _sys, frames = bdr.parse_csv(csv_text(frametimes, gpu=gpu, cpu=cpu))
    return bdr.anchor_frames(frames, anchor)


def session(good_before, drops, good_after, **kw):
    """A tidy session: healthy frames, the drop(s), healthy frames."""
    return frames_from([FRAME60] * good_before + list(drops)
                       + [FRAME60] * good_after, **kw)


# =========================================================================
# parsing
# =========================================================================
def test_the_frame_header_is_found_by_name_not_by_line_number():
    """MangoHud adding a sysinfo column must not shift the parser off the
    frame header."""
    text = csv_text([FRAME60] * 3).replace(
        'os,cpu,gpu,ram', 'os,cpu,gpu,extra_new_field,ram').replace(
        'Ubuntu 24.04.4 LTS,', 'Ubuntu 24.04.4 LTS,X,')
    sysinfo, frames = bdr.parse_csv(text)
    assert len(frames) == 3
    assert sysinfo['os'] == 'Ubuntu 24.04.4 LTS'


def test_one_ruined_row_does_not_lose_the_session():
    text = csv_text([FRAME60] * 5).splitlines()
    text.insert(5, 'garbage,,,,,,')            # a torn line, half flushed
    text.insert(7, '')
    sysinfo, frames = bdr.parse_csv('\n'.join(text))
    assert len(frames) == 5, 'the bad rows are skipped, every good one survives'


def test_a_missing_load_reads_as_unknown_not_as_idle():
    """An empty gpu_load cell is not a zero reading. If it parsed as 0 every
    such incident would be blamed on the emulator's thread."""
    _sys, frames = bdr.parse_csv(csv_text([FRAME60, 60.0, FRAME60], gpu=''))
    assert all(f.gpu_load == -1.0 for f in frames)
    bdr.anchor_frames(frames, EPOCH)
    inc = bdr.find_incidents(frames, 33.4)[0]
    bdr.classify(inc, frames, [], have_events=True)
    assert inc.cause == 'unclear'
    assert 'unknown' in inc.evidence


def test_a_csv_without_a_frame_header_is_a_clear_error():
    with pytest.raises(ValueError, match='frametime'):
        bdr.parse_csv('nothing,useful\n1,2\n')


def test_events_parse_only_the_interesting_lines():
    ev = bdr.parse_events(events_text([
        (EPOCH + 1, COMPILE),
        (EPOCH + 2, '[Kernel] <Info> boring chatter'),
        (EPOCH + 3, ERROR),
        (EPOCH + 4, '[Core] <Critical> something bad'),
    ], end=EPOCH + 10))
    assert [e.kind for e in ev.events] == ['compile', 'error', 'error']
    assert ev.start == EPOCH and ev.end == EPOCH + 10
    assert ev.truncated is False


def test_a_missing_END_line_is_noticed_not_fatal():
    """bb-event-tail only writes END if it outlives the emulator. No END
    means the session went down hard, which the report should say."""
    ev = bdr.parse_events(events_text([(EPOCH + 1, COMPILE)]))
    assert ev.truncated is True
    assert ev.end is None
    assert len(ev.compiles) == 1


# =========================================================================
# alignment
# =========================================================================
def test_wall_clock_is_the_anchor_plus_elapsed_since_the_first_row():
    frames = frames_from([FRAME60] * 3, anchor=EPOCH)
    assert frames[0].wall == pytest.approx(EPOCH)
    assert frames[2].wall == pytest.approx(EPOCH + 2 * FRAME60 / 1000, abs=1e-6)


def test_a_frame_began_one_frametime_before_it_presented():
    frames = frames_from([FRAME60, 100.0], anchor=EPOCH)
    assert frames[1].began == pytest.approx(frames[1].wall - 0.1, abs=1e-6)


# =========================================================================
# detection
# =========================================================================
def test_the_threshold_is_twice_the_session_median():
    median, thr = bdr.drop_threshold([FRAME60] * 100 + [200.0])
    assert median == pytest.approx(FRAME60)
    assert thr == pytest.approx(2 * FRAME60, abs=0.01)


def test_a_fast_session_still_gets_the_25ms_floor():
    """At 144fps twice the median is 13.9ms, and calling a 14ms frame a drop
    would fill the report with noise nobody can see."""
    median, thr = bdr.drop_threshold([6.94] * 100)
    assert thr == pytest.approx(25.0)


def test_a_thirty_fps_session_measures_drops_against_its_own_normal():
    median, thr = bdr.drop_threshold([33.3] * 100)
    assert thr == pytest.approx(66.6, abs=0.01)
    frames = frames_from([33.3] * 50)
    assert bdr.find_incidents(frames, thr) == [], 'a capped session is not one long drop'


def test_a_drop_records_its_time_length_and_floor():
    frames = session(60, [120.0], 60)
    inc = bdr.find_incidents(frames, 33.4)[0]
    # The 61st frame PRESENTED at 1.00s, but the picture had already been
    # frozen for its whole 120ms before that, so the drop starts at 0.90s.
    # Reporting the presentation time would point Donnie a frame too late.
    assert inc.offset_s == pytest.approx(0.897, abs=0.01)
    assert inc.duration_s == pytest.approx(0.12, abs=1e-6)
    assert inc.worst_ms == pytest.approx(120.0)
    assert inc.fps_floor == pytest.approx(1000 / 120)


def test_offsets_are_printed_as_minutes_and_seconds():
    assert bdr.mmss(0.4) == '00:00'
    assert bdr.mmss(72.9) == '01:12'
    assert bdr.mmss(-1) == '00:00'
    assert bdr.human_duration(582) == '9m 42s'
    assert bdr.human_duration(42) == '42s'


def test_late_frames_close_together_are_one_incident():
    """A compile spans several frames. Reporting five drops for one hitch
    would treble the count and misdescribe the evening."""
    frames = frames_from([FRAME60] * 20 + [90.0, 80.0, 70.0] + [FRAME60] * 20)
    incidents = bdr.find_incidents(frames, 33.4)
    assert len(incidents) == 1
    assert incidents[0].frames == 3
    assert incidents[0].worst_ms == pytest.approx(90.0)


def test_late_frames_a_second_apart_are_two_incidents():
    gap = [FRAME60] * 90          # 1.5s of healthy frames between them
    frames = frames_from([FRAME60] * 10 + [90.0] + gap + [90.0] + [FRAME60] * 10)
    assert len(bdr.find_incidents(frames, 33.4)) == 2


def test_the_merge_gap_edge_holds_at_exactly_one_second():
    inside = [FRAME60] * 59       # 0.98s apart, merged
    outside = [FRAME60] * 62      # 1.03s apart, separate
    assert len(bdr.find_incidents(
        frames_from([90.0] + inside + [90.0]), 33.4)) == 1
    assert len(bdr.find_incidents(
        frames_from([90.0] + outside + [90.0]), 33.4)) == 2


def test_a_clean_session_reports_no_incidents():
    frames = frames_from([FRAME60] * 200)
    _median, thr = bdr.drop_threshold([f.frametime_ms for f in frames])
    assert bdr.find_incidents(frames, thr) == []


# =========================================================================
# classification
# =========================================================================
def classify_one(frames, events, have_events=True, threshold=33.4):
    inc = bdr.find_incidents(frames, threshold)[0]
    return bdr.classify(inc, frames, events, have_events)


def test_a_compile_beside_a_drop_is_the_cause():
    frames = session(60, [150.0], 60)
    hitch = frames[60].wall
    ev = bdr.parse_events(events_text([(hitch - 0.05, COMPILE),
                                       (hitch, COMPILE)], end=EPOCH + 10))
    inc = classify_one(frames, ev.events)
    assert inc.cause == 'shader compile'
    assert inc.compiles == 2
    assert '2 compiles' in inc.evidence


def test_a_compile_wins_even_when_the_gpu_looks_pegged():
    """Priority order matters: a compile explains the hitch whatever the load
    numbers happened to read during it."""
    frames = session(60, [150.0], 60, gpu=99.0)
    ev = bdr.parse_events(events_text([(frames[60].wall, COMPILE)], end=EPOCH + 10))
    assert classify_one(frames, ev.events).cause == 'shader compile'


def test_a_pegged_card_with_no_compile_is_gpu_bound():
    frames = session(60, [150.0], 60, gpu=96.0)
    inc = classify_one(frames, [])
    assert inc.cause == 'GPU-bound'
    assert inc.gpu_load == pytest.approx(96.0)


def test_an_idle_card_with_no_compile_is_the_emulator():
    frames = session(60, [150.0], 60, gpu=41.0)
    inc = classify_one(frames, [])
    assert inc.cause == 'CPU/engine'
    assert 'waiting' in inc.evidence


def test_the_emulator_verdict_is_never_gated_on_the_all_core_cpu_average():
    """THE TRAP. cpu_load is averaged over all 16 hardware threads, so a
    shadPS4 pinning five of them reads about 30. Anything that required a
    high cpu_load here would call a stalled emulator "unclear" forever."""
    frames = session(60, [150.0], 60, gpu=35.0, cpu=30.0)
    inc = classify_one(frames, [])
    assert inc.cause == 'CPU/engine'
    assert inc.cpu_load == pytest.approx(30.0), 'reported, but not used to decide'


def test_a_middling_card_with_no_compile_is_left_unclear():
    """85% GPU is neither flat out nor waiting. Guessing here would be worse
    than admitting we do not know."""
    frames = session(60, [150.0], 60, gpu=85.0)
    inc = classify_one(frames, [])
    assert inc.cause == 'unclear'


def test_errors_near_a_drop_are_flagged_without_becoming_the_cause():
    frames = session(60, [150.0], 60, gpu=96.0)
    ev = bdr.parse_events(events_text([(frames[60].wall, ERROR)], end=EPOCH + 10))
    inc = classify_one(frames, ev.events)
    assert inc.cause == 'GPU-bound', 'an error line is evidence, not a diagnosis'
    assert inc.errors == [ERROR]
    assert '1 error line' in inc.evidence


# =========================================================================
# the +/- 1.5s window edges
# =========================================================================
@pytest.mark.parametrize('offset,expected', [
    (-1.4, 'shader compile'),      # just inside, before the drop
    (-1.6, 'CPU/engine'),          # just outside
    (1.4, 'shader compile'),       # just inside, after the drop
    (1.6, 'CPU/engine'),           # just outside
])
def test_the_attribution_window_is_one_and_a_half_seconds(offset, expected):
    """The two logs are stamped by different processes and agree to about a
    second, so the window is deliberately loose. It is not unbounded."""
    frames = session(60, [150.0], 240, gpu=41.0)
    inc = bdr.find_incidents(frames, 33.4)[0]
    edge = (inc.start if offset < 0 else inc.end) + offset
    ev = bdr.parse_events(events_text([(edge, COMPILE)], end=EPOCH + 20))
    bdr.classify(inc, frames, ev.events)
    assert inc.cause == expected


def test_the_window_is_measured_from_the_ends_of_a_long_stall():
    """A four second stall with a compile in the middle of it must still be
    attributed: the window hangs off the incident's edges, not its start."""
    frames = session(60, [4000.0], 60, gpu=41.0)
    inc = bdr.find_incidents(frames, 33.4)[0]
    ev = bdr.parse_events(events_text([(inc.start + 2.0, COMPILE)], end=EPOCH + 20))
    bdr.classify(inc, frames, ev.events)
    assert inc.cause == 'shader compile'


# =========================================================================
# session numbers and the report body
# =========================================================================
def test_the_session_summary_matches_the_frames():
    frames = frames_from([FRAME60] * 600)
    s = bdr.session_stats(frames)
    assert s['frames'] == 600
    assert s['duration_s'] == pytest.approx(10.0, abs=0.02)
    assert s['avg_fps'] == pytest.approx(60.0, abs=0.1)


def test_the_one_percent_low_is_dragged_down_by_the_worst_frames():
    frames = frames_from([FRAME60] * 99 + [200.0])
    s = bdr.session_stats(frames)
    assert s['avg_fps'] > 50
    assert s['low_1pct_fps'] == pytest.approx(5.0, abs=0.1)


def test_a_compile_heavy_session_gets_the_cache_verdict():
    incidents = [bdr.Incident(0, 0, 0, 0, 0, 0, 1, cause='shader compile')
                 for _ in range(14)]
    incidents += [bdr.Incident(0, 0, 0, 0, 0, 0, 1, cause='GPU-bound')
                  for _ in range(4)]
    v = bdr.verdict(incidents, True)
    assert v.startswith('14/18 drops were one-time shader compiles')
    assert 'cache fills' in v


def test_a_clean_session_says_so():
    assert 'held' in bdr.verdict([], True)


def test_no_em_dashes_anywhere_in_the_output_or_the_source():
    """House rule. Checked on the source too, because the strings that reach
    Donnie all live in it."""
    with open(TOOL, encoding='utf-8') as fh:
        assert '—' not in fh.read()
    frames = session(20, [150.0], 20, gpu=96.0)
    rep = bdr.build_report('x.csv', None, {}, frames, bdr.Events(), False, 'test')
    assert '—' not in bdr.render_text(rep)


# =========================================================================
# missing / broken inputs
# =========================================================================
def test_without_an_events_file_the_report_still_works(tmp_path):
    csvp = tmp_path / 'shadps4_2026-08-21_21-59-34.csv'
    csvp.write_text(csv_text([FRAME60] * 60 + [150.0] + [FRAME60] * 60, gpu=96.0))
    os.environ['BB_CSV_ANCHOR'] = str(EPOCH)
    try:
        got = bdr.read_session(str(csvp), str(tmp_path / 'events-nope.log'))
    finally:
        del os.environ['BB_CSV_ANCHOR']
    sysinfo, frames, ev, have_events, source, skew = got
    assert have_events is False and skew is None
    rep = bdr.build_report(str(csvp), None, sysinfo, frames, ev, have_events, source)
    text = bdr.render_text(rep)
    assert rep['attribution'] is False
    assert 'events  none found' in text
    assert len(rep['incidents']) == 1, 'drops are still found without events'


def test_a_truncated_events_file_is_called_out_in_the_report(tmp_path):
    frames = session(60, [150.0], 60, gpu=41.0)
    ev = bdr.parse_events(events_text([(frames[60].wall, COMPILE)]))   # no END
    rep = bdr.build_report('a.csv', 'b.log', {}, frames, ev, True, 'test')
    assert rep['events_truncated'] is True
    assert 'no END line' in bdr.render_text(rep)


def test_two_files_from_different_sessions_are_flagged(tmp_path):
    """Defaulting to "newest of each" can pair a CSV with the previous
    session's events file. Silently doing that would produce confident,
    wrong causes."""
    frames = session(20, [150.0], 20, gpu=41.0)
    rep = bdr.build_report('a.csv', 'b.log', {}, frames, bdr.Events(start=EPOCH),
                           True, 'file birth time', pair_skew=-900.0)
    assert 'WARNING' in bdr.render_text(rep)


def test_birth_time_reads_a_real_file_or_returns_zero(tmp_path):
    """The one bit of I/O worth touching disk for: it is a subprocess call to
    coreutils and it is the whole time alignment."""
    p = tmp_path / 'probe.csv'
    p.write_text('x')
    born = bdr.birth_time(str(p))
    assert born == 0.0 or born > 1_700_000_000, 'either unsupported, or sane'


def test_an_empty_csv_is_a_clear_error(tmp_path):
    p = tmp_path / 'shadps4_empty.csv'
    p.write_text(csv_text([]))
    with pytest.raises(ValueError, match='no frame rows'):
        bdr.read_session(str(p), None)


# =========================================================================
# the CLI, on a full synthetic pair
# =========================================================================
def write_pair(tmp_path):
    """A session with three drops of three different causes: one compile
    hitch, one pegged card, one stalled emulator.

    The pegged stretch holds 97% for a second either side of its drop, which
    is what a genuinely GPU-bound moment looks like. A single 97% row with
    quiet frames around it would average back down inside the load window,
    and it SHOULD: one hot sample is not a bottleneck.
    """
    gpu, ft = [], []

    def stretch(n, frametime, load):
        ft.extend([frametime] * n)
        gpu.extend([load] * n)

    stretch(120, FRAME60, 52.0)     # 0.0 - 2.0s  healthy
    stretch(1, 150.0, 52.0)         #             compile hitch
    stretch(120, FRAME60, 52.0)
    stretch(60, FRAME60, 97.0)      #             the card climbs to flat out
    stretch(1, 90.0, 97.0)          #             GPU-bound drop
    stretch(60, FRAME60, 97.0)
    stretch(120, FRAME60, 52.0)
    stretch(1, 120.0, 38.0)         #             emulator stall, card idle
    stretch(120, FRAME60, 52.0)

    csvp = tmp_path / 'shadps4_2026-08-21_21-59-34.csv'
    csvp.write_text(csv_text(ft, gpu=gpu))

    _sys, frames = bdr.parse_csv(csvp.read_text())
    bdr.anchor_frames(frames, EPOCH)
    _median, thr = bdr.drop_threshold([f.frametime_ms for f in frames])
    hitch, _pegged, stall = bdr.find_incidents(frames, thr)
    evp = tmp_path / 'events-2026-08-21_21-59-34.log'
    evp.write_text(events_text([
        (hitch.start - 0.1, COMPILE),
        (hitch.end, COMPILE),
        (stall.end + 0.2, ERROR),
    ], start=EPOCH, end=EPOCH + 12))
    return csvp, evp


def run_cli(tmp_path, *args):
    env = dict(os.environ, BB_PERF_DIR=str(tmp_path), BB_CSV_ANCHOR=str(EPOCH))
    return subprocess.run([sys.executable, TOOL, *args], capture_output=True,
                          text=True, env=env, timeout=60)


def test_the_cli_picks_the_newest_pair_and_explains_every_drop(tmp_path):
    write_pair(tmp_path)
    out = run_cli(tmp_path)
    assert out.returncode == 0, out.stderr
    text = out.stdout
    assert '3 drops' in text
    assert 'shader compile' in text and 'GPU-bound' in text and 'CPU/engine' in text
    assert 'Verdict:' in text
    assert '2 compiles within 1.5s' in text
    assert 'Session' in text and 'average' in text
    assert 'Error lines beside drops' in text


def test_the_cli_json_carries_the_same_answers(tmp_path):
    write_pair(tmp_path)
    out = run_cli(tmp_path, '--json')
    assert out.returncode == 0, out.stderr
    rep = json.loads(out.stdout)
    assert rep['counts'] == {'shader compile': 1, 'GPU-bound': 1, 'CPU/engine': 1}
    assert rep['attribution'] is True
    assert rep['compiles_total'] == 2 and rep['errors_total'] == 1
    assert len(rep['incidents']) == 3
    first = rep['incidents'][0]
    assert first['cause'] == 'shader compile' and first['compiles'] == 2
    assert rep['incidents'][2]['errors'], 'the error line rides with its drop'
    assert rep['anchor_source'] == 'BB_CSV_ANCHOR'


def test_the_cli_takes_an_explicit_pair(tmp_path):
    csvp, evp = write_pair(tmp_path)
    out = run_cli(tmp_path, str(csvp), str(evp), '--json')
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout)['csv'] == str(csvp)


def test_the_cli_says_so_when_there_is_nothing_to_read(tmp_path):
    out = run_cli(tmp_path)
    assert out.returncode == 2
    assert 'no MangoHud CSV' in out.stderr


def test_the_cli_rejects_an_unknown_option(tmp_path):
    write_pair(tmp_path)
    out = run_cli(tmp_path, '--wat')
    assert out.returncode == 2 and 'unknown option' in out.stderr
