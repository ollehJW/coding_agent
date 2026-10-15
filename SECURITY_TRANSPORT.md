# Security transport (2026-10-15)

Plain HTTP frontend listeners bind only to 127.0.0.1 and are intended for the local AX gateway. Use https://axforwork.wia.co.kr/wiacoding/ for browser access. Direct external HTTP ports are intentionally unavailable.
Standalone HTTPS mode retains FRONTEND_HOST configuration and permits only TLS 1.2/1.3 with forward-secret AEAD cipher suites.
