/* midiengine.js — dependency-free UMD MIDI parser + Web Audio synth for the
 * 红石音乐走线设计器 (poc/layout_designer.html, 任务8).
 *
 * Exposes `MidiEngine` (browser: window.MidiEngine, node: module.exports) with:
 *   MidiEngine.parse(arrayBufferOrUint8Array)
 *       -> { notes:[{t,dur,midi,vel,ch,prog,instr}], duration, ppq, format, ntrks }
 *   MidiEngine.Synth   — Web Audio playback class (browser only; ctor is lazy)
 *   MidiEngine.FAMILY  — the GM-program-family map (must match redpiano_map_multi.json)
 *
 * Parsing mirrors poc/48_build_swave_multi.py's mido-based reader:
 *   - all tracks merged onto one absolute-tick timeline
 *   - per-channel running program_change; a note's prog = channel program at note-off
 *   - note_on vel0 == note_off
 *   - tempo map (FF 51 03) drives ticks->seconds, default 500000 us/qn
 *   - instr = 'drum' if ch===9 else FAMILY[prog>>3] (default 'pno')
 *
 * Node self-test at bottom (guarded by require.main===module) reads the real
 * 七里香 .mid and prints note + per-(ch,prog) counts.
 */
(function (root, factory) {
  if (typeof module !== 'undefined' && module.exports) module.exports = factory();
  else root.MidiEngine = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  // GM program (>>3) -> instrument family. MUST match redpiano_map_multi.json family_map.
  var FAMILY = {
    0: 'pno', 1: 'pno', 2: 'pad', 3: 'lead', 4: 'bass', 5: 'pad', 6: 'pad', 7: 'lead',
    8: 'lead', 9: 'lead', 10: 'lead', 11: 'pad', 12: 'pad', 13: 'lead', 14: 'drum', 15: 'drum'
  };
  function instrFor(ch, prog) {
    if (ch === 9) return 'drum';
    var f = FAMILY[prog >> 3];
    return f || 'pno';
  }

  // ---------------------------------------------------------------- parse ----
  function toU8(buf) {
    if (buf instanceof Uint8Array) return buf;
    if (typeof ArrayBuffer !== 'undefined' && buf instanceof ArrayBuffer) return new Uint8Array(buf);
    // node Buffer is already a Uint8Array; this also covers array-likes
    if (buf && buf.buffer instanceof ArrayBuffer) return new Uint8Array(buf.buffer, buf.byteOffset || 0, buf.byteLength);
    if (Array.isArray(buf)) return new Uint8Array(buf);
    throw new Error('MidiEngine.parse: expected ArrayBuffer / Uint8Array / Buffer');
  }

  // Byte cursor over a Uint8Array.
  function Reader(u8) { this.u = u8; this.p = 0; }
  Reader.prototype.u8 = function () { return this.u[this.p++]; };
  Reader.prototype.u16 = function () { var v = (this.u[this.p] << 8) | this.u[this.p + 1]; this.p += 2; return v; };
  Reader.prototype.u32 = function () {
    var v = (this.u[this.p] * 0x1000000) + (this.u[this.p + 1] << 16) + (this.u[this.p + 2] << 8) + this.u[this.p + 3];
    this.p += 4; return v >>> 0;
  };
  Reader.prototype.str = function (n) { var s = ''; for (var i = 0; i < n; i++) s += String.fromCharCode(this.u[this.p++]); return s; };
  Reader.prototype.bytes = function (n) { var b = this.u.subarray(this.p, this.p + n); this.p += n; return b; };
  // MIDI variable-length quantity.
  Reader.prototype.vlq = function () {
    var v = 0, c;
    do { c = this.u[this.p++]; v = (v << 7) | (c & 0x7f); } while (c & 0x80);
    return v >>> 0;
  };

  function parse(input) {
    var u8 = toU8(input);
    var r = new Reader(u8);

    if (r.str(4) !== 'MThd') throw new Error('MidiEngine.parse: missing MThd header');
    var hlen = r.u32();
    var format = r.u16();
    var ntrks = r.u16();
    var division = r.u16();
    // SMPTE timecode division (top bit set) is not supported by the redstone
    // pipeline; treat ppq as the low 15 bits and warn implicitly by clamping.
    var ppq = (division & 0x8000) ? (division & 0x7fff) || 480 : division;
    if (!ppq) ppq = 480;
    // skip any extra header bytes beyond the 6 we read
    r.p = 8 + hlen;

    // Pass 1: read every track into a flat event list keyed by absolute tick.
    // We keep insertion order (track index, then in-track order) as a tiebreaker
    // so same-tick events resolve like mido's stable merge.
    var events = [];   // {tick, ti, oi, type, ...}
    var tempos = [];   // {tick, usPerQn}
    var oi = 0;

    for (var ti = 0; ti < ntrks; ti++) {
      if (r.str(4) !== 'MTrk') {
        // Some files mis-declare ntrks; stop gracefully at first bad chunk.
        break;
      }
      var clen = r.u32();
      var end = r.p + clen;
      var tick = 0;
      var status = 0; // running status

      while (r.p < end) {
        tick += r.vlq();
        var b = r.u[r.p];
        if (b & 0x80) { status = b; r.p++; }
        // else: running status — reuse previous status byte, b is first data byte
        var type = status & 0xf0;
        var ch = status & 0x0f;

        if (status === 0xff) {              // meta
          var metaType = r.u8();
          var len = r.vlq();
          var data = r.bytes(len);
          if (metaType === 0x51 && len === 3) {
            tempos.push({ tick: tick, usPerQn: (data[0] << 16) | (data[1] << 8) | data[2] });
          }
          // 0x2f end_of_track handled implicitly by `end`; other metas ignored.
        } else if (status === 0xf0 || status === 0xf7) { // sysex
          var slen = r.vlq();
          r.bytes(slen);
        } else if (type === 0x90) {          // note_on
          var n1 = r.u8(), v1 = r.u8();
          if (v1 > 0) events.push({ tick: tick, ti: ti, oi: oi++, k: 'on', ch: ch, note: n1, vel: v1 });
          else events.push({ tick: tick, ti: ti, oi: oi++, k: 'off', ch: ch, note: n1 });
        } else if (type === 0x80) {          // note_off
          var n2 = r.u8(); r.u8(); // velocity ignored
          events.push({ tick: tick, ti: ti, oi: oi++, k: 'off', ch: ch, note: n2 });
        } else if (type === 0xc0) {          // program_change (1 data byte)
          var prog = r.u8();
          events.push({ tick: tick, ti: ti, oi: oi++, k: 'prog', ch: ch, prog: prog });
        } else if (type === 0xd0) {          // channel pressure (1 data byte)
          r.u8();
        } else if (type === 0xa0 || type === 0xb0 || type === 0xe0) { // 2 data bytes
          r.u8(); r.u8();
        } else {
          // Unknown/unsupported running-status state — bail this track to avoid
          // desync rather than misread the stream.
          r.p = end;
        }
      }
      r.p = end; // ensure we are exactly at chunk end
    }

    // Sort merged events by tick, then by original (track, in-track) order.
    events.sort(function (a, b) { return (a.tick - b.tick) || (a.ti - b.ti) || (a.oi - b.oi); });
    tempos.sort(function (a, b) { return a.tick - b.tick; });

    // Build a tick->seconds function from the tempo map.
    if (!tempos.length || tempos[0].tick !== 0) tempos.unshift({ tick: 0, usPerQn: 500000 });
    // Precompute cumulative seconds at each tempo change boundary.
    var segSec = [0];
    for (var i = 1; i < tempos.length; i++) {
      var dt = tempos[i].tick - tempos[i - 1].tick;
      segSec[i] = segSec[i - 1] + (dt * (tempos[i - 1].usPerQn / 1e6) / ppq);
    }
    function tickToSec(t) {
      // find last tempo whose tick <= t (linear scan back is fine; few tempos)
      var idx = 0;
      for (var j = tempos.length - 1; j >= 0; j--) { if (tempos[j].tick <= t) { idx = j; break; } }
      return segSec[idx] + (t - tempos[idx].tick) * (tempos[idx].usPerQn / 1e6) / ppq;
    }

    // Pass 2: pair note_on/off, tracking per-channel program. A note's prog is
    // the channel's current program at note-off (matches 48's reader).
    var curProg = {};          // ch -> program (default 0)
    var active = {};           // "ch:note" -> {tick, vel}
    var notes = [];
    var maxTick = 0;

    for (var e = 0; e < events.length; e++) {
      var ev = events[e];
      if (ev.tick > maxTick) maxTick = ev.tick;
      if (ev.k === 'prog') {
        curProg[ev.ch] = ev.prog;
      } else if (ev.k === 'on') {
        active[ev.ch + ':' + ev.note] = { tick: ev.tick, vel: ev.vel };
      } else if (ev.k === 'off') {
        var key = ev.ch + ':' + ev.note;
        var on = active[key];
        if (on) {
          delete active[key];
          var prog = curProg[ev.ch] || 0;
          var t0 = tickToSec(on.tick);
          var t1 = tickToSec(ev.tick);
          var dur = t1 - t0; if (dur < 0.02) dur = 0.02;
          notes.push({
            t: t0,
            dur: dur,
            midi: ev.note | 0,
            vel: on.vel / 127,
            ch: ev.ch,
            prog: prog,
            instr: instrFor(ev.ch, prog)
          });
        }
      }
    }

    // Flush any notes left hanging at track end (no matching note_off).
    var endSec = tickToSec(maxTick);
    for (var ka in active) {
      if (!active.hasOwnProperty(ka)) continue;
      var parts = ka.split(':');
      var chh = parts[0] | 0, nn = parts[1] | 0;
      var on2 = active[ka];
      var pg = curProg[chh] || 0;
      var ts = tickToSec(on2.tick);
      var du = endSec - ts; if (du < 0.02) du = 0.02;
      notes.push({ t: ts, dur: du, midi: nn, vel: on2.vel / 127, ch: chh, prog: pg, instr: instrFor(chh, pg) });
    }

    notes.sort(function (a, b) { return (a.t - b.t) || (a.midi - b.midi); });

    var duration = 0;
    for (var z = 0; z < notes.length; z++) { var te = notes[z].t + notes[z].dur; if (te > duration) duration = te; }

    return { notes: notes, duration: duration, ppq: ppq, format: format, ntrks: ntrks };
  }

  // ----------------------------------------------------------------- Synth ---
  // Lightweight polyphonic Web Audio synth. Browser-only; in node the class is
  // still exported but instantiation throws (no AudioContext).
  function Synth(opts) {
    opts = opts || {};
    this._ctx = null;
    this._master = null;
    this._notes = [];
    this._gain = opts.gain != null ? opts.gain : 0.5;
    this._maxVoices = opts.maxVoices || 48;   // concurrent-voice cap
    this._lookahead = opts.lookahead || 0.1;  // sec of scheduling lookahead
    this._interval = opts.interval || 25;     // ms scheduler tick
    this.isPlaying = false;
    this.duration = 0;
    this._startCtxTime = 0;   // ctx.currentTime when (logical 0) playback began
    this._offset = 0;         // playback seconds at _startCtxTime
    this._scanIdx = 0;        // next note index to schedule
    this._timer = null;
    this._raf = null;
    this._live = [];          // {endTime, stop()} currently sounding voices
    this._onProgress = null;
    this._onEnded = null;
    this._endedFired = false;
  }

  Synth.prototype._ensureCtx = function () {
    if (this._ctx) return this._ctx;
    var AC = (typeof window !== 'undefined') && (window.AudioContext || window.webkitAudioContext);
    if (!AC) throw new Error('Synth: Web Audio API not available in this environment');
    this._ctx = new AC();
    this._master = this._ctx.createGain();
    this._master.gain.value = this._gain;
    this._master.connect(this._ctx.destination);
    // shared noise buffer for drums
    var sr = this._ctx.sampleRate, len = (sr * 0.3) | 0;
    var nb = this._ctx.createBuffer(1, len, sr), ch = nb.getChannelData(0);
    for (var i = 0; i < len; i++) ch[i] = Math.random() * 2 - 1;
    this._noiseBuf = nb;
    return this._ctx;
  };

  Synth.prototype.loadNotes = function (notes) {
    this._notes = (notes || []).slice().sort(function (a, b) { return a.t - b.t; });
    var d = 0;
    for (var i = 0; i < this._notes.length; i++) { var e = this._notes[i].t + this._notes[i].dur; if (e > d) d = e; }
    this.duration = d;
    return this;
  };

  Synth.prototype.setGain = function (g) {
    this._gain = Math.max(0, Math.min(1, g));
    if (this._master) this._master.gain.value = this._gain;
    return this;
  };
  Synth.prototype.onProgress = function (cb) { this._onProgress = cb; return this; };
  Synth.prototype.onEnded = function (cb) { this._onEnded = cb; return this; };

  Object.defineProperty(Synth.prototype, 'currentTime', {
    get: function () {
      if (!this._ctx) return this._offset;
      if (!this.isPlaying) return this._offset;
      return this._offset + (this._ctx.currentTime - this._startCtxTime);
    }
  });

  // midi -> frequency
  function mtof(m) { return 440 * Math.pow(2, (m - 69) / 12); }

  // Schedule one note as a voice starting at absolute ctx time `when`.
  Synth.prototype._spawn = function (n, when) {
    var ctx = this._ctx, instr = n.instr;
    var dur = Math.max(0.04, n.dur);
    var vel = Math.max(0.02, Math.min(1, n.vel || 0.6));
    var g = ctx.createGain();
    g.connect(this._master);
    var nodes = [];

    if (instr === 'drum') {
      // short filtered noise burst; kick-ish for low GM notes, hat-ish for high
      var src = ctx.createBufferSource();
      src.buffer = this._noiseBuf;
      var filt = ctx.createBiquadFilter();
      var hi = n.midi >= 42;
      filt.type = hi ? 'highpass' : 'lowpass';
      filt.frequency.value = hi ? 6000 : 400;
      var dlen = hi ? 0.05 : 0.16;
      src.connect(filt); filt.connect(g);
      var peak = 0.9 * vel;
      g.gain.setValueAtTime(0, when);
      g.gain.linearRampToValueAtTime(peak, when + 0.002);
      g.gain.exponentialRampToValueAtTime(0.0008, when + dlen);
      src.start(when); src.stop(when + dlen + 0.02);
      nodes.push(src);
      return { endTime: when + dlen + 0.02, nodes: nodes, gain: g };
    }

    var wave = (instr === 'pad' || instr === 'bass') ? 'sine' : 'triangle';
    var osc = ctx.createOscillator();
    osc.type = wave;
    osc.frequency.value = mtof(n.midi);
    osc.connect(g);
    nodes.push(osc);
    // ADSR: quick attack, exp decay to a sustain floor, exp release.
    var atk = instr === 'pad' ? 0.04 : 0.008;
    var rel = instr === 'pad' ? 0.25 : 0.12;
    var peakL = 0.32 * vel;
    var sus = peakL * 0.7;
    var t0 = when, tRelStart = when + dur, tEnd = tRelStart + rel;
    g.gain.setValueAtTime(0.0001, t0);
    g.gain.linearRampToValueAtTime(peakL, t0 + atk);
    g.gain.exponentialRampToValueAtTime(Math.max(0.0002, sus), t0 + atk + 0.08);
    g.gain.setValueAtTime(Math.max(0.0002, sus), Math.max(t0 + atk + 0.08, tRelStart));
    g.gain.exponentialRampToValueAtTime(0.0006, tEnd);
    osc.start(t0); osc.stop(tEnd + 0.02);
    return { endTime: tEnd + 0.02, nodes: nodes, gain: g };
  };

  // Scheduler: push notes whose onset falls within the lookahead window.
  Synth.prototype._tick = function () {
    if (!this.isPlaying) return;
    var ctx = this._ctx;
    var now = ctx.currentTime;
    var horizon = (now - this._startCtxTime) + this._offset + this._lookahead; // playback sec
    while (this._scanIdx < this._notes.length && this._notes[this._scanIdx].t <= horizon) {
      var n = this._notes[this._scanIdx++];
      // voice cap: drop oldest still-future-ending voices if saturated
      if (this._live.length >= this._maxVoices) {
        // prune finished
        this._live = this._live.filter(function (v) { return v.endTime > now; });
      }
      if (this._live.length >= this._maxVoices) { continue; } // truly saturated: skip
      var when = this._startCtxTime + (n.t - this._offset);
      if (when < now) when = now; // never schedule in the past
      try { this._live.push(this._spawn(n, when)); } catch (err) { /* ignore voice fail */ }
    }
    // drop finished voices
    this._live = this._live.filter(function (v) { return v.endTime > now - 0.05; });

    // natural end
    if (this._scanIdx >= this._notes.length && this.currentTime >= this.duration) {
      this._finish();
    }
  };

  Synth.prototype._loop = function () {
    var self = this;
    this._timer = setInterval(function () { self._tick(); }, this._interval);
    var raf = (typeof requestAnimationFrame !== 'undefined') ? requestAnimationFrame : function (cb) { return setTimeout(function () { cb(); }, 16); };
    function frame() {
      if (!self.isPlaying) return;
      if (self._onProgress) self._onProgress(self.currentTime);
      if (self.currentTime >= self.duration && self._scanIdx >= self._notes.length) self._finish();
      else self._raf = raf(frame);
    }
    self._raf = raf(frame);
  };

  Synth.prototype.play = function (fromSec) {
    this._ensureCtx();
    if (this._ctx.state === 'suspended' && this._ctx.resume) this._ctx.resume();
    if (this.isPlaying) return this;
    if (fromSec != null) this._offset = Math.max(0, fromSec);
    // (re)position scan index to first note at/after offset
    this._scanIdx = 0;
    while (this._scanIdx < this._notes.length && this._notes[this._scanIdx].t < this._offset) this._scanIdx++;
    this._startCtxTime = this._ctx.currentTime + 0.02;
    this.isPlaying = true;
    this._endedFired = false;
    this._loop();
    return this;
  };

  Synth.prototype._stopVoices = function () {
    var now = this._ctx ? this._ctx.currentTime : 0;
    for (var i = 0; i < this._live.length; i++) {
      var v = this._live[i];
      try {
        if (v.gain) { v.gain.gain.cancelScheduledValues(now); v.gain.gain.setValueAtTime(0.0001, now); }
        for (var j = 0; j < v.nodes.length; j++) { try { v.nodes[j].stop(now + 0.03); } catch (e) {} }
      } catch (e2) {}
    }
    this._live = [];
  };

  Synth.prototype._clearTimers = function () {
    if (this._timer) { clearInterval(this._timer); this._timer = null; }
    if (this._raf != null) {
      if (typeof cancelAnimationFrame !== 'undefined') cancelAnimationFrame(this._raf);
      else clearTimeout(this._raf);
      this._raf = null;
    }
  };

  Synth.prototype.pause = function () {
    if (!this.isPlaying) return this;
    this._offset = this.currentTime;
    this.isPlaying = false;
    this._clearTimers();
    this._stopVoices();
    return this;
  };

  Synth.prototype.stop = function () {
    this.isPlaying = false;
    this._clearTimers();
    this._stopVoices();
    this._offset = 0;
    this._scanIdx = 0;
    return this;
  };

  Synth.prototype.seek = function (sec) {
    var wasPlaying = this.isPlaying;
    if (wasPlaying) { this.isPlaying = false; this._clearTimers(); this._stopVoices(); }
    this._offset = Math.max(0, Math.min(sec, this.duration || sec));
    this._scanIdx = 0;
    while (this._scanIdx < this._notes.length && this._notes[this._scanIdx].t < this._offset) this._scanIdx++;
    if (wasPlaying) this.play();
    else if (this._onProgress) this._onProgress(this._offset);
    return this;
  };

  Synth.prototype._finish = function () {
    if (this._endedFired) return;
    this._endedFired = true;
    this.isPlaying = false;
    this._clearTimers();
    this._offset = this.duration;
    if (this._onProgress) this._onProgress(this.duration);
    if (this._onEnded) this._onEnded();
  };

  // ----------------------------------------------------------------- export --
  return { parse: parse, Synth: Synth, FAMILY: FAMILY, instrFor: instrFor };
});

// ------------------------------------------------------------ node self-test --
if (typeof module !== 'undefined' && typeof require !== 'undefined' && require.main === module) {
  var fs = require('fs');
  var MidiEngine = module.exports;
  var SRC = process.argv[2] || '~/Downloads/七里香 周杰伦_爱给网_aigei_com.mid';
  var buf = fs.readFileSync(SRC);
  var res = MidiEngine.parse(buf);
  var notes = res.notes;

  // per-(ch,prog) aggregation
  var agg = {};
  for (var i = 0; i < notes.length; i++) {
    var n = notes[i];
    var key = n.ch + '|' + n.prog;
    if (!agg[key]) agg[key] = { ch: n.ch, prog: n.prog, instr: n.instr, count: 0, lo: 999, hi: -1 };
    var a = agg[key];
    a.count++;
    if (n.midi < a.lo) a.lo = n.midi;
    if (n.midi > a.hi) a.hi = n.midi;
  }
  var rows = Object.keys(agg).map(function (k) { return agg[k]; });
  rows.sort(function (a, b) { return (a.ch - b.ch) || (a.prog - b.prog); });

  console.log('file      :', SRC);
  console.log('format    :', res.format, ' ntrks:', res.ntrks, ' ppq:', res.ppq);
  console.log('duration  :', res.duration.toFixed(2), 'sec');
  console.log('total notes:', notes.length);
  console.log('per (ch,prog):');
  console.log('  ch  prog  instr   count   midi-range');
  for (var r = 0; r < rows.length; r++) {
    var x = rows[r];
    console.log(
      '  ' + String(x.ch).padStart(2) +
      '  ' + String(x.prog).padStart(4) +
      '  ' + x.instr.padEnd(6) +
      '  ' + String(x.count).padStart(5) +
      '   ' + x.lo + '-' + x.hi
    );
  }
}
