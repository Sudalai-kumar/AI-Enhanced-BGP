/**
 * NOC sound alert system — Web Audio API oscillator tones (no audio assets).
 * Lazily creates the AudioContext on first user gesture; muted state persists
 * in localStorage.
 */

export type AlertTone = 'inject' | 'detection' | 'quarantine' | 'success' | 'failed' | 'watch';

const STORAGE_KEY = 'bgp-noc-muted';

let ctx: AudioContext | null = null;
let muted = typeof window !== 'undefined' && window.localStorage.getItem(STORAGE_KEY) === '1';

/** Create/resume the AudioContext (must be called from a user-gesture context at least once). */
function ensureCtx(): AudioContext | null {
  if (typeof window === 'undefined') return null;
  if (!ctx) {
    const AC = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!AC) return null;
    ctx = new AC();
  }
  if (ctx.state === 'suspended') {
    void ctx.resume();
  }
  return ctx;
}

/** Call once on app mount: unlocks audio on the first pointer/key gesture. */
export function primeAudioUnlock(): () => void {
  if (typeof window === 'undefined') return () => undefined;
  const unlock = () => {
    ensureCtx();
    window.removeEventListener('pointerdown', unlock);
    window.removeEventListener('keydown', unlock);
  };
  window.addEventListener('pointerdown', unlock);
  window.addEventListener('keydown', unlock);
  return () => {
    window.removeEventListener('pointerdown', unlock);
    window.removeEventListener('keydown', unlock);
  };
}

interface ToneSpec {
  freqs: number[]; // sequential notes
  dur: number; // per-note seconds
  type: OscillatorType;
  gain: number;
  gap: number; // pause between notes (seconds)
}

const TONES: Record<AlertTone, ToneSpec> = {
  // low double-thud: something entered the testbed
  inject: { freqs: [220, 165], dur: 0.09, type: 'triangle', gain: 0.16, gap: 0.05 },
  // rising attention pair: anomaly detected
  detection: { freqs: [659, 880], dur: 0.11, type: 'sine', gain: 0.14, gap: 0.06 },
  // urgent descending minor: route quarantined
  quarantine: { freqs: [880, 587, 440], dur: 0.1, type: 'square', gain: 0.07, gap: 0.04 },
  // resolving major arpeggio: rollback complete / mitigated
  success: { freqs: [523, 659, 784], dur: 0.12, type: 'sine', gain: 0.12, gap: 0.05 },
  // single low buzz: mitigation failed
  failed: { freqs: [147], dur: 0.28, type: 'sawtooth', gain: 0.08, gap: 0 },
  // watchlist siren: watched prefix changed state — urgent repeating fifth
  watch: { freqs: [740, 988, 740, 988], dur: 0.08, type: 'triangle', gain: 0.13, gap: 0.03 },
};

/** Play one alert tone (no-op when muted or audio unavailable). */
export function playAlert(tone: AlertTone): void {
  if (muted) return;
  const audio = ensureCtx();
  if (!audio || audio.state !== 'running') return;
  const spec = TONES[tone];
  const now = audio.currentTime;
  let t = now;
  for (const freq of spec.freqs) {
    const osc = audio.createOscillator();
    const gain = audio.createGain();
    osc.type = spec.type;
    osc.frequency.value = freq;
    // envelope: fast attack, exponential release
    gain.gain.setValueAtTime(0.0001, t);
    gain.gain.exponentialRampToValueAtTime(spec.gain, t + 0.012);
    gain.gain.exponentialRampToValueAtTime(0.0001, t + spec.dur);
    osc.connect(gain).connect(audio.destination);
    osc.start(t);
    osc.stop(t + spec.dur + 0.02);
    t += spec.dur + spec.gap;
  }
}

export function isMuted(): boolean {
  return muted;
}

export function setMuted(next: boolean): void {
  muted = next;
  if (typeof window !== 'undefined') {
    try {
      window.localStorage.setItem(STORAGE_KEY, next ? '1' : '0');
    } catch {
      /* storage unavailable — session-only mute */
    }
  }
}

/** Map a live engine event to an alert tone (null = no sound). */
export function alertForEvent(source: string, level: string, message: string): AlertTone | null {
  if (source === 'attack' && /injected/i.test(message)) return 'inject';
  if (source === 'detection' && level !== 'info') return 'detection';
  if (source === 'policy' && /Quarantine/i.test(message) && level === 'danger') return 'quarantine';
  if (source === 'rollback' && level === 'success') return 'success';
  if (source === 'metrics' && /failed|missed/i.test(message)) return 'failed';
  return null;
}
