import {mkdir, copyFile, rm} from 'node:fs/promises';
import {resolve, dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
await rm(resolve(root,'dist'),{recursive:true,force:true});
for(const item of ['index.html','styles.css','src/app.js','src/analytics.js','assets/catalog.json','assets/favicon.svg']) {
  const dest=resolve(root,'dist',item);
  await mkdir(dirname(dest),{recursive:true});
  await copyFile(resolve(root,item),dest);
}
console.log('Built static web preview to dist/ (no npm dependencies).');
