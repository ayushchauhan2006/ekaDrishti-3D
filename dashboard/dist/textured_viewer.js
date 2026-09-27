const canvas = document.querySelector('#model-canvas');
const scene = document.querySelector('.scene');
const loading = document.querySelector('#loading');
const errorBox = document.querySelector('#scene-error');
const resetButton = document.querySelector('#reset-view');
const measureToggle = document.querySelector('#measure-toggle');
const measureClear = document.querySelector('#measure-clear');
const measureResult = document.querySelector('#measure-result');
const measureState = document.querySelector('#measure-state');
const overlay = document.querySelector('#measure-overlay');
const overlayLine = document.querySelector('#measure-line');
const overlayA = document.querySelector('#measure-a');
const overlayB = document.querySelector('#measure-b');
const inspector = document.querySelector(".inspector");
const inspectorDragHandle = document.querySelector("#inspector-drag-handle");
const inspectorToggle = document.querySelector("#inspector-toggle");
const gl = canvas.getContext('webgl', { antialias: true, alpha: false, preserveDrawingBuffer: true });
const requestedMode = new URLSearchParams(location.search).get("mode");
const modelTitle = document.querySelector("#model-title");
const modelSummary = document.querySelector("#model-summary");
const modelStatus = document.querySelector("#model-status");
const meshTitle = document.querySelector("#mesh-title");
const modelSourceNote = document.querySelector("#model-source-note");
const modelDownload = document.querySelector("#model-download");
const fallbackCatalog = { active_mode: null, models: {} };

let yaw = 3.9, pitch = -1.45, distance = 1.22, panX = 0, panY = 0;
let panning = false, dragging = false, moved = false, lastPointer, pointerStart;
let program, pickProgram, modelTexture, positionBuffer, uvBuffer, pickColorBuffer, vertexCount = 0;
let positions, center = [0,0,0], extent = 1, currentMatrix;
let pickFramebuffer, pickTexture, pickDepth, pickWidth = 0, pickHeight = 0;
let measuring = false, measurementPoints = [], screenPoints = [];

function parseMesh(buffer) {
  const bytes = new Uint8Array(buffer);
  const text = new TextDecoder('ascii').decode(bytes.subarray(0, Math.min(bytes.length, 20000)));
  const marker = 'end_header\n', end = text.indexOf(marker);
  if (end < 0 || !text.includes('format binary_little_endian 1.0')) throw new Error('The textured mesh is not a supported binary little-endian PLY file.');
  const lines = text.slice(0,end).split('\n');
  const vertices = Number(lines.find(line=>line.startsWith('element vertex '))?.split(' ').at(-1));
  const faces = Number(lines.find(line=>line.startsWith('element face '))?.split(' ').at(-1));
  if(!vertices||!faces) throw new Error('The mesh does not contain vertices and triangles.');
  const start=end+marker.length, view=new DataView(buffer), points=new Float32Array(vertices*3);
  const min=[Infinity,Infinity,Infinity],max=[-Infinity,-Infinity,-Infinity];
  for(let i=0;i<vertices;i++) for(let axis=0;axis<3;axis++){
    const value=view.getFloat32(start+i*12+axis*4,true); points[i*3+axis]=value;
    min[axis]=Math.min(min[axis],value); max[axis]=Math.max(max[axis],value);
  }
  let offset=start+vertices*12, writeVertex=0;
  const expandedPositions=new Float32Array(faces*9), uvs=new Float32Array(faces*6), pickColors=new Uint8Array(faces*9);
  for(let face=0;face<faces;face++){
    const count=view.getUint8(offset); offset+=1; const indices=[];
    for(let i=0;i<count;i++){indices.push(view.getInt32(offset,true));offset+=4;}
    const uvCount=view.getUint8(offset);offset+=1;const faceUvs=[];
    for(let i=0;i<uvCount;i++){faceUvs.push(view.getFloat32(offset,true));offset+=4;}
    if(count<3||uvCount<count*2)continue;
    for(let triangle=1;triangle<count-1;triangle++){
      const triangleId=Math.floor(writeVertex/3)+1;
      const rgb=[triangleId&255,(triangleId>>8)&255,(triangleId>>16)&255];
      for(const slot of [0,triangle,triangle+1]){
        const index=indices[slot], p=writeVertex*3, uv=writeVertex*2;
        expandedPositions[p]=points[index*3]; expandedPositions[p+1]=points[index*3+1]; expandedPositions[p+2]=points[index*3+2];
        uvs[uv]=faceUvs[slot*2]; uvs[uv+1]=faceUvs[slot*2+1];
        pickColors[p]=rgb[0];pickColors[p+1]=rgb[1];pickColors[p+2]=rgb[2]; writeVertex++;
      }
    }
  }
  const sortedAxes=[0,1,2].map(axis=>Array.from({length:vertices},(_,i)=>points[i*3+axis]).sort((a,b)=>a-b));const percentileBounds=sortedAxes.map(values=>[values[Math.floor(vertices*.02)],values[Math.ceil(vertices*.98)-1]]);
  center=percentileBounds.map(([low,high])=>(low+high)/2); extent=Math.max(...percentileBounds.map(([low,high])=>high-low))||1;
  return {positions:expandedPositions.subarray(0,writeVertex*3),uvs:uvs.subarray(0,writeVertex*2),pickColors:pickColors.subarray(0,writeVertex*3)};
}

function shader(type,source){const compiled=gl.createShader(type);gl.shaderSource(compiled,source);gl.compileShader(compiled);if(!gl.getShaderParameter(compiled,gl.COMPILE_STATUS))throw new Error(gl.getShaderInfoLog(compiled));return compiled;}
function makeProgram(vertexSource,fragmentSource){const result=gl.createProgram();gl.attachShader(result,shader(gl.VERTEX_SHADER,vertexSource));gl.attachShader(result,shader(gl.FRAGMENT_SHADER,fragmentSource));gl.linkProgram(result);if(!gl.getProgramParameter(result,gl.LINK_STATUS))throw new Error(gl.getProgramInfoLog(result));return result;}
function multiply(a,b){const out=new Float32Array(16);for(let c=0;c<4;c++)for(let r=0;r<4;r++)out[c*4+r]=a[r]*b[c*4]+a[4+r]*b[c*4+1]+a[8+r]*b[c*4+2]+a[12+r]*b[c*4+3];return out;}
function identity(){return new Float32Array([1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1]);}
function perspective(f,a,n,z){const q=1/Math.tan(f/2);return new Float32Array([q/a,0,0,0,0,q,0,0,0,0,(z+n)/(n-z),-1,0,0,2*z*n/(n-z),0]);}
function translate(x,y,z){const m=identity();m[12]=x;m[13]=y;m[14]=z;return m;}
function scale(value){const m=identity();m[0]=m[5]=m[10]=value;return m;}
function rotateX(angle){const c=Math.cos(angle),s=Math.sin(angle);return new Float32Array([1,0,0,0,0,c,s,0,0,-s,c,0,0,0,0,1]);}
function rotateZ(angle){const c=Math.cos(angle),s=Math.sin(angle);return new Float32Array([c,s,0,0,-s,c,0,0,0,0,1,0,0,0,0,1]);}
function wrapTurn(angle){const turn=Math.PI*2;return((angle+Math.PI)%turn+turn)%turn-Math.PI;}
function loadImage(url){return new Promise((resolve,reject)=>{const image=new Image();image.onload=()=>resolve(image);image.onerror=()=>reject(new Error('The terrain texture could not be loaded.'));image.src=url;});}

function assetPath(model,file){return model.asset_base.replace(/\/$/,"")+"/"+file;}
async function selectModel(){
  let catalog=fallbackCatalog;
  try{const response=await fetch("/api/models",{cache:"no-store"});if(!response.ok)throw new Error("catalog unavailable");catalog=await response.json();}catch{}
  const models=catalog&&catalog.models&&typeof catalog.models==="object"?catalog.models:fallbackCatalog.models;
  const available=Object.keys(models).filter(mode=>models[mode]&&models[mode].status==="ready");
  const mode=available.includes(requestedMode)?requestedMode:(available.includes(catalog.active_mode)?catalog.active_mode:(available.includes("precision")?"precision":available[0]));
  if(!mode)throw new Error("Add Video and Telemetry data to make a 3d model");
  const model=Object.assign({label:mode==="rapid"?"Rapid preview":"Precision model",asset_base:"assets"},models[mode]);
  model.mode=mode;
  modelTitle.textContent=model.label+" · photo-textured 3D";
  modelSummary.textContent=(mode==="rapid"?"Fast reconstruction":"High-detail reconstruction")+" · separate "+model.label.toLowerCase()+" output";
  modelStatus.innerHTML="<i></i> "+model.label+" loaded";
  meshTitle.textContent=model.label+" textured mesh";
  const frames=Number(model.frames_selected);
  modelSourceNote.textContent="This is the separately saved "+model.label.toLowerCase()+". "+(Number.isFinite(frames)&&frames>0?frames+" retained frames were used for this result.":"It does not overwrite the other completed quality mode.");
  modelDownload.href=assetPath(model,"dense_textured_mesh.ply");
  document.title="EkaDrishti 3D | "+model.label;
  return model;
}
function loadValidation(model){fetch(assetPath(model,"accuracy_validation.json")).then(response=>response.json()).then(report=>{const state=document.querySelector("#validation-state"),detail=document.querySelector("#validation-detail");if(report.status==="independently_validated"){state.textContent="Independent validation complete";state.classList.add("verified");const metrics=report.three_dimensional||report.distance_error;detail.textContent="RMSE "+metrics.rmse_m.toFixed(3)+" m · P95 "+metrics.p95_m.toFixed(3)+" m · "+metrics.count+" checks";}else{state.textContent="Checkpoint data required";detail.textContent=report.message||"Internal RTK agreement is not independent ground truth.";}}).catch(()=>{});}

function inverse(m){
  const out=new Float32Array(16);const a00=m[0],a01=m[1],a02=m[2],a03=m[3],a10=m[4],a11=m[5],a12=m[6],a13=m[7],a20=m[8],a21=m[9],a22=m[10],a23=m[11],a30=m[12],a31=m[13],a32=m[14],a33=m[15];
  const b00=a00*a11-a01*a10,b01=a00*a12-a02*a10,b02=a00*a13-a03*a10,b03=a01*a12-a02*a11,b04=a01*a13-a03*a11,b05=a02*a13-a03*a12,b06=a20*a31-a21*a30,b07=a20*a32-a22*a30,b08=a20*a33-a23*a30,b09=a21*a32-a22*a31,b10=a21*a33-a23*a31,b11=a22*a33-a23*a32;
  let det=b00*b11-b01*b10+b02*b09+b03*b08-b04*b07+b05*b06;if(!det)return null;det=1/det;
  out[0]=(a11*b11-a12*b10+a13*b09)*det;out[1]=(a02*b10-a01*b11-a03*b09)*det;out[2]=(a31*b05-a32*b04+a33*b03)*det;out[3]=(a22*b04-a21*b05-a23*b03)*det;
  out[4]=(a12*b08-a10*b11-a13*b07)*det;out[5]=(a00*b11-a02*b08+a03*b07)*det;out[6]=(a32*b02-a30*b05-a33*b01)*det;out[7]=(a20*b05-a22*b02+a23*b01)*det;
  out[8]=(a10*b10-a11*b08+a13*b06)*det;out[9]=(a01*b08-a00*b10-a03*b06)*det;out[10]=(a30*b04-a31*b02+a33*b00)*det;out[11]=(a21*b02-a20*b04-a23*b00)*det;
  out[12]=(a11*b07-a10*b09-a12*b06)*det;out[13]=(a00*b09-a01*b07+a02*b06)*det;out[14]=(a31*b01-a30*b03-a32*b00)*det;out[15]=(a20*b03-a21*b01+a22*b00)*det;return out;
}
function transformPoint(m,v){const x=v[0],y=v[1],z=v[2],w=v[3];const out=[m[0]*x+m[4]*y+m[8]*z+m[12]*w,m[1]*x+m[5]*y+m[9]*z+m[13]*w,m[2]*x+m[6]*y+m[10]*z+m[14]*w,m[3]*x+m[7]*y+m[11]*z+m[15]*w];return out.map((value,index)=>index<3?value/out[3]:value);}
function subtract(a,b){return[a[0]-b[0],a[1]-b[1],a[2]-b[2]];}function dot(a,b){return a[0]*b[0]+a[1]*b[1]+a[2]*b[2];}function cross(a,b){return[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];}function normalize(v){const n=Math.hypot(...v)||1;return v.map(x=>x/n);}
function intersectTriangle(origin,direction,a,b,c){const edge1=subtract(b,a),edge2=subtract(c,a),h=cross(direction,edge2),det=dot(edge1,h);if(Math.abs(det)<1e-7)return null;const inv=1/det,s=subtract(origin,a),u=inv*dot(s,h);if(u<0||u>1)return null;const q=cross(s,edge1),v=inv*dot(direction,q);if(v<0||u+v>1)return null;const t=inv*dot(edge2,q);return t>1e-6?[origin[0]+direction[0]*t,origin[1]+direction[1]*t,origin[2]+direction[2]*t]:null;}

function setup(data,image){
  if(!gl)throw new Error('WebGL is unavailable. Open this dashboard in Chrome, Edge or Firefox.');
  program=makeProgram('attribute vec3 aPosition;attribute vec2 aUv;uniform mat4 uMatrix;varying vec2 vUv;void main(){gl_Position=uMatrix*vec4(aPosition,1.0);vUv=aUv;}','precision mediump float;varying vec2 vUv;uniform sampler2D uTexture;void main(){vec4 color=texture2D(uTexture,vUv);if(dot(color.rgb,vec3(.2126,.7152,.0722))<.018)discard;gl_FragColor=color;}');
  pickProgram=makeProgram('attribute vec3 aPosition;attribute vec3 aPickColor;uniform mat4 uMatrix;varying vec3 vColor;void main(){gl_Position=uMatrix*vec4(aPosition,1.0);vColor=aPickColor;}','precision highp float;varying vec3 vColor;void main(){gl_FragColor=vec4(vColor,1.0);}');
  const buffer=(values)=>{const result=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,result);gl.bufferData(gl.ARRAY_BUFFER,values,gl.STATIC_DRAW);return result;};
  positions=data.positions;positionBuffer=buffer(data.positions);uvBuffer=buffer(data.uvs);pickColorBuffer=buffer(data.pickColors);vertexCount=data.positions.length/3;
  modelTexture=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,modelTexture);gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL,true);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,image);gl.enable(gl.DEPTH_TEST);
}
function bind(programValue,name,buffer,size,type=gl.FLOAT,normalized=false){const location=gl.getAttribLocation(programValue,name);gl.bindBuffer(gl.ARRAY_BUFFER,buffer);gl.enableVertexAttribArray(location);gl.vertexAttribPointer(location,size,type,normalized,0,0);}
function resize(){const ratio=Math.min(devicePixelRatio||1,2),width=Math.max(1,Math.floor(canvas.clientWidth*ratio)),height=Math.max(1,Math.floor(canvas.clientHeight*ratio));if(canvas.width!==width||canvas.height!==height){canvas.width=width;canvas.height=height;}return{ratio,width,height};}
function matrixFor(width,height){const model=multiply(rotateX(pitch),multiply(rotateZ(yaw),multiply(scale(1/extent),translate(-center[0],-center[1],-center[2]))));return multiply(perspective(Math.PI/3,width/height,.01,30),multiply(translate(panX,panY,-distance),model));}
function render(){requestAnimationFrame(render);if(!program)return;const{width,height}=resize();currentMatrix=matrixFor(width,height);gl.bindFramebuffer(gl.FRAMEBUFFER,null);gl.viewport(0,0,width,height);gl.clearColor(.024,.11,.16,1);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);gl.useProgram(program);gl.uniformMatrix4fv(gl.getUniformLocation(program,'uMatrix'),false,currentMatrix);bind(program,'aPosition',positionBuffer,3);bind(program,'aUv',uvBuffer,2);gl.activeTexture(gl.TEXTURE0);gl.bindTexture(gl.TEXTURE_2D,modelTexture);gl.drawArrays(gl.TRIANGLES,0,vertexCount);}

function ensurePickTarget(width,height){if(pickFramebuffer&&pickWidth===width&&pickHeight===height)return;if(pickFramebuffer){gl.deleteFramebuffer(pickFramebuffer);gl.deleteTexture(pickTexture);gl.deleteRenderbuffer(pickDepth);}pickWidth=width;pickHeight=height;pickFramebuffer=gl.createFramebuffer();gl.bindFramebuffer(gl.FRAMEBUFFER,pickFramebuffer);pickTexture=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,pickTexture);gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,width,height,0,gl.RGBA,gl.UNSIGNED_BYTE,null);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.NEAREST);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.NEAREST);gl.framebufferTexture2D(gl.FRAMEBUFFER,gl.COLOR_ATTACHMENT0,gl.TEXTURE_2D,pickTexture,0);pickDepth=gl.createRenderbuffer();gl.bindRenderbuffer(gl.RENDERBUFFER,pickDepth);gl.renderbufferStorage(gl.RENDERBUFFER,gl.DEPTH_COMPONENT16,width,height);gl.framebufferRenderbuffer(gl.FRAMEBUFFER,gl.DEPTH_ATTACHMENT,gl.RENDERBUFFER,pickDepth);if(gl.checkFramebufferStatus(gl.FRAMEBUFFER)!==gl.FRAMEBUFFER_COMPLETE)throw new Error('Surface picking framebuffer is incomplete.');}
function pickSurface(clientX,clientY){const rect=canvas.getBoundingClientRect(),{ratio,width,height}=resize();currentMatrix=matrixFor(width,height);ensurePickTarget(width,height);gl.bindFramebuffer(gl.FRAMEBUFFER,pickFramebuffer);gl.viewport(0,0,width,height);gl.disable(gl.DITHER);gl.clearColor(0,0,0,1);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);gl.useProgram(pickProgram);gl.uniformMatrix4fv(gl.getUniformLocation(pickProgram,'uMatrix'),false,currentMatrix);bind(pickProgram,'aPosition',positionBuffer,3);bind(pickProgram,'aPickColor',pickColorBuffer,3,gl.UNSIGNED_BYTE,true);gl.drawArrays(gl.TRIANGLES,0,vertexCount);const pixel=new Uint8Array(4),px=Math.max(0,Math.min(width-1,Math.floor((clientX-rect.left)*ratio))),py=Math.max(0,Math.min(height-1,height-1-Math.floor((clientY-rect.top)*ratio)));gl.readPixels(px,py,1,1,gl.RGBA,gl.UNSIGNED_BYTE,pixel);gl.enable(gl.DITHER);gl.bindFramebuffer(gl.FRAMEBUFFER,null);const triangleId=pixel[0]+(pixel[1]<<8)+(pixel[2]<<16)-1;if(triangleId<0)return null;const index=triangleId*9;if(index+8>=positions.length)return null;const inv=inverse(currentMatrix);if(!inv)return null;const nx=(clientX-rect.left)/rect.width*2-1,ny=1-(clientY-rect.top)/rect.height*2;const near=transformPoint(inv,[nx,ny,-1,1]),far=transformPoint(inv,[nx,ny,1,1]),direction=normalize(subtract(far,near));const a=[positions[index],positions[index+1],positions[index+2]],b=[positions[index+3],positions[index+4],positions[index+5]],c=[positions[index+6],positions[index+7],positions[index+8]];return intersectTriangle(near,direction,a,b,c)||[(a[0]+b[0]+c[0])/3,(a[1]+b[1]+c[1])/3,(a[2]+b[2]+c[2])/3];}

function updateOverlay(){const show=screenPoints.length>0;overlayA.style.display=show?'block':'none';if(show){overlayA.setAttribute('cx',screenPoints[0][0]);overlayA.setAttribute('cy',screenPoints[0][1]);}const complete=screenPoints.length===2;overlayB.style.display=complete?'block':'none';overlayLine.style.display=complete?'block':'none';if(complete){overlayB.setAttribute('cx',screenPoints[1][0]);overlayB.setAttribute('cy',screenPoints[1][1]);overlayLine.setAttribute('x1',screenPoints[0][0]);overlayLine.setAttribute('y1',screenPoints[0][1]);overlayLine.setAttribute('x2',screenPoints[1][0]);overlayLine.setAttribute('y2',screenPoints[1][1]);}}
function clearMeasurement(message='Enable measurement, then select two observed surface points.'){measurementPoints=[];screenPoints=[];measureResult.textContent=message;measureState.textContent=measuring?'Select point 1':'Ready';updateOverlay();}
function addMeasurement(event){if(measurementPoints.length===2)clearMeasurement('Select the first surface point.');measureState.textContent='Reading surface…';const point=pickSurface(event.clientX,event.clientY);if(!point){measureState.textContent='No surface';measureResult.textContent='No triangle was found at that location. Select a visible model surface.';return;}const rect=scene.getBoundingClientRect();measurementPoints.push(point);screenPoints.push([event.clientX-rect.left,event.clientY-rect.top]);updateOverlay();if(measurementPoints.length===1){measureState.textContent='Select point 2';measureResult.textContent=`Point 1: ${point.map(value=>value.toFixed(2)).join(', ')} m`;return;}const delta=subtract(measurementPoints[1],measurementPoints[0]),length=Math.hypot(...delta);measureState.textContent='Measured';measureResult.innerHTML=`<strong>${length.toFixed(3)} m</strong> <span>ΔE ${Math.abs(delta[0]).toFixed(2)} · ΔN ${Math.abs(delta[1]).toFixed(2)} · ΔZ ${Math.abs(delta[2]).toFixed(2)} m</span>`;}

canvas.addEventListener('pointerdown',event=>{dragging=true;moved=false;panning=event.shiftKey||event.button===2;lastPointer=[event.clientX,event.clientY];pointerStart=[event.clientX,event.clientY];canvas.setPointerCapture(event.pointerId);});
canvas.addEventListener('pointermove',event=>{if(!dragging)return;const dx=event.clientX-lastPointer[0],dy=event.clientY-lastPointer[1];if(Math.hypot(event.clientX-pointerStart[0],event.clientY-pointerStart[1])>4)moved=true;if(!measuring||panning){if(panning){panX+=dx/canvas.clientWidth*distance*1.1;panY-=dy/canvas.clientHeight*distance*1.1;}else{yaw=wrapTurn(yaw+dx*.008);pitch=wrapTurn(pitch+dy*.008);}if(measurementPoints.length)clearMeasurement('View changed; select two points again.');}lastPointer=[event.clientX,event.clientY];});
canvas.addEventListener('pointerup',event=>{if(measuring&&!moved&&!panning)addMeasurement(event);dragging=false;panning=false;});canvas.addEventListener('contextmenu',event=>event.preventDefault());
canvas.addEventListener('wheel',event=>{event.preventDefault();distance=Math.max(.06,Math.min(30,distance*Math.exp(event.deltaY*.0015)));if(measurementPoints.length)clearMeasurement('View changed; select two points again.');},{passive:false});
resetButton.addEventListener('click',()=>{yaw=3.9;pitch=-1.45;distance=1.22;panX=0;panY=0;clearMeasurement();});
measureToggle.addEventListener('click',()=>{measuring=!measuring;measureToggle.classList.toggle('active',measuring);measureToggle.textContent=measuring?'Measuring: ON':'Measure distance';scene.classList.toggle('measure-mode',measuring);clearMeasurement(measuring?'Select the first visible surface point.':'Measurement disabled.');});
measureClear.addEventListener('click',()=>clearMeasurement());

let inspectorDrag = null;
function clampInspector(left,top){const rect=inspector.getBoundingClientRect(),margin=10,minTop=86;return[Math.max(margin,Math.min(innerWidth-rect.width-margin,left)),Math.max(minTop,Math.min(innerHeight-rect.height-margin,top))];}
function moveInspector(left,top){const [x,y]=clampInspector(left,top);inspector.style.left=x+"px";inspector.style.top=y+"px";inspector.style.right="auto";}
inspectorDragHandle.addEventListener("pointerdown",event=>{if(event.target.closest("button")||matchMedia("(max-width: 840px)").matches)return;const rect=inspector.getBoundingClientRect();inspectorDrag={pointerId:event.pointerId,offsetX:event.clientX-rect.left,offsetY:event.clientY-rect.top};inspector.classList.add("is-dragging");inspectorDragHandle.setPointerCapture(event.pointerId);event.preventDefault();});
inspectorDragHandle.addEventListener("pointermove",event=>{if(!inspectorDrag||event.pointerId!==inspectorDrag.pointerId)return;moveInspector(event.clientX-inspectorDrag.offsetX,event.clientY-inspectorDrag.offsetY);});
function stopInspectorDrag(event){if(!inspectorDrag||event.pointerId!==inspectorDrag.pointerId)return;inspectorDrag=null;inspector.classList.remove("is-dragging");}
inspectorDragHandle.addEventListener("pointerup",stopInspectorDrag);inspectorDragHandle.addEventListener("pointercancel",stopInspectorDrag);
inspectorToggle.addEventListener("click",()=>{const collapsed=inspector.classList.toggle("is-collapsed");inspectorToggle.textContent=collapsed?"Show":"Hide";inspectorToggle.setAttribute("aria-expanded",String(!collapsed));inspectorToggle.setAttribute("aria-label",collapsed?"Show model inspector":"Hide model inspector");if(inspector.style.left){const rect=inspector.getBoundingClientRect();moveInspector(rect.left,rect.top);}});
addEventListener("resize",()=>{if(matchMedia("(max-width: 840px)").matches){inspector.style.left="";inspector.style.top="";inspector.style.right="";return;}if(inspector.style.left){const rect=inspector.getBoundingClientRect();moveInspector(rect.left,rect.top);}});

selectModel().then(model=>{loadValidation(model);return Promise.all([fetch(assetPath(model,"dense_textured_mesh.ply")).then(response=>{if(!response.ok)throw new Error(model.label+" mesh could not be loaded.");return response.arrayBuffer();}),loadImage(assetPath(model,"dense_texture.png"))]);}).then(([mesh,image])=>{setup(parseMesh(mesh),image);loading.hidden=true;requestAnimationFrame(render);}).catch(error=>{loading.hidden=true;errorBox.hidden=false;errorBox.textContent=error.message;});
const fullscreenButton = document.createElement("button");
fullscreenButton.type = "button";
fullscreenButton.className = "fullscreen-model";
fullscreenButton.textContent = "Fullscreen ⛶";
fullscreenButton.setAttribute("aria-label", "Open model viewer in fullscreen");
document.querySelector(".viewer-header").append(fullscreenButton);
fullscreenButton.addEventListener("click", async () => {
  try {
    if (document.fullscreenElement) await document.exitFullscreen();
    else await document.documentElement.requestFullscreen();
  } catch { /* Fullscreen may be blocked by an older browser. */ }
});
document.addEventListener("fullscreenchange", () => {
  fullscreenButton.textContent = document.fullscreenElement ? "Exit fullscreen ×" : "Fullscreen ⛶";
});
