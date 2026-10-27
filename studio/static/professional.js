import {smoothPoints, chartGeometry, nearestPoint, appendConsole} from './charts.js';

export const professionalMessages = {
  zh: {enablePro:'专业模式',disablePro:'专业模式 · 已开启',monitor:'训练监控',openMonitor:'查看曲线与控制台',monitorTitle:'训练过程，清晰可见。',monitorSubtitle:'查看真实训练指标与实时引擎输出，也支持回看历史任务。',liveInterval:'每 2 秒刷新',monitorJob:'监控任务',refreshNow:'立即刷新',trainingCurves:'训练曲线',metric:'指标',smoothing:'指数平滑',smoothingOff:'关闭 · 原始数据',noTrainingData:'尚无训练曲线。训练开始并写入 TensorBoard 指标后会自动显示。',chartHint:'横轴为真实训练步数；浅线为原始值，深线为平滑值。移动指针查看采样点。',liveConsole:'实时控制台',consoleHint:'仅显示引擎输出，不提供命令执行。暂停仅停止日志跟随，不影响任务。',autoScroll:'自动滚动',pauseConsole:'暂停跟随',resumeConsole:'继续跟随',clearConsole:'清空视图',downloadLog:'下载完整日志',noMonitorJobs:'尚无任务；可以先创建素材处理或训练任务。',consoleWaiting:'等待引擎输出…',consolePaused:'日志跟随已暂停，训练和曲线刷新仍继续。',consoleTail:'仅保留最近 200,000 字符；完整内容可下载。',consoleTruncated:'已跳到最近日志；前面的内容请下载完整日志查看。',monitorError:'监控刷新失败，将自动重试：',monitorEpoch:'训练轮数',monitorStep:'训练步数',monitorProgress:'训练进度',monitorLoss:'最新指标',monitorSource:'指标来源',notTraining:'此任务不是训练任务，可以在下方查看控制台。',noSelection:'请选择任务',points:'点',lastUpdated:'更新于',sourceNone:'等待实际指标',sourceTensorboard:'TensorBoard 事件',sourceConsole:'训练控制台',sourceMissing:'没有指标',chartStep:'步数',chartValue:'数值',chartRaw:'原始值',chartSmoothed:'平滑值',chartWallTime:'记录时间',proEmpty:'没有真实数据时不会显示模拟曲线。',metricTotal:'生成器总损失',metricDisc:'判别器损失',metricMel:'Mel 损失',metricFM:'特征匹配损失',metricKL:'KL 损失',metricAdv:'生成器对抗损失',metricLR:'学习率',metricGradG:'生成器梯度',metricGradD:'判别器梯度',metricAvg:'50 步均值'},
  en: {enablePro:'Professional mode',disablePro:'Professional mode · ON',monitor:'Training monitor',openMonitor:'Curves & console',monitorTitle:'A clear view of every training run.',monitorSubtitle:'Inspect actual training metrics and live engine output, including past jobs.',liveInterval:'Refreshes every 2 seconds',monitorJob:'Monitored job',refreshNow:'Refresh now',trainingCurves:'Training curves',metric:'Metric',smoothing:'Exponential smoothing',smoothingOff:'Off · raw values',noTrainingData:'No training curves yet. Metrics appear after training writes TensorBoard events.',chartHint:'X-axis: observed training steps. Light line: raw values; dark line: smoothed values. Hover to inspect a sample.',liveConsole:'Live console',consoleHint:'Read-only engine output. Pausing log follow does not pause the job.',autoScroll:'Auto-scroll',pauseConsole:'Pause follow',resumeConsole:'Resume follow',clearConsole:'Clear view',downloadLog:'Download full log',noMonitorJobs:'No jobs yet. Create a dataset preparation or training job first.',consoleWaiting:'Waiting for engine output…',consolePaused:'Log follow is paused. Training and curve updates continue.',consoleTail:'Only the latest 200,000 characters are retained here; download the full log for everything.',consoleTruncated:'Skipped to the recent log tail. Download the full log for earlier output.',monitorError:'Monitor refresh failed; retrying automatically: ',monitorEpoch:'Epoch',monitorStep:'Training step',monitorProgress:'Training progress',monitorLoss:'Latest metric',monitorSource:'Metric source',notTraining:'This is not a training job. Its live console is available below.',noSelection:'Select a job',points:'points',lastUpdated:'Updated',sourceNone:'Waiting for actual metrics',sourceTensorboard:'TensorBoard events',sourceConsole:'Training console',sourceMissing:'No metrics',chartStep:'Step',chartValue:'Value',chartRaw:'Raw',chartSmoothed:'Smoothed',chartWallTime:'Recorded',proEmpty:'No simulated curves are shown when real data is unavailable.',metricTotal:'Generator total loss',metricDisc:'Discriminator loss',metricMel:'Mel loss',metricFM:'Feature matching loss',metricKL:'KL loss',metricAdv:'Generator adversarial loss',metricLR:'Learning rate',metricGradG:'Generator gradient',metricGradD:'Discriminator gradient',metricAvg:'50-step average'}
};
const $=id=>document.getElementById(id);
const escape=text=>String(text??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const number=value=>Number.isFinite(value)?Number(value).toLocaleString(undefined,{maximumSignificantDigits:6}):'—';

export class ProfessionalMonitor {
  constructor({language,api,fileUrl,uiText}) {
    this.language=language; this.api=api; this.fileUrl=fileUrl;this.uiText=uiText;
    this.jobs=[]; this.id=null; this.active=false; this.paused=false; this.cursor=null;
    this.buffer=''; this.metrics=null; this.generation=0; this.pending=false; this.trimmed=false;
    this.lastUpdated=null; this.logExists=false;
    $('curve-smoothing').value=localStorage.getItem('cover-studio-smoothing')||'0.6';
    $('monitor-job').addEventListener('change',()=>this.selectJob($('monitor-job').value));
    $('monitor-metric').addEventListener('change',()=>this.draw());
    $('curve-smoothing').addEventListener('change',()=>{localStorage.setItem('cover-studio-smoothing',$('curve-smoothing').value);this.draw();});
    $('monitor-refresh').addEventListener('click',()=>this.refresh());
    $('console-pause').addEventListener('click',()=>{this.paused=!this.paused;this.labels();if(!this.paused)this.refresh();});
    $('console-clear').addEventListener('click',()=>{this.buffer='';this.trimmed=false;this.showConsole();});
    $('training-chart').addEventListener('pointermove',e=>this.hover(e));
    this.timer=setInterval(()=>{if(this.active && !document.hidden)this.refresh();},2000);
    document.addEventListener('visibilitychange',()=>{if(this.active&&!document.hidden)this.refresh();});
  }
  t(key) {return professionalMessages[this.language()][key]||key;}
  setActive(value) {
    const changed=this.active!==value; this.active=value;
    if(value&&changed)this.refresh();
  }
  updateState(state) {
    this.jobs=state.jobs||[];
    const selection=this.id;
    const options=this.jobs.map(j=>[j.id,`${j.request.name||j.id.slice(0,8)} · ${this.uiText(j.kind)} · ${this.uiText(j.status)}`]);
    const signature=JSON.stringify(options)+this.language();
    if(signature!==this.jobSignature) {
      this.jobSignature=signature;
      $('monitor-job').replaceChildren();
      if(!options.length)$('monitor-job').add(new Option(this.t('noMonitorJobs'),''));
      for(const [id,label] of options)$('monitor-job').add(new Option(label,id));
      $('monitor-job').disabled=!options.length;
      if(options.some(([id])=>id===selection))$('monitor-job').value=selection;
      else if(options.length) {
        const preferred=this.jobs.find(j=>j.kind==='train'&&['running','queued'].includes(j.status))||this.jobs.find(j=>j.kind==='train')||this.jobs[0];
        this.selectJob(preferred.id);
      } else if(this.id)this.selectJob(null);
    }
    this.labels();
    this.displayMetrics();
  }
  selectJob(id) {
    if(this.id===id)return;
    this.id=id||null; this.generation++; this.cursor=null;this.buffer='';this.metrics=null;
    this.logExists=false;this.trimmed=false;this.lastUpdated=null;
    if(id)$('monitor-job').value=id;
    $('console-error').hidden=true; $('monitor-warning').hidden=true;
    this.displayMetrics();this.showConsole();this.labels();
    if(this.active)this.refresh();
  }
  labels() {
    $('console-pause').textContent=this.t(this.paused?'resumeConsole':'pauseConsole');
    $('console-pause').disabled=!this.id;
    $('console-clear').disabled=!this.id;
    $('monitor-refresh').disabled=!this.id;
    const job=this.jobs.find(j=>j.id===this.id);
    $('monitor-status').textContent=job?`${this.uiText(job.kind)} · ${this.uiText(job.status)}`:this.t('noSelection');
    $('monitor-status').className='status '+(job?.status||'');
    $('monitor-console').setAttribute('aria-label',this.t('liveConsole'));
    this.showConsole();
  }
  async refresh() {
    if(!this.active||!this.id||this.pending)return;
    this.pending=true;
    const generation=this.generation, id=this.id, readingConsole=!this.paused;
    try {
      const tasks=[this.api(`/api/jobs/${id}/metrics`)];
      if(readingConsole)tasks.push(this.api(`/api/jobs/${id}/console${this.cursor===null?'':'?cursor='+this.cursor}`));
      const results=await Promise.allSettled(tasks);
      if(generation!==this.generation)return;
      const errors=[];
      if(results[0].status==='fulfilled') {
        this.metrics=results[0].value;this.lastUpdated=new Date();this.displayMetrics();
      } else errors.push(results[0].reason.message);
      if(readingConsole&&results[1].status==='fulfilled') {
        const log=results[1].value;
        if(log.reset)this.buffer='';
        const appended=appendConsole(this.buffer,log.text);
        this.buffer=appended.text;this.cursor=log.cursor;this.logExists=log.exists;
        this.trimmed=appended.trimmed||log.truncated||this.trimmed;
        $('console-download').href=this.fileUrl(`jobs/${id}/worker.log`)+'?download=true';
        this.showConsole();
      } else if(readingConsole)errors.push(results[1].reason.message);
      $('console-error').hidden=!errors.length;
      $('console-error').textContent=errors.length?this.t('monitorError')+errors.join(' / '):'';
    } finally {
      this.pending=false;
      if(generation!==this.generation&&this.active)this.refresh();
    }
  }
  showConsole() {
    const console=$('monitor-console'), nearEnd=console.scrollHeight-console.scrollTop-console.clientHeight<40;
    const text=this.buffer||this.t('consoleWaiting');
    if(console.textContent!==text) {
      console.textContent=text;
      if($('console-autoscroll').checked&&(nearEnd||!this.buffer))console.scrollTop=console.scrollHeight;
    }
    $('console-state').textContent=this.paused?this.t('consolePaused'):this.trimmed?this.t('consoleTruncated'):this.t('consoleTail');
    $('console-download').hidden=!this.logExists;
  }
  metricLabel(tag) {
    const keys={'loss/g/total':'metricTotal','loss/d/adv':'metricDisc','loss/g/mel':'metricMel','loss/g/fm':'metricFM','loss/g/kl':'metricKL','loss/g/adv':'metricAdv','learning_rate':'metricLR','grad/norm_g':'metricGradG','grad/norm_d':'metricGradD'};
    const normalized=tag.replace('loss_avg_50/','loss/').replace('grad_avg_50/','grad/');
    return (keys[normalized]?this.t(keys[normalized]):tag)+(tag.includes('_avg_50/')?` · ${this.t('metricAvg')}`:'');
  }
  displayMetrics() {
    const series=this.metrics?.series||[], previous=$('monitor-metric').value;
    const signature=JSON.stringify(series.map(s=>s.tag))+this.language();
    if(signature!==this.metricSignature) {
      this.metricSignature=signature;$('monitor-metric').replaceChildren();
      if(!series.length)$('monitor-metric').add(new Option(this.t('sourceNone'),''));
      for(const item of series)$('monitor-metric').add(new Option(this.metricLabel(item.tag),item.tag));
      const preferred=series.find(s=>s.tag===previous)||series.find(s=>s.tag==='loss/g/total')||series[0];
      if(preferred)$('monitor-metric').value=preferred.tag;
      $('monitor-metric').disabled=!series.length;
    }
    const p=this.metrics?.progress||{};
    const cards=[['monitorEpoch',p.epoch!=null?`${p.epoch} / ${p.total_epochs??'—'}`:'—'],['monitorStep',number(p.step)],['monitorProgress',p.percent!=null?`${Number(p.percent).toFixed(1)}%`:'—']];
    $('monitor-summary').innerHTML=cards.map(([key,value])=>`<div class="metric-card"><span>${escape(this.t(key))}</span><strong>${escape(value)}</strong></div>`).join('');
    const sources={tensorboard:'sourceTensorboard',console:'sourceConsole',none:'sourceNone'};
    $('curve-source').textContent=this.t(sources[this.metrics?.source]||'sourceNone')+(this.lastUpdated?` · ${this.t('lastUpdated')} ${this.lastUpdated.toLocaleTimeString()}`:'');
    const warnings=this.metrics?.warnings||[];
    $('monitor-warning').textContent=warnings.join('\n');$('monitor-warning').hidden=!warnings.length;
    this.draw();
  }
  draw() {
    const item=this.metrics?.series?.find(s=>s.tag===$('monitor-metric').value);
    this.raw=item?.points||[];
    this.smoothed=smoothPoints(this.raw,Number($('curve-smoothing').value));
    const geometry=chartGeometry(this.raw);this.geometry=geometry;
    $('curve-container').hidden=!geometry;$('curve-empty').hidden=!!geometry;
    $('curve-empty').textContent=this.metrics?.status==='not_applicable'?this.t('notTraining'):this.t('noTrainingData');
    if(!geometry){$('training-chart').replaceChildren();$('curve-readout').textContent='';return;}
    const g=geometry;
    const line=this.smoothed.map((p,i)=>`${i?'L':'M'}${g.x(p.step).toFixed(2)},${g.y(p.value).toFixed(2)}`).join(' ');
    let grid='';
    for(let i=0;i<=4;i++) {
      const y=g.top+(g.bottom-g.top)*i/4, value=g.maxY-(g.maxY-g.minY)*i/4;
      grid+=`<line x1="${g.left}" y1="${y}" x2="${g.right}" y2="${y}" class="chart-grid"/><text x="${g.left-12}" y="${y+4}" text-anchor="end">${escape(number(value))}</text>`;
      const step=g.minX+(g.maxX-g.minX)*i/4,x=g.x(step);
      grid+=`<text x="${x}" y="${g.bottom+24}" text-anchor="middle">${escape(number(Math.round(step)))}</text>`;
    }
    const latest=this.raw.at(-1);
    $('training-chart').innerHTML=`<title id="chart-title">${escape(this.metricLabel(item.tag))}</title><desc id="chart-desc">${escape(this.t('chartHint'))}</desc>${grid}<path class="chart-raw" d="${g.path}"/><path class="chart-smooth" d="${line}"/><circle id="curve-dot" r="4" cx="${g.x(latest.step)}" cy="${g.y(this.smoothed.at(-1).value)}"/><line id="curve-guide" x1="${g.x(latest.step)}" x2="${g.x(latest.step)}" y1="${g.top}" y2="${g.bottom}" class="chart-guide"/>`;
    this.readout(latest);
  }
  readout(point) {
    const smoothed=this.smoothed.find(p=>p.step===point.step);
    $('curve-readout').textContent=`${this.t('chartStep')} ${number(point.step)} · ${this.t('chartRaw')} ${number(point.value)} · ${this.t('chartSmoothed')} ${number(smoothed?.value)}${Number.isFinite(point.wall_time)?` · ${new Date(point.wall_time*1000).toLocaleTimeString()}`:''}`;
  }
  hover(event) {
    if(!this.geometry||!this.raw.length)return;
    const rect=$('training-chart').getBoundingClientRect();
    const x=(event.clientX-rect.left)/rect.width*1000,g=this.geometry;
    const point=nearestPoint(this.raw,g.minX+(x-g.left)/(g.right-g.left)*(g.maxX-g.minX));
    if(!point)return;this.readout(point);
    const smooth=this.smoothed.find(p=>p.step===point.step)||point;
    $('curve-dot').setAttribute('cx',g.x(point.step));$('curve-dot').setAttribute('cy',g.y(smooth.value));
    $('curve-guide').setAttribute('x1',g.x(point.step));$('curve-guide').setAttribute('x2',g.x(point.step));
  }
}
