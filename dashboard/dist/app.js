const route = [
  [116,451],[166,428],[224,410],[285,385],[341,351],[371,318],[416,294],[463,264],
  [503,237],[555,213],[595,177],[645,163],[696,133],[731,101],[778,84],[826,67],[884,57]
];

function drawRoute() {
  const svg = document.querySelector('#flight-path');
  if (!svg) return;
  const path = route.map((point,index)=>`${index?'L':'M'} ${point[0]} ${point[1]}`).join(' ');
  svg.innerHTML = `<path d="${path}" fill="none" stroke="#0d9a91" stroke-width="8" stroke-linecap="round" stroke-linejoin="round" opacity=".18"/><path d="${path}" fill="none" stroke="#087e77" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"/><circle cx="${route[0][0]}" cy="${route[0][1]}" r="8" fill="#0d9a91" stroke="white" stroke-width="3"/><circle cx="${route.at(-1)[0]}" cy="${route.at(-1)[1]}" r="8" fill="#e8584e" stroke="white" stroke-width="3"/>`;
}

function drawPointCloud() {
  const canvas = document.querySelector('#point-cloud');
  if (!canvas) return;
  const context = canvas.getContext('2d');
  const {width,height}=canvas;
  context.fillStyle='#09283b'; context.fillRect(0,0,width,height);
  const seed=n=>{const x=Math.sin(n*127.1)*43758.5453;return x-Math.floor(x)};
  for(let i=0;i<3500;i++){
    const x=seed(i)*width;
    const ridge=Math.sin((x/width)*7.2+1.2)*28+height*.5;
    const y=ridge+(seed(i+93)-.5)*(55+90*seed(i+188));
    const shade=Math.floor(105+seed(i+400)*110);
    context.fillStyle=`rgba(${40+Math.floor(seed(i+70)*45)},${shade},${115+Math.floor(seed(i+30)*60)},${.18+seed(i+40)*.65})`;
    context.fillRect(x,y,1.4,1.4);
  }
}

function updateReadyDashboard(report) {
  const metrics = document.querySelectorAll('.metric');
  metrics[2].querySelector('strong').textContent = report.reconstruction.registered_images.toLocaleString();
  metrics[2].querySelector('small').textContent = 'All selected cameras registered';
  metrics[3].querySelector('strong').textContent = report.points_retained.toLocaleString();
  metrics[3].querySelector('span').textContent = 'Filtered 3D points';
  metrics[3].querySelector('small').textContent = `${report.mesh_triangles.toLocaleString()} surface triangles`;

  const status = document.querySelector('.process-panel .pill');
  status.textContent='Presentation ready'; status.classList.add('success');
  const details = [
    ['Inspect mission','MP4 and DJI SRT validated'],
    ['Select sharp frames','242 usable images retained'],
    ['Build sparse 3D model',`${report.reconstruction.mean_reprojection_error_px.toFixed(2)} px mean reprojection error`],
    ['Synchronize and geo-register',`${report.alignment.verified_horizontal_median_m.toFixed(2)} m median GPS consistency`],
    ['Generate surface and deliverables',`${report.mesh_triangles.toLocaleString()} triangles · LAS · GeoTIFF · GLB`],
    ['Confidence filter and report',`${report.confidence.high_confidence_percent.toFixed(1)}% high-confidence points`],
  ];
  document.querySelectorAll('#pipeline li').forEach((item,index)=>{
    item.className='done'; item.querySelector('.step-icon').textContent='✓';
    item.querySelector('strong').textContent=details[index][0]; item.querySelector('small').textContent=details[index][1]; item.querySelector('time').textContent='Done';
  });

  const modelPanel=document.querySelector('.model-panel');
  modelPanel.querySelector('h2').textContent='Presentation 3D result';
  modelPanel.querySelector('.pill').textContent='Metric colored surface';
  modelPanel.querySelector('.model-annotation strong').textContent=`${report.mesh_triangles.toLocaleString()} triangles`;
  modelPanel.querySelector('.model-annotation span').textContent=`${(report.extent_east_m/1000).toFixed(2)} × ${(report.extent_north_m/1000).toFixed(2)} km footprint`;
  modelPanel.querySelector('.model-footer>span').innerHTML='<b class="quality-dot"></b> Metric alignment and exports verified';
  const links=modelPanel.querySelectorAll('.model-links a');
  links[0].href='presentation.html'; links[0].textContent='Open metric 3D viewer →';
  links[1].href='assets/presentation_mesh.glb'; links[1].textContent='Download GLB ↗';

  const accuracy=document.querySelector('.accuracy-panel');
  accuracy.querySelector('h2').textContent='Presentation readiness';
  accuracy.querySelector('.accuracy-score span').textContent='Implemented deliverables';
  accuracy.querySelector('.accuracy-score strong').textContent='100%';
  accuracy.querySelector('.bar i').style.width='100%';
  accuracy.querySelector('.warning').innerHTML=`<b>Verified:</b> real-scale 3D surface, UTM point cloud, LAS and 2 m DSM are ready. GPS agreement is ${report.alignment.verified_3d_rmse_m.toFixed(2)} m RMSE; use independent GCPs before claiming absolute sub-metre accuracy.`;
  document.querySelector('#details-dialog h2').textContent='How metric alignment was verified';
  const paragraphs=document.querySelectorAll('#details-dialog p:not(.eyebrow)');
  paragraphs[0].textContent=`The visual model registered all ${report.reconstruction.registered_images} cameras and ${report.reconstruction.observations.toLocaleString()} feature observations. A similarity transform synchronized the camera path to DJI telemetry with a ${report.alignment.time_shift_seconds.toFixed(3)} second correction.`;
  paragraphs[1].textContent=`The transformed camera path measures ${report.alignment.verified_horizontal_median_m.toFixed(2)} m median horizontal GPS consistency. Ground-control checkpoints remain the correct final validation for survey-grade absolute accuracy.`;
}

function setupDialog() {
  const dialog=document.querySelector('#details-dialog');
  const trigger=document.querySelector('#details-button');
  if (!dialog || !trigger) return;
  trigger.addEventListener('click',()=>dialog.showModal());
  document.querySelector('#close-dialog').addEventListener('click',()=>dialog.close());
}

drawRoute(); drawPointCloud(); setupDialog();
// The legacy presentation report is intentionally not loaded: this mission still needs GPS calibration.
