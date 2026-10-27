// Pure curve helpers; no chart service, CDN or remote telemetry.
export function smoothPoints(points, weight = 0) {
  const alpha = Math.min(.99, Math.max(0, Number(weight) || 0));
  let value;
  return points.filter(p => Number.isFinite(p.step) && Number.isFinite(p.value)).map(p => {
    value = value === undefined ? p.value : value * alpha + p.value * (1 - alpha);
    return {...p, value};
  });
}

export function chartGeometry(points, width=1000, height=290) {
  const clean = points.filter(p => Number.isFinite(p.step) && Number.isFinite(p.value));
  if (!clean.length) return null;
  const left=78, right=width-24, top=22, bottom=height-42;
  let minX=Math.min(...clean.map(p=>p.step)), maxX=Math.max(...clean.map(p=>p.step));
  let minY=Math.min(...clean.map(p=>p.value)), maxY=Math.max(...clean.map(p=>p.value));
  if (minX===maxX) { minX=Math.max(0,minX-1); maxX+=1; }
  const pad=Math.max((maxY-minY)*.1, Math.abs(maxY)*.02, 1e-9);
  minY-=pad; maxY+=pad;
  const x=value=>left+(value-minX)/(maxX-minX)*(right-left);
  const y=value=>bottom-(value-minY)/(maxY-minY)*(bottom-top);
  return {left,right,top,bottom,minX,maxX,minY,maxY,x,y,
    path: clean.map((p,i)=>`${i?'L':'M'}${x(p.step).toFixed(2)},${y(p.value).toFixed(2)}`).join(' ')};
}

export function nearestPoint(points, step) {
  return points.reduce((best,p)=>!best || Math.abs(p.step-step)<Math.abs(best.step-step)?p:best,null);
}

export function appendConsole(current, incoming, limit=200000) {
  const text=(current+incoming).replace(/\u001b\[[0-?]*[ -/]*[@-~]/g,'').replace(/\r\n/g,'\n').replace(/\r/g,'\n');
  return {text:text.slice(-limit),trimmed:text.length>limit};
}
