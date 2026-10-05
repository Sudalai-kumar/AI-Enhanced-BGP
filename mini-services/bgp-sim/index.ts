import { createServer } from 'http';
import { Server } from 'socket.io';
import { BGPSimEngine, startWatchdog } from './src/engine';
import { ATTACK_SCENARIOS, SimState } from './src/types';

const httpServer = createServer((req, res) => {
  // lightweight health endpoint
  res.writeHead(200, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify({ ok: true, service: 'bgp-sim', time: Date.now() }));
});

const io = new Server(httpServer, {
  // DO NOT change the path, it is used by Caddy to forward the request to the correct port
  path: '/',
  cors: { origin: '*', methods: ['GET', 'POST'] },
  pingTimeout: 60000,
  pingInterval: 25000,
});

const engine = new BGPSimEngine();

// stalled-loop watchdog: self-heals the tick timer if it ever dies while running
startWatchdog(() => engine);

let lastState: SimState = engine.buildState();
engine.setOnChange((state) => {
  lastState = state;
  io.emit('sim:state', state);
  const lastEvent = state.events[state.events.length - 1];
  if (lastEvent) io.emit('event:new', lastEvent);
});

io.on('connection', (socket) => {
  console.log(`[bgp-sim] client connected: ${socket.id}`);

  socket.emit('sim:state', lastState);

  socket.on('sim:start', () => engine.start());
  socket.on('sim:pause', () => engine.pause());
  socket.on('sim:reset', () => engine.reset());
  socket.on('sim:tick', () => engine.tickOnce());

  socket.on('config:update', (patch: unknown, ack?: (r: { ok: boolean; error?: string }) => void) => {
    try {
      engine.setConfig(patch);
      ack?.({ ok: true });
    } catch (e) {
      ack?.({ ok: false, error: String(e) });
    }
  });

  socket.on('config:preset', (variant: string, ack?: (r: { ok: boolean }) => void) => {
    const ok = engine.applyPreset(String(variant ?? ''));
    ack?.({ ok });
  });

  socket.on('config:reset', () => {
    engine.resetConfig();
  });

  socket.on('attack:inject', (payload: { scenarioId: string; durationSec?: number }, ack?: (r: { ok: boolean }) => void) => {
    const ok = engine.injectScenario(String(payload?.scenarioId ?? ''), payload?.durationSec);
    ack?.({ ok });
  });

  socket.on('attack:custom', (spec: unknown, ack?: (r: { ok: boolean; error?: string }) => void) => {
    try {
      const result = engine.injectCustom(spec as never);
      ack?.(result);
    } catch (e) {
      ack?.({ ok: false, error: String(e) });
    }
  });

  socket.on('attack:withdraw', () => engine.withdrawAttack());

  socket.on('scenarios:list', (ack?: (r: unknown) => void) => {
    ack?.(ATTACK_SCENARIOS);
  });

  socket.on('disconnect', () => {
    console.log(`[bgp-sim] client disconnected: ${socket.id}`);
  });
});

const PORT = 3010;
httpServer.listen(PORT, () => {
  console.log(`[bgp-sim] BGP simulation engine listening on port ${PORT}`);
});

process.on('SIGTERM', () => {
  httpServer.close(() => process.exit(0));
});
process.on('SIGINT', () => {
  httpServer.close(() => process.exit(0));
});
