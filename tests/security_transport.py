"""Start an isolated frontend with a stub API; never uses live data or credentials."""
import contextlib,http.client,http.server,json,os,socket,ssl,subprocess,sys,tempfile,threading,time
from pathlib import Path
root=Path(__file__).resolve().parents[1]
name=root.name
node=os.environ.get('NODE_BINARY','/home/jongwook/.nvm/versions/node/v24.20.0/bin/node')
class API(http.server.BaseHTTPRequestHandler):
 def do_GET(self):
  self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(b'{"status":"ok"}')
 def log_message(self,*args):pass
api=http.server.ThreadingHTTPServer(('127.0.0.1',0),API)
threading.Thread(target=api.serve_forever,daemon=True).start()
def freeport():
 with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]
results=[]
try:
 with tempfile.TemporaryDirectory(prefix='security-transport-') as tmp:
  tmp=Path(tmp);key=tmp/'key.pem';cert=tmp/'cert.pem'
  subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(key),'-out',str(cert),'-days','1','-subj','/CN=localhost','-addext','subjectAltName=DNS:localhost,IP:127.0.0.1'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True)
  modes=['https'] if name=='wiareport' else ['http'] if name=='wiavoice' else ['http','https']
  for mode in modes:
   port=freeport();env={**os.environ,'FRONTEND_PROTOCOL':mode,'FRONTEND_PORT':str(port),'FRONTEND_HOST':'0.0.0.0','BACKEND_ORIGIN':f'http://127.0.0.1:{api.server_port}',
    'TLS_CERT':str(cert),'TLS_KEY':str(key),'WIANEWS_TLS_CERT':str(cert),'WIANEWS_TLS_KEY':str(key),'WIAREPORT_TLS_CERT_FILE':str(cert),'WIAREPORT_TLS_KEY_FILE':str(key)}
   args=[node,str(root/'frontend/server.mjs')] if name!='wiareport' else [node,str(root/'frontend/node_modules/vite/bin/vite.js'),'preview','--host','127.0.0.1','--port',str(port),'--strictPort']
   with open(tmp/'server.log','wb') as log:p=subprocess.Popen(args,cwd=root/'frontend',env=env,stdout=log,stderr=log)
   try:
    for _ in range(100):
     if p.poll() is not None:raise AssertionError((tmp/'server.log').read_text())
     try:
      with socket.create_connection(('127.0.0.1',port),timeout=.2):break
     except OSError:time.sleep(.1)
    else:raise AssertionError('startup timeout')
    def request(path):
     c=http.client.HTTPSConnection('localhost',port,context=ssl.create_default_context(cafile=str(cert)),timeout=5) if mode=='https' else http.client.HTTPConnection('127.0.0.1',port,timeout=5)
     c.request('GET',path);r=c.getresponse();body=r.read();status=r.status;c.close();return status,body
    assert request('/')[0]==200
    assert request('/api/health')[0]==200
    for path in ('/%','/%GG','/%E0%A4%A','/agent/%'):
     code,body=request(path);assert code==400,(mode,path,code)
     assert all(x not in body for x in (b'node_modules',b'/home/',b'/tmp/',b'Traceback',b'URIError'))
    assert request('/agent')[0]==200
    code,html=request('/')
    import re
    for asset in re.findall(rb'(?:src|href)="([^" ]+\.(?:js|css))"',html):
     path=asset.decode();path='/'+path.lstrip('./')
     assert request(path)[0]==200,path
    if mode=='http':
     entries=[]
     for file in ('/proc/net/tcp','/proc/net/tcp6'):
      for line in Path(file).read_text().splitlines()[1:]:
       f=line.split()
       if f[3]=='0A' and int(f[1].split(':')[1],16)==port:entries.append(f[1].split(':')[0])
     assert entries==['0100007F'],entries
    else:
     for cipher in ('ECDHE-RSA-AES128-SHA256','AES128-GCM-SHA256'):
      ctx=ssl.create_default_context(cafile=str(cert));ctx.minimum_version=ctx.maximum_version=ssl.TLSVersion.TLSv1_2;ctx.set_ciphers(cipher+':@SECLEVEL=0')
      try:
       with socket.create_connection(('127.0.0.1',port),timeout=3) as raw:
        with ctx.wrap_socket(raw,server_hostname='localhost'):pass
      except ssl.SSLError:pass
      else:raise AssertionError('Weak cipher accepted: '+cipher)
    results.append({'service':name,'mode':mode,'static_and_assets':200,'api_proxy':200,'malformed_paths':400,'http_loopback_only':mode=='http','weak_tls_rejected':mode=='https'})
   finally:
    p.terminate()
    try:p.wait(timeout=15)
    except subprocess.TimeoutExpired:p.kill();p.wait()
finally:api.shutdown();api.server_close()
print(json.dumps(results))
