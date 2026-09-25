const canvas = document.querySelector('#cloud-canvas');
const loading = document.querySelector('#loading');
const errorBox = document.querySelector('#scene-error');
const pointCount = document.querySelector('#point-count');
const resetButton = document.querySelector('#reset-view');
const gl = canvas.getContext('webgl', { antialias: true, alpha: false });

let yaw = 2.7;
let pitch = -1.0;
let distance = 1.65;
let dragging = false;
let lastPointer = null;
let pointBuffer;
let colorBuffer;
let vertexCount = 0;
let center = [0, 0, 0];
let extent = 1;
let program;

function typeSize(type) {
  return ({ char: 1, uchar: 1, int8: 1, uint8: 1, short: 2, ushort: 2, int16: 2, uint16: 2, int: 4, uint: 4, int32: 4, uint32: 4, float: 4, float32: 4, double: 8, float64: 8 })[type] || 0;
}

function readValue(view, offset, type) {
  const readers = { char: 'getInt8', int8: 'getInt8', uchar: 'getUint8', uint8: 'getUint8', short: 'getInt16', int16: 'getInt16', ushort: 'getUint16', uint16: 'getUint16', int: 'getInt32', int32: 'getInt32', uint: 'getUint32', uint32: 'getUint32', float: 'getFloat32', float32: 'getFloat32', double: 'getFloat64', float64: 'getFloat64' };
  return view[readers[type]](offset, true);
}

function parsePly(buffer) {
  const bytes = new Uint8Array(buffer);
  const preview = new TextDecoder('ascii').decode(bytes.subarray(0, Math.min(bytes.length, 20000)));
  const headerEnd = preview.indexOf('end_header\n');
  if (headerEnd < 0 || !preview.includes('format binary_little_endian 1.0')) throw new Error('This viewer expects a binary little-endian PLY point cloud.');
  const header = preview.slice(0, headerEnd).split('\n');
  const count = Number(header.find(line => line.startsWith('element vertex '))?.split(' ').at(-1));
  const properties = header.filter(line => line.startsWith('property ')).map(line => { const [, type, name] = line.split(' '); return { type, name, size: typeSize(type) }; });
  const stride = properties.reduce((sum, property) => sum + property.size, 0);
  const dataStart = headerEnd + 'end_header\n'.length;
  if (!count || !stride || dataStart + count * stride > bytes.byteLength) throw new Error('The point cloud header or vertex data is incomplete.');
  const values = new DataView(buffer, dataStart);
  const positions = new Float32Array(count * 3);
  const colors = new Float32Array(count * 3);
  const minimum = [Infinity, Infinity, Infinity];
  const maximum = [-Infinity, -Infinity, -Infinity];
  for (let vertex = 0; vertex < count; vertex++) {
    let offset = vertex * stride;
    const item = {};
    for (const property of properties) { item[property.name] = readValue(values, offset, property.type); offset += property.size; }
    const target = vertex * 3;
    positions[target] = item.x; positions[target + 1] = item.y; positions[target + 2] = item.z;
    colors[target] = (item.red ?? 120) / 255; colors[target + 1] = (item.green ?? 208) / 255; colors[target + 2] = (item.blue ?? 194) / 255;
    for (let axis = 0; axis < 3; axis++) { minimum[axis] = Math.min(minimum[axis], positions[target + axis]); maximum[axis] = Math.max(maximum[axis], positions[target + axis]); }
  }
  center = minimum.map((value, axis) => (value + maximum[axis]) / 2);
  extent = Math.max(...maximum.map((value, axis) => value - minimum[axis])) || 1;
  return { positions, colors, count };
}

function shader(type, source) {
  const compiled = gl.createShader(type); gl.shaderSource(compiled, source); gl.compileShader(compiled);
  if (!gl.getShaderParameter(compiled, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(compiled));
  return compiled;
}

function multiply(a, b) {
  const output = new Float32Array(16);
  for (let column = 0; column < 4; column++) for (let row = 0; row < 4; row++) output[column * 4 + row] = a[row] * b[column * 4] + a[4 + row] * b[column * 4 + 1] + a[8 + row] * b[column * 4 + 2] + a[12 + row] * b[column * 4 + 3];
  return output;
}
function identity() { return new Float32Array([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]); }
function perspective(fovy, aspect, near, far) { const f = 1 / Math.tan(fovy / 2); return new Float32Array([f / aspect, 0, 0, 0, 0, f, 0, 0, 0, 0, (far + near) / (near - far), -1, 0, 0, 2 * far * near / (near - far), 0]); }
function translate(x, y, z) { const m = identity(); m[12] = x; m[13] = y; m[14] = z; return m; }
function scale(value) { const m = identity(); m[0] = m[5] = m[10] = value; return m; }
function rotateX(angle) { const c = Math.cos(angle), s = Math.sin(angle); return new Float32Array([1, 0, 0, 0, 0, c, s, 0, 0, -s, c, 0, 0, 0, 0, 1]); }
function rotateY(angle) { const c = Math.cos(angle), s = Math.sin(angle); return new Float32Array([c, 0, -s, 0, 0, 1, 0, 0, s, 0, c, 0, 0, 0, 0, 1]); }

function setupGl(data) {
  if (!gl) throw new Error('WebGL is unavailable in this browser. Open this dashboard in Chrome or Firefox.');
  const vertex = shader(gl.VERTEX_SHADER, 'attribute vec3 aPosition; attribute vec3 aColor; uniform mat4 uMatrix; varying vec3 vColor; void main(){ gl_Position=uMatrix*vec4(aPosition,1.0); gl_PointSize=3.0; vColor=aColor; }');
  const fragment = shader(gl.FRAGMENT_SHADER, 'precision mediump float; varying vec3 vColor; void main(){ float d=distance(gl_PointCoord,vec2(.5)); if(d>.5) discard; vec3 visibleColor=min(vColor*1.75+vec3(.10),vec3(1.0)); gl_FragColor=vec4(visibleColor,1.0); }');
  program = gl.createProgram(); gl.attachShader(program, vertex); gl.attachShader(program, fragment); gl.linkProgram(program);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(program));
  pointBuffer = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, pointBuffer); gl.bufferData(gl.ARRAY_BUFFER, data.positions, gl.STATIC_DRAW);
  colorBuffer = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, colorBuffer); gl.bufferData(gl.ARRAY_BUFFER, data.colors, gl.STATIC_DRAW);
  vertexCount = data.count;
  gl.enable(gl.DEPTH_TEST); gl.enable(gl.BLEND); gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
}

function render() {
  if (!program) return;
  const pixelRatio = Math.min(window.devicePixelRatio || 1, 2);
  const width = Math.floor(canvas.clientWidth * pixelRatio), height = Math.floor(canvas.clientHeight * pixelRatio);
  if (canvas.width !== width || canvas.height !== height) { canvas.width = width; canvas.height = height; }
  gl.viewport(0, 0, width, height); gl.clearColor(.024, .11, .16, 1); gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
  const model = multiply(rotateX(pitch), multiply(rotateY(yaw), multiply(scale(1 / extent), translate(-center[0], -center[1], -center[2]))));
  const matrix = multiply(perspective(Math.PI / 3, width / height, .01, 30), multiply(translate(0, 0, -distance), model));
  gl.useProgram(program);
  gl.uniformMatrix4fv(gl.getUniformLocation(program, 'uMatrix'), false, matrix);
  const position = gl.getAttribLocation(program, 'aPosition'); gl.bindBuffer(gl.ARRAY_BUFFER, pointBuffer); gl.enableVertexAttribArray(position); gl.vertexAttribPointer(position, 3, gl.FLOAT, false, 0, 0);
  const color = gl.getAttribLocation(program, 'aColor'); gl.bindBuffer(gl.ARRAY_BUFFER, colorBuffer); gl.enableVertexAttribArray(color); gl.vertexAttribPointer(color, 3, gl.FLOAT, false, 0, 0);
  gl.drawArrays(gl.POINTS, 0, vertexCount);
  requestAnimationFrame(render);
}

canvas.addEventListener('pointerdown', event => { dragging = true; lastPointer = [event.clientX, event.clientY]; canvas.setPointerCapture(event.pointerId); });
canvas.addEventListener('pointermove', event => { if (!dragging) return; yaw += (event.clientX - lastPointer[0]) * .008; pitch = Math.max(-1.45, Math.min(1.45, pitch + (event.clientY - lastPointer[1]) * .008)); lastPointer = [event.clientX, event.clientY]; });
canvas.addEventListener('pointerup', () => { dragging = false; });
canvas.addEventListener('wheel', event => { event.preventDefault(); distance = Math.max(1.2, Math.min(8, distance + event.deltaY * .004)); }, { passive: false });
resetButton.addEventListener('click', () => { yaw = 2.7; pitch = -1.0; distance = 1.65; });

fetch('assets/dense_point_cloud.ply').then(response => response.ok ? response : fetch('assets/sparse_point_cloud.ply'))
  .then(response => { if (!response.ok) throw new Error('The current PLY model could not be loaded.'); return response.arrayBuffer(); })
  .then(parsePly)
  .then(data => { setupGl(data); pointCount.textContent = data.count.toLocaleString(); loading.hidden = true; requestAnimationFrame(render); })
  .catch(error => { loading.hidden = true; errorBox.hidden = false; errorBox.textContent = error.message; });
