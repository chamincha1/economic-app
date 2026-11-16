import http from 'node:http';
import {readFile, stat} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {dirname, extname, join, relative, resolve, sep} from 'node:path';

const root=dirname(fileURLToPath(import.meta.url));
const useDist=process.argv.includes('--dist');
const publicRoot=resolve(root,useDist?'dist':'.');
const mime={'.html':'text/html; charset=utf-8','.css':'text/css; charset=utf-8','.js':'text/javascript; charset=utf-8','.mjs':'text/javascript; charset=utf-8','.svg':'image/svg+xml','.json':'application/json; charset=utf-8','.png':'image/png','.ico':'image/x-icon'};
function send(res,code,body,type='text/plain; charset=utf-8') {
  res.writeHead(code,{'Content-Type':type,'X-Content-Type-Options':'nosniff','Cache-Control':'no-store','Referrer-Policy':'no-referrer'});
  res.end(body);
}
export function createServer(base=publicRoot) {
  return http.createServer(async(req,res)=>{
    if(req.method!=='GET'&&req.method!=='HEAD') return send(res,405,'Method not allowed');
    let url;
    try { url=new URL(req.url??'/', 'http://localhost'); }
    catch {return send(res,400,'Bad URL');}
    if(url.pathname==='/api/health') return send(res,200,JSON.stringify({ok:true,product:'MARKET PULSE',mode:'web preview',marketData:'user CSV only'}),'application/json; charset=utf-8');
    let pathname;
    try {pathname=decodeURIComponent(url.pathname);}catch{return send(res,400,'Invalid path');}
    if(pathname.includes('\0')||pathname.includes('\\')||pathname.split('/').includes('..')) return send(res,403,'Forbidden');
    if(pathname==='/') pathname='/index.html';
    const target=resolve(base,'.'+pathname);
    const rel=relative(base,target);
    if(rel.startsWith('..'+sep)||rel==='..'||rel.startsWith(sep)) return send(res,403,'Forbidden');
    // Never serve Python source, API credentials, hidden files, or project internals.
    if(!['/index.html','/styles.css','/src/app.js','/src/analytics.js','/assets/catalog.json','/assets/favicon.svg'].includes(pathname)) {
      return send(res,404,'Not found');
    }
    try {
      const s=await stat(target);
      if(!s.isFile()||s.size>5*1024*1024) return send(res,404,'Not found');
      const content=await readFile(target);
      if(req.method==='HEAD') {res.writeHead(200,{'Content-Type':mime[extname(target)]??'application/octet-stream'});res.end();return;}
      return send(res,200,content,mime[extname(target)]??'application/octet-stream');
    }catch{return send(res,404,'Not found');}
  });
}
if(process.argv[1] && resolve(process.argv[1])===fileURLToPath(import.meta.url)) {
  const rawPort=process.env.PORT ?? '3000';
  const port=Number(rawPort);
  if(!Number.isInteger(port) || port<1 || port>65535){
    console.error(`Invalid PORT: ${rawPort} (expected integer 1..65535)`);
    process.exitCode=1;
  } else {
    const server=createServer();
    server.on('error',err=>{
      if(err.code==='EADDRINUSE') console.error(`PORT ${port} is in use. Set PORT to an available port or stop the old process.`);
      else console.error(`Server startup failed: ${err.message}`);
      process.exitCode=1;
    });
    server.listen(port,'0.0.0.0',()=>console.log(`MARKET PULSE web preview on http://localhost:${port}`));
  }
}
