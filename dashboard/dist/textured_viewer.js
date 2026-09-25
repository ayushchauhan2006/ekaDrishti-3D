const canvas = document.querySelector('#model-canvas');
const loading = document.querySelector('#loading');
const errorBox = document.querySelector('#scene-error');
const resetButton = document.querySelector('#reset-view');
const gl = canvas.getContext('webgl', { antialias: true, alpha: false });
let yaw = 3.9, pitch = -1.45, distance = 1.22, panX = 0, panY = 0, panning = false, dragging = false, lastPointer;
let program, positionBuffer, uvBuffer, vertexCount = 0, center = [0, 0, 0], extent = 1;

function parseMesh(buffer) {
  const bytes = new Uint8Array(buffer);
  const text = new TextDecoder('ascii').decode(bytes.subarray(0, Math.min(bytes.length, 20000)));
  const marker = 'end_header\n', end = text.indexOf(marker);
  if (end < 0 || !text.includes('format binary_little_endian 1.0')) throw new Error('The textured mesh is not a supported binary PLY file.');
  const lines = text.slice(0, end).split('\n');
  const vertices = Number(lines.find(line => line.startsWith('element vertex '))?.split(' ').at(-1));
  const faces = Number(lines.find(line => line.startsWith('element face '))?.split(' ').at(-1));
  if (!vertices || !faces) throw new Error('The mesh does not contain vertices and triangles.');
  const start = end + marker.length, view = new DataView(buffer);
  const points = new Float32Array(vertices * 3);
  const min = [Infinity, Infinity, Infinity], max = [-Infinity, -Infinity, -Infinity];
  for (let i = 0; i < vertices; i++) {
    for (let axis = 0; axis < 3; axis++) {
      const value = view.getFloat32(start + i * 12 + axis * 4, true);
      points[i * 3 + axis] = value; min[axis] = Math.min(min[axis], value); max[axis] = Math.max(max[axis], value);
    }
  }
  let offset = start + vertices * 12;
  const positions = [], uvs = [];
  for (let face = 0; face < faces; face++) {
    const count = view.getUint8(offset); offset += 1;
    const indices = [];
    for (let i = 0; i < count; i++) { indices.push(view.getInt32(offset, true)); offset += 4; }
    const uvCount = view.getUint8(offset); offset += 1;
    const faceUvs = [];
    for (let i = 0; i < uvCount; i++) { faceUvs.push(view.getFloat32(offset, true)); offset += 4; }
    if (count < 3 || uvCount < count * 2) continue;
    for (let triangle = 1; triangle < count - 1; triangle++) {
      for (const slot of [0, triangle, triangle + 1]) {
        const index = indices[slot]; positions.push(points[index * 3], points[index * 3 + 1], points[index * 3 + 2]);
        uvs.push(faceUvs[slot * 2], faceUvs[slot * 2 + 1]);
      }
    }
  }
  const percentileBounds = [0, 1, 2].map(axis => { const values = Array.from({ length: vertices }, (_, index) => points[index * 3 + axis]).sort((a, b) => a - b); return [values[Math.floor(vertices * 0.02)], values[Math.ceil(vertices * 0.98) - 1]]; }); center = percentileBounds.map(([low, high]) => (low + high) / 2); extent = Math.max(...percentileBounds.map(([low, high]) => high - low)) || 1;
  return { positions: new Float32Array(positions), uvs: new Float32Array(uvs) };
}
function shader(type, source) { const compiled = gl.createShader(type); gl.shaderSource(compiled, source); gl.compileShader(compiled); if (!gl.getShaderParameter(compiled, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(compiled)); return compiled; }
function multiply(a, b) { const out = new Float32Array(16); for (let c = 0; c < 4; c++) for (let r = 0; r < 4; r++) out[c * 4 + r] = a[r] * b[c * 4] + a[4 + r] * b[c * 4 + 1] + a[8 + r] * b[c * 4 + 2] + a[12 + r] * b[c * 4 + 3]; return out; }
function identity() { return new Float32Array([1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1]); }
function perspective(f, a, n, z) { const q = 1 / Math.tan(f / 2); return new Float32Array([q/a,0,0,0,0,q,0,0,0,0,(z+n)/(n-z),-1,0,0,2*z*n/(n-z),0]); }
function translate(x, y, z) { const m = identity(); m[12] = x; m[13] = y; m[14] = z; return m; }
function scale(value) { const m = identity(); m[0] = m[5] = m[10] = value; return m; }
function rotateX(angle) { const c = Math.cos(angle), s = Math.sin(angle); return new Float32Array([1,0,0,0,0,c,s,0,0,-s,c,0,0,0,0,1]); }
function rotateY(angle) { const c = Math.cos(angle), s = Math.sin(angle); return new Float32Array([c,0,-s,0,0,1,0,0,s,0,c,0,0,0,0,1]); }
function wrapTurn(angle) { const turn = Math.PI * 2; return ((angle + Math.PI) % turn + turn) % turn - Math.PI; }
function loadImage(url) { return new Promise((resolve, reject) => { const image = new Image(); image.onload = () => resolve(image); image.onerror = () => reject(new Error('The terrain texture could not be loaded.')); image.src = url; }); }
function setup(data, image) {
  if (!gl) throw new Error('WebGL is unavailable in this browser. Open this dashboard in Chrome or Firefox.');
  const vertex = shader(gl.VERTEX_SHADER, 'attribute vec3 aPosition; attribute vec2 aUv; uniform mat4 uMatrix; varying vec2 vUv; void main(){gl_Position=uMatrix*vec4(aPosition,1.0);vUv=aUv;}');
  const fragment = shader(gl.FRAGMENT_SHADER, 'precision mediump float; varying vec2 vUv; uniform sampler2D uTexture; void main(){vec4 color=texture2D(uTexture,vUv);if(dot(color.rgb,vec3(.2126,.7152,.0722))<.018)discard;gl_FragColor=color;}');
  program = gl.createProgram(); gl.attachShader(program, vertex); gl.attachShader(program, fragment); gl.linkProgram(program); if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(program));
  positionBuffer = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, positionBuffer); gl.bufferData(gl.ARRAY_BUFFER, data.positions, gl.STATIC_DRAW);
  uvBuffer = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, uvBuffer); gl.bufferData(gl.ARRAY_BUFFER, data.uvs, gl.STATIC_DRAW);
  const texture = gl.createTexture(); gl.bindTexture(gl.TEXTURE_2D, texture); gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, true); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE); gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, image);
  vertexCount = data.positions.length / 3; gl.enable(gl.DEPTH_TEST);
}
function render() {
  if (!program) return; const ratio = Math.min(window.devicePixelRatio || 1, 2), width = Math.floor(canvas.clientWidth * ratio), height = Math.floor(canvas.clientHeight * ratio); if (canvas.width !== width || canvas.height !== height) { canvas.width = width; canvas.height = height; }
  gl.viewport(0,0,width,height); gl.clearColor(.024,.11,.16,1); gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
  const model = multiply(rotateX(pitch), multiply(rotateY(yaw), multiply(scale(1/extent), translate(-center[0],-center[1],-center[2]))));
  const matrix = multiply(perspective(Math.PI/3,width/height,.01,30), multiply(translate(panX,panY,-distance),model)); gl.useProgram(program); gl.uniformMatrix4fv(gl.getUniformLocation(program,'uMatrix'),false,matrix);
  const position = gl.getAttribLocation(program,'aPosition'); gl.bindBuffer(gl.ARRAY_BUFFER,positionBuffer); gl.enableVertexAttribArray(position); gl.vertexAttribPointer(position,3,gl.FLOAT,false,0,0);
  const uv = gl.getAttribLocation(program,'aUv'); gl.bindBuffer(gl.ARRAY_BUFFER,uvBuffer); gl.enableVertexAttribArray(uv); gl.vertexAttribPointer(uv,2,gl.FLOAT,false,0,0); gl.drawArrays(gl.TRIANGLES,0,vertexCount); requestAnimationFrame(render);
}
canvas.addEventListener('pointerdown', event => { dragging = true; panning = event.shiftKey || event.button === 2; lastPointer = [event.clientX,event.clientY]; canvas.setPointerCapture(event.pointerId); });
canvas.addEventListener('pointermove', event => { if (!dragging) return; const dx = event.clientX-lastPointer[0], dy = event.clientY-lastPointer[1]; if (panning) { panX += dx / canvas.clientWidth * distance * 1.1; panY -= dy / canvas.clientHeight * distance * 1.1; } else { yaw = wrapTurn(yaw + dx*.008); pitch = wrapTurn(pitch + dy*.008); } lastPointer = [event.clientX,event.clientY]; });
canvas.addEventListener('contextmenu', event => event.preventDefault());
canvas.addEventListener('pointerup', () => { dragging = false; panning = false; }); canvas.addEventListener('wheel', event => { event.preventDefault(); distance = Math.max(.06,Math.min(30,distance*Math.exp(event.deltaY*.0015))); },{passive:false}); resetButton.addEventListener('click',() => { yaw=3.9; pitch=-1.45; distance=1.22; panX=0; panY=0; });
Promise.all([fetch('assets/dense_textured_mesh.ply').then(response => { if (!response.ok) throw new Error('The textured mesh file could not be loaded.'); return response.arrayBuffer(); }),loadImage('assets/dense_texture.png')]).then(([mesh,image]) => { setup(parseMesh(mesh),image); loading.hidden=true; requestAnimationFrame(render); }).catch(error => { loading.hidden=true; errorBox.hidden=false; errorBox.textContent=error.message; });
