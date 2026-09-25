const canvas = document.querySelector('#model-canvas');
const loading = document.querySelector('#loading');
const errorBox = document.querySelector('#scene-error');
const gl = canvas.getContext('webgl', { antialias: true, alpha: false });

let yaw = 2.45;
let pitch = -0.93;
let distance = 1.72;
let dragging = false;
let lastPointer;
let program;
let geometry;
let activeMode = 'mesh';
const cache = new Map();

const sources = {
  mesh: 'assets/presentation_mesh.ply',
  points: 'assets/georeferenced_point_cloud.ply',
  confidence: 'assets/confidence_point_cloud.ply',
};

const sizes = { char: 1, uchar: 1, int8: 1, uint8: 1, short: 2, ushort: 2, int16: 2, uint16: 2, int: 4, uint: 4, int32: 4, uint32: 4, float: 4, float32: 4, double: 8, float64: 8 };
const readers = { char: 'getInt8', int8: 'getInt8', uchar: 'getUint8', uint8: 'getUint8', short: 'getInt16', int16: 'getInt16', ushort: 'getUint16', uint16: 'getUint16', int: 'getInt32', int32: 'getInt32', uint: 'getUint32', uint32: 'getUint32', float: 'getFloat32', float32: 'getFloat32', double: 'getFloat64', float64: 'getFloat64' };

function readValue(view, offset, type) {
  const reader = readers[type];
  if (!reader) throw new Error(`Unsupported PLY value type: ${type}`);
  return view[reader](offset, true);
}

function parsePly(buffer) {
  const bytes = new Uint8Array(buffer);
  const preview = new TextDecoder('ascii').decode(bytes.subarray(0, Math.min(bytes.length, 65536)));
  const marker = 'end_header\n';
  const headerEnd = preview.indexOf(marker);
  if (headerEnd < 0 || !preview.includes('format binary_little_endian 1.0')) {
    throw new Error('The model is not a supported binary little-endian PLY file.');
  }
  const lines = preview.slice(0, headerEnd).split('\n');
  let element = '';
  let vertexCount = 0;
  let faceCount = 0;
  const vertexProperties = [];
  let faceCountType = 'uchar';
  let faceIndexType = 'uint';
  for (const line of lines) {
    const fields = line.trim().split(/\s+/);
    if (fields[0] === 'element') {
      element = fields[1];
      if (element === 'vertex') vertexCount = Number(fields[2]);
      if (element === 'face') faceCount = Number(fields[2]);
    } else if (fields[0] === 'property' && element === 'vertex') {
      vertexProperties.push({ type: fields[1], name: fields[2], size: sizes[fields[1]] });
    } else if (fields[0] === 'property' && fields[1] === 'list' && element === 'face') {
      faceCountType = fields[2];
      faceIndexType = fields[3];
    }
  }
  const stride = vertexProperties.reduce((sum, item) => sum + item.size, 0);
  const dataStart = headerEnd + marker.length;
  if (!vertexCount || !stride || dataStart + vertexCount * stride > buffer.byteLength) throw new Error('The PLY vertex block is incomplete.');
  const view = new DataView(buffer);
  const positions = new Float32Array(vertexCount * 3);
  const normals = new Float32Array(vertexCount * 3);
  const colors = new Float32Array(vertexCount * 3);
  const minimum = [Infinity, Infinity, Infinity];
  const maximum = [-Infinity, -Infinity, -Infinity];
  for (let vertex = 0; vertex < vertexCount; vertex++) {
    let offset = dataStart + vertex * stride;
    const values = {};
    for (const property of vertexProperties) {
      values[property.name] = readValue(view, offset, property.type);
      offset += property.size;
    }
    const target = vertex * 3;
    positions[target] = values.x; positions[target + 1] = values.y; positions[target + 2] = values.z;
    normals[target] = values.nx ?? 0; normals[target + 1] = values.ny ?? 0; normals[target + 2] = values.nz ?? 1;
    colors[target] = (values.red ?? 64) / 255; colors[target + 1] = (values.green ?? 170) / 255; colors[target + 2] = (values.blue ?? 157) / 255;
    for (let axis = 0; axis < 3; axis++) {
      minimum[axis] = Math.min(minimum[axis], positions[target + axis]);
      maximum[axis] = Math.max(maximum[axis], positions[target + axis]);
    }
  }
  let offset = dataStart + vertexCount * stride;
  const triangles = [];
  for (let face = 0; face < faceCount; face++) {
    const count = readValue(view, offset, faceCountType);
    offset += sizes[faceCountType];
    const polygon = [];
    for (let index = 0; index < count; index++) {
      polygon.push(readValue(view, offset, faceIndexType));
      offset += sizes[faceIndexType];
    }
    for (let index = 1; index + 1 < polygon.length; index++) triangles.push(polygon[0], polygon[index], polygon[index + 1]);
  }
  return {
    positions,
    normals,
    colors,
    indices: triangles.length ? new Uint32Array(triangles) : null,
    vertexCount,
    triangleCount: triangles.length / 3,
    center: minimum.map((value, axis) => (value + maximum[axis]) / 2),
    extent: Math.max(...maximum.map((value, axis) => value - minimum[axis])) || 1,
  };
}

function compile(type, source) {
  const shader = gl.createShader(type);
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(shader));
  return shader;
}

function initializeGl() {
  if (!gl) throw new Error('WebGL is unavailable. Open the presentation in a current Chrome, Edge, or Firefox browser.');
  if (!gl.getExtension('OES_element_index_uint')) throw new Error('This browser cannot display the full survey mesh.');
  const vertex = compile(gl.VERTEX_SHADER, `
    attribute vec3 aPosition; attribute vec3 aNormal; attribute vec3 aColor;
    uniform mat4 uMatrix; uniform float uPointSize;
    varying vec3 vColor; varying float vLight;
    void main(){
      gl_Position = uMatrix * vec4(aPosition, 1.0);
      gl_PointSize = uPointSize;
      vColor = aColor;
      vec3 light = normalize(vec3(-0.35, -0.25, 0.90));
      vLight = 0.58 + 0.55 * abs(dot(normalize(aNormal), light));
    }
  `);
  const fragment = compile(gl.FRAGMENT_SHADER, `
    precision mediump float; varying vec3 vColor; varying float vLight; uniform bool uPoints;
    void main(){
      if(uPoints && distance(gl_PointCoord, vec2(0.5)) > 0.5) discard;
      vec3 color = min(vColor * vLight + vec3(0.035, 0.045, 0.045), vec3(1.0));
      gl_FragColor = vec4(color, 1.0);
    }
  `);
  program = gl.createProgram();
  gl.attachShader(program, vertex); gl.attachShader(program, fragment); gl.linkProgram(program);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(program));
  gl.enable(gl.DEPTH_TEST);
  gl.enable(gl.CULL_FACE);
  gl.cullFace(gl.BACK);
}

function upload(data) {
  const makeBuffer = (target, values) => {
    const buffer = gl.createBuffer(); gl.bindBuffer(target, buffer); gl.bufferData(target, values, gl.STATIC_DRAW); return buffer;
  };
  geometry = {
    ...data,
    positionBuffer: makeBuffer(gl.ARRAY_BUFFER, data.positions),
    normalBuffer: makeBuffer(gl.ARRAY_BUFFER, data.normals),
    colorBuffer: makeBuffer(gl.ARRAY_BUFFER, data.colors),
    indexBuffer: data.indices ? makeBuffer(gl.ELEMENT_ARRAY_BUFFER, data.indices) : null,
  };
}

function identity() { return new Float32Array([1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1]); }
function multiply(a,b){const out=new Float32Array(16);for(let c=0;c<4;c++)for(let r=0;r<4;r++)out[c*4+r]=a[r]*b[c*4]+a[4+r]*b[c*4+1]+a[8+r]*b[c*4+2]+a[12+r]*b[c*4+3];return out;}
function perspective(fovy,aspect,near,far){const f=1/Math.tan(fovy/2);return new Float32Array([f/aspect,0,0,0,0,f,0,0,0,0,(far+near)/(near-far),-1,0,0,2*far*near/(near-far),0]);}
function translate(x,y,z){const m=identity();m[12]=x;m[13]=y;m[14]=z;return m;}
function scale(value){const m=identity();m[0]=m[5]=m[10]=value;return m;}
function rotateX(angle){const c=Math.cos(angle),s=Math.sin(angle);return new Float32Array([1,0,0,0,0,c,s,0,0,-s,c,0,0,0,0,1]);}
function rotateZ(angle){const c=Math.cos(angle),s=Math.sin(angle);return new Float32Array([c,s,0,0,-s,c,0,0,0,0,1,0,0,0,0,1]);}

function bindAttribute(name, buffer) {
  const location = gl.getAttribLocation(program, name);
  gl.bindBuffer(gl.ARRAY_BUFFER, buffer); gl.enableVertexAttribArray(location); gl.vertexAttribPointer(location, 3, gl.FLOAT, false, 0, 0);
}

function render() {
  requestAnimationFrame(render);
  if (!geometry || !program) return;
  const ratio = Math.min(window.devicePixelRatio || 1, 2);
  const width = Math.max(1, Math.floor(canvas.clientWidth * ratio));
  const height = Math.max(1, Math.floor(canvas.clientHeight * ratio));
  if (canvas.width !== width || canvas.height !== height) { canvas.width = width; canvas.height = height; }
  gl.viewport(0, 0, width, height);
  gl.clearColor(0.025, 0.095, 0.13, 1);
  gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
  const normalized = multiply(scale(1 / geometry.extent), translate(-geometry.center[0], -geometry.center[1], -geometry.center[2]));
  const model = multiply(rotateX(pitch), multiply(rotateZ(yaw), normalized));
  const matrix = multiply(perspective(Math.PI / 3, width / height, .01, 30), multiply(translate(0, 0, -distance), model));
  gl.useProgram(program);
  gl.uniformMatrix4fv(gl.getUniformLocation(program, 'uMatrix'), false, matrix);
  const points = activeMode !== 'mesh';
  gl.uniform1f(gl.getUniformLocation(program, 'uPointSize'), points ? Math.max(2, ratio * 1.35) : 1);
  gl.uniform1i(gl.getUniformLocation(program, 'uPoints'), points);
  bindAttribute('aPosition', geometry.positionBuffer);
  bindAttribute('aNormal', geometry.normalBuffer);
  bindAttribute('aColor', geometry.colorBuffer);
  if (!points && geometry.indexBuffer) {
    gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, geometry.indexBuffer);
    gl.drawElements(gl.TRIANGLES, geometry.indices.length, gl.UNSIGNED_INT, 0);
  } else {
    gl.disable(gl.CULL_FACE); gl.drawArrays(gl.POINTS, 0, geometry.vertexCount); gl.enable(gl.CULL_FACE);
  }
}

async function selectMode(mode) {
  activeMode = mode;
  document.querySelectorAll('.view-switch button').forEach(button => button.classList.toggle('active', button.dataset.mode === mode));
  loading.hidden = false;
  loading.querySelector('strong').textContent = mode === 'mesh' ? 'Loading metric surface' : `Loading ${mode} layer`;
  errorBox.hidden = true;
  try {
    if (!cache.has(mode)) {
      const response = await fetch(sources[mode]);
      if (!response.ok) throw new Error(`Could not load ${sources[mode]}.`);
      cache.set(mode, parsePly(await response.arrayBuffer()));
    }
    upload(cache.get(mode));
    loading.hidden = true;
  } catch (error) {
    loading.hidden = true; errorBox.hidden = false; errorBox.textContent = error.message;
  }
}

function resetView() { yaw = 2.45; pitch = -0.93; distance = 1.72; }
canvas.addEventListener('pointerdown', event => { dragging = true; lastPointer = [event.clientX,event.clientY]; canvas.setPointerCapture(event.pointerId); });
canvas.addEventListener('pointermove', event => { if(!dragging)return; yaw += (event.clientX-lastPointer[0])*.007; pitch = Math.max(-1.48,Math.min(1.48,pitch+(event.clientY-lastPointer[1])*.007)); lastPointer=[event.clientX,event.clientY]; });
canvas.addEventListener('pointerup', () => { dragging = false; });
canvas.addEventListener('pointercancel', () => { dragging = false; });
canvas.addEventListener('wheel', event => { event.preventDefault(); distance=Math.max(.72,Math.min(6,distance+event.deltaY*.003)); }, { passive:false });
canvas.addEventListener('dblclick', resetView);
document.querySelectorAll('.view-switch button').forEach(button => button.addEventListener('click', () => selectMode(button.dataset.mode)));

fetch('assets/presentation_report.json').then(response => response.json()).then(report => {
  document.querySelector('#footprint').textContent = `${(report.extent_east_m/1000).toFixed(2)} × ${(report.extent_north_m/1000).toFixed(2)} km`;
  document.querySelector('#triangle-count').textContent = report.mesh_triangles.toLocaleString();
  document.querySelector('#point-count').textContent = report.points_retained.toLocaleString();
  document.querySelector('#gps-fit').textContent = `${report.alignment.verified_horizontal_median_m.toFixed(2)} m`;
  document.querySelector('#coverage').textContent = `${report.dsm.coverage_percent.toFixed(2)}%`;
  document.querySelector('#registered').textContent = `${report.reconstruction.registered_images} / ${report.reconstruction.registered_images}`;
  document.querySelector('#reprojection').textContent = `${report.reconstruction.mean_reprojection_error_px.toFixed(2)} px`;
  document.querySelector('#crs').textContent = report.crs.replace('EPSG:32611','UTM 11N');
}).catch(() => {});

try { initializeGl(); selectMode('mesh'); requestAnimationFrame(render); }
catch (error) { loading.hidden = true; errorBox.hidden = false; errorBox.textContent = error.message; }
