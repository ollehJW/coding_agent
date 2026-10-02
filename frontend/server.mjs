// Serve the built frontend over HTTPS and stream API requests to the local backend.
// The original Host header is kept: the backend rejects writes whose Origin differs from Host.
import https from 'node:https';
import http from 'node:http';
import { readFileSync, createReadStream } from 'node:fs';
import { stat, realpath } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { resolve, sep, extname } from 'node:path';

const root = await realpath(fileURLToPath(new URL('./dist', import.meta.url)));
const target = new URL(process.env.BACKEND_ORIGIN || 'http://127.0.0.1:9901');
if (target.protocol !== 'http:' || !['127.0.0.1', 'localhost'].includes(target.hostname)) throw new Error('Backend must be local HTTP');
const options = { cert: readFileSync(process.env.TLS_CERT), key: readFileSync(process.env.TLS_KEY), minVersion: 'TLSv1.2' };
const mime = { '.mp4': 'video/mp4', '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation', '.ppt': 'application/vnd.ms-powerpoint', '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.json': 'application/json', '.svg': 'image/svg+xml', '.png': 'image/png', '.ico': 'image/x-icon', '.woff2': 'font/woff2', '.txt': 'text/plain; charset=utf-8' };
const hop = new Set(['connection', 'keep-alive', 'proxy-authenticate', 'proxy-authorization', 'te', 'trailer', 'transfer-encoding', 'upgrade']);
function withoutHop(headers) {
  const blocked = new Set([...hop, ...String(headers.connection || '').toLowerCase().split(',').map(value => value.trim())]);
  return Object.fromEntries(Object.entries(headers).filter(([key]) => !blocked.has(key)));
}
function error(res, status, message) {
  if (res.headersSent) { res.destroy(); return; }
  res.writeHead(status, { 'Content-Type': 'text/plain; charset=utf-8', 'Cache-Control': 'no-store' });
  res.end(message);
}

const server = https.createServer(options, async (req, res) => {
  res.setHeader('X-Content-Type-Options', 'nosniff');
  res.setHeader('Strict-Transport-Security', 'max-age=31536000');
  let pathname;
  try { pathname = decodeURIComponent(new URL(req.url, 'https://localhost').pathname); } catch { return error(res, 400, 'Invalid URL'); }
  if (pathname === '/api' || pathname.startsWith('/api/')) {
    const headers = { ...withoutHop(req.headers), 'x-forwarded-proto': 'https', 'x-forwarded-for': req.socket.remoteAddress };
    const upstream = http.request({ hostname: target.hostname, port: target.port || 80, path: req.url, method: req.method, headers }, reply => {
      res.writeHead(reply.statusCode, withoutHop(reply.headers)); res.flushHeaders(); reply.pipe(res);
      reply.on('error', () => res.destroy());
    });
    upstream.setTimeout(200000, () => upstream.destroy());  // Background Agent turns may take up to 150s.
    upstream.on('error', () => error(res, 502, 'Backend unavailable'));
    req.on('aborted', () => upstream.destroy());
    res.on('close', () => { if (!res.writableEnded) upstream.destroy(); });
    req.pipe(upstream);
    return;
  }
  if (!['GET', 'HEAD'].includes(req.method)) return error(res, 405, 'Method not allowed');
  if (pathname === '/agent/') {
    res.writeHead(308, { Location: '/agent' + new URL(req.url, 'https://localhost').search, 'Cache-Control': 'no-store' });
    res.end(); return;
  }
  if (pathname.split('/').some(part => part.startsWith('.'))) return error(res, 404, 'Not found');
  try {
    let filename = resolve(root, '.' + pathname);
    if (filename !== root && !filename.startsWith(root + sep)) return error(res, 403, 'Forbidden');
    let info;
    try { info = await stat(filename); } catch {}
    if (!info?.isFile()) {
      if (extname(pathname) || pathname.startsWith('/assets/')) return error(res, 404, 'Not found');
      filename = resolve(root, 'index.html'); info = await stat(filename);
    }
    filename = await realpath(filename);
    if (!filename.startsWith(root + sep)) return error(res, 403, 'Forbidden');
    res.writeHead(200, { 'Content-Type': mime[extname(filename)] || 'application/octet-stream', 'Content-Length': info.size,
      'Cache-Control': pathname.startsWith('/assets/') ? 'public, max-age=31536000, immutable' : 'no-cache' });
    if (req.method === 'HEAD') return res.end();
    const stream = createReadStream(filename); stream.on('error', () => res.destroy()); stream.pipe(res);
  } catch { error(res, 500, 'Unable to serve frontend'); }
});
server.requestTimeout = 200000;
const port = Number(process.env.FRONTEND_PORT || 9902);
server.listen(port, process.env.FRONTEND_HOST || '0.0.0.0', () => console.log(`WiaCoding HTTPS frontend listening on ${port}`));
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => { server.close(() => process.exit(0)); setTimeout(() => process.exit(0), 30000).unref(); });
