// Offline Viz.js adapter. Native Graphviz is also supported by the Python caller.
'use strict';
const fs = require('node:fs');
const modulePath = process.argv[2] || '@viz-js/viz';
(async () => {
  const { instance } = require(modulePath);
  const viz = await instance();
  const result = viz.renderJSON(fs.readFileSync(0, 'utf8'), { engine: 'dot' });
  result.engineVersion = viz.graphvizVersion;
  process.stdout.write(JSON.stringify(result));
})().catch(error => { process.stderr.write(String(error)); process.exitCode = 1; });
