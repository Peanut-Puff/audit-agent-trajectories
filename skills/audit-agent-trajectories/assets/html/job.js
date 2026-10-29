"use strict";
(() => {
  const D=JSON.parse(document.getElementById("audit-data").textContent),root=document.getElementById("app");
  const colors=["#2671d9","#d15c32"],outcomeColors={通过:"#1b7b60",失败:"#d15c32",未知:"#a6b3c2"};
  const esc=s=>String(s??"未知").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const fmt=n=>typeof n==="number"?n.toLocaleString("zh-CN",{maximumFractionDigits:2}):"未知";
  const finite=v=>typeof v==="number"&&Number.isFinite(v)&&v>=0;
  const labels={identity:"任务身份",trace:"执行记录",delivery:"交付产物",verifier:"独立验证",environment:"环境",integrity:"评测完整性",tokens:"Token",latency:"耗时",complete:"完整",partial:"部分",absent:"缺失",missing:"缺失",contradictory:"矛盾",unsupported:"不支持",not_applicable:"不适用",unknown:"未知",valid:"可分析",degraded:"证据受限",infra_failed:"基础设施失败",behavior_unverified:"行为未经验证",strict:"严格",conditional:"有条件",descriptive_only:"仅描述",ineligible:"不合格",confirmed:"已确认",rejected:"已排除",indeterminate:"未确定",sample_mechanism:"样本机制",hypothesis:"假设"};
  const show=s=>esc(labels[s]||s),tag=s=>`<span class="tag">${show(s)}</span>`;
  const link=t=>`<a href="${esc(D.details_dir+t.detail)}">${esc(t.task_name||t.trial_key)}</a>`;
  const byKey=new Map(D.trials.map(t=>[t.trial_key,t]));
  const metricDefs=[{key:"rounds",label:"模型轮次",unit:"轮"},{key:"duration_sec",label:"完成耗时",unit:"秒"},{key:"input_tokens",label:"报告输入",unit:"token"},{key:"cost_usd",label:"报告费用",unit:"USD"}];
  const count=(rows,key)=>rows.reduce((m,r)=>(m[r[key]]=(m[r[key]]||0)+1,m),{});
  const median=values=>{if(!values.length)return null;const a=values.slice().sort((a,b)=>a-b),i=Math.floor(a.length/2);return a.length%2?a[i]:(a[i-1]+a[i])/2;};
  const detailScope=t=>`${t.trial_key} · ${t.model||t.agent||"未知 agent"}`;
  root.innerHTML=`<div class="eyebrow">TRAJECTORY AUDIT · JOB OVERVIEW</div><h1>${esc(D.scope)}</h1><p class="lead">先看整体结果与覆盖，再找到需要深读的任务。</p><div class="legend">${D.jobs.map((j,i)=>`<span><i class="swatch" style="background:${colors[i]}"></i>${esc(j.label)} · ${esc(j.depth)} · 方法 ${esc(j.methodology_version)}</span>`).join("")}</div><nav><a href="#job-overview">结果与结论</a>${D.pairs.length?'<a href="#job-pairs">配对差异</a>':""}<a href="#job-resources">资源分布</a><a href="#job-coverage">数据覆盖</a><a href="#job-trials">任务列表</a></nav><div class="panel job-filters"><label>查找任务<input id="task-filter" type="search" placeholder="任务、Trial、模型"></label><label>验证结果<select id="outcome-filter"><option value="">全部结果</option><option>通过</option><option>失败</option><option>未知</option></select></label><label>数据状态<select id="health-filter"><option value="">全部状态</option>${[...new Set(D.trials.map(t=>t.health||"unknown"))].sort().map(s=>`<option value="${esc(s)}">${show(s)}</option>`).join("")}</select></label><button id="clear-filters" class="btn">清除筛选</button><p id="job-scope" class="caption" aria-live="polite"></p></div><div id="job-content"></div><dialog id="job-dialog" aria-labelledby="job-dialog-title"><div class="evidence-toolbar"><span class="eyebrow">统计范围与依据</span><button type="button" class="btn" id="job-dialog-close">关闭</button></div><div id="job-dialog-content"></div></dialog>`;
  const content=document.getElementById("job-content");
  let current=[],currentPairs=[],page=0,statsVersion=0,worker=null,workerUrl=null,lastTrigger=null;
  const state={query:"",outcome:"",health:""};
  const section=(id,title,body)=>`<section id="${id}"><h2>${title}</h2>${body}</section>`;
  const action=(kind,key,text)=>`<button class="link-button" data-inspect="${esc(kind)}" data-key="${esc(key)}">${text}</button>`;
  function histogram(rows,definition,color,sharedMax){
    const available=rows.filter(t=>finite(t.metrics[definition.key])&&(definition.key!=="duration_sec"||t.censored===false));
    const missing=rows.filter(t=>!finite(t.metrics[definition.key])).length;
    const excluded=rows.length-missing-available.length;
    const values=available.map(t=>t.metrics[definition.key]);
    const max=sharedMax,min=0,bins=Array.from({length:8},()=>0);
    values.forEach(v=>bins[max===0?0:Math.min(7,Math.floor(v/max*8))]++);
    const peak=Math.max(1,...bins);
    return `<div class="histogram-summary"><strong>${fmt(median(values))}</strong><span>中位数 · ${definition.unit}</span></div><div class="histogram" aria-label="${esc(definition.label)}分布">${bins.map((n,i)=>`<span class="histogram-bin" title="${fmt(max*i/8)}–${fmt(max*(i+1)/8)} ${definition.unit}：${n} 个 Trial"><i style="height:${n/peak*100}%;background:${color}"></i><b>${n||""}</b></span>`).join("")}</div><div class="histogram-axis"><span>${fmt(min)}</span><span>${fmt(max)} ${definition.unit}</span></div><p class="caption">有效 ${available.length} / 缺失 ${missing}${excluded?` / 排除超时或完成状态未知 ${excluded}`:""} · 分母 ${rows.length} Trial</p>`;
  }
  function verifierSummary(rows){
    return `<div class="job-verifier">${["f2p","p2p"].map(prefix=>{
      const valid=rows.filter(t=>finite(t.score?.reconciled?.[prefix+"_passed"])&&finite(t.score?.reconciled?.[prefix+"_total"]));
      const passed=valid.reduce((n,t)=>n+t.score.reconciled[prefix+"_passed"],0),total=valid.reduce((n,t)=>n+t.score.reconciled[prefix+"_total"],0);
      return `<span><strong>${prefix.toUpperCase()}</strong> ${valid.length?`${fmt(passed)} / ${fmt(total)}`:"未记录"}<small>测试计数 · 有效 ${valid.length} / 缺失 ${rows.length-valid.length} Trial</small></span>`;
    }).join("")}<p class="caption">Raw / 对账后结果变化 ${rows.filter(t=>t.score?.changed===true).length} Trial；查看任务详情核对测试覆盖。</p></div>`;
  }
  function overview(){
    const summary=D.jobs.map((job,i)=>{
      const rows=current.filter(t=>t.job_id===job.id),o=count(rows,"outcome"),h=count(rows,"health");
      const recorded=(o.通过||0)+(o.失败||0),rate=recorded?(o.通过||0)/recorded*100:null;
      return `<article class="panel"><h3 class="trial-title" style="border-color:${colors[i]}">${esc(job.label)}</h3><div class="job-kpis"><div><span>验证通过</span><strong>${action("outcome",job.id,`${o.通过||0}<small> / ${recorded}</small>`)}</strong><p>${rate===null?"通过率未知":fmt(rate)+"%"} · 未知 ${o.未知||0}</p></div><div><span>当前 Trial</span><strong>${action("all",job.id,String(rows.length))}</strong><p>原范围 ${D.trials.filter(t=>t.job_id===job.id).length}</p></div><div><span>基础设施失败</span><strong>${action("health",job.id,String(h.infra_failed||0))}</strong><p>行为未验证 ${h.behavior_unverified||0}</p></div></div><div class="outcome-stack" aria-label="结果分布">${["通过","失败","未知"].map(k=>`<span style="width:${rows.length?(o[k]||0)/rows.length*100:0}%;background:${outcomeColors[k]}" title="${k} ${o[k]||0}"></span>`).join("")}</div><div class="legend small">${["通过","失败","未知"].map(k=>`<span><i class="swatch" style="background:${outcomeColors[k]}"></i>${k} ${o[k]||0}</span>`).join("")}</div>${verifierSummary(rows)}</article>`;
    }).join("");
    const issues=current.filter(t=>t.outcome==="失败"||t.health!=="valid"||t.candidates.length);
    const findings=current.flatMap(t=>t.findings.map(f=>({t,f}))).slice(0,5);
    const rootFor=t=>t.findings.filter(f=>f.finding_type==="root_cause"&&!['sample_mechanism','hypothesis'].includes(f.conclusion_level)&&f.adjudication==="confirmed"&&f.root_cause_category&&f.has_direct_evidence);
    const allFailures=D.trials.filter(t=>t.outcome==="失败"&&["valid","degraded"].includes(t.health));
    const fullRoots=D.jobs.every(j=>j.depth==="full")&&allFailures.every(t=>rootFor(t).length===1||t.findings.some(f=>f.finding_type==="root_cause"&&f.adjudication==="indeterminate"&&f.has_direct_evidence));
    const failures=current.filter(t=>t.outcome==="失败"&&["valid","degraded"].includes(t.health));
    const covered=failures.filter(t=>rootFor(t).length===1).length;
    const rootPanel=fullRoots&&failures.length?`<p class="caption">当前可分析失败 ${failures.length} 个，已确认主因 ${covered}，无法归因 ${failures.length-covered}。</p>${[...failures.reduce((m,t)=>{const category=rootFor(t).length===1?rootFor(t)[0].root_cause_category:"无法归因";m.set(category,(m.get(category)||0)+1);return m;},new Map())].map(([k,v])=>`<p>${esc(k)}：${v} / ${failures.length}</p>`).join("")}`:`<p class="caption">全量测量与深读样本分开呈现；根因分布需 full 完成全部可分析失败裁决，筛选不能降低这项覆盖要求。</p>`;
    return section("job-overview","结果与当前结论",`<div class="cols ${D.jobs.length===1?"single":""}">${summary}</div><div class="panel job-conclusions"><h3>当前筛选范围</h3><p>${action("issues","",`${issues.length} 个 Trial 需要关注`)}，其中验证失败 ${current.filter(t=>t.outcome==="失败").length}，证据受限或环境异常 ${current.filter(t=>t.health!=="valid").length}。这些是测量与候选，不代表同一根因。</p>${findings.length?findings.map(({t,f})=>`<p>${tag(labels[f.conclusion_level]||(["confirmed","rejected","indeterminate"].includes(f.adjudication)?"已裁决发现":"未裁决记录"))} ${link(t)} <span class="caption">${esc(D.jobs.find(j=>j.id===t.job_id)?.label)}</span>：${esc(f.summary||f.observation||"已有裁决记录")} <span class="caption">${show(f.adjudication)}</span></p>`).join(""):'<p class="muted">当前范围尚无人工裁决结论。</p>'}${rootPanel}${D.unmatched_findings?`<p class="caption">${D.unmatched_findings} 条 findings 未能对应当前 Trial 身份，未纳入。</p>`:""}</div>`);
  }
  function pairSection(){
    if(!D.pairs.length)return "";
    const eligible=currentPairs.filter(p=>["strict","conditional"].includes(p.grade));
    const known=eligible.filter(p=>!["未知或不合格","缺少对应 Trial"].includes(p.outcome));
    const quadrants=["通过 / 通过","通过 / 失败","失败 / 通过","失败 / 失败"];
    return section("job-pairs","配对资格与差异",`<div class="panel"><p>${action("pairs","",`${eligible.length} / ${currentPairs.length} 个 pair 满足配对资格`)} · 结果有效 ${known.length} / 未知 ${eligible.length-known.length}。${Object.entries(count(currentPairs,"grade")).map(([k,v])=>`${labels[k]||k} ${v}`).join(" · ")}</p><div class="quadrants">${quadrants.map((q,i)=>`<button class="quadrant" data-inspect="quadrant" data-key="${esc(q)}"><span>${["共同通过","仅左侧通过","仅右侧通过","共同失败"][i]}</span><strong>${known.filter(p=>p.outcome===q).length}</strong></button>`).join("")}</div><div id="pair-statistics" aria-live="polite">正在更新配对统计…</div><p class="caption">每项单独检查覆盖与口径；完成耗时排除超时/取消。右减左为正表示右侧更多，观察差异不代表因果优越性。</p></div>`);
  }
  function resources(){
    return section("job-resources","轮次、耗时与资源分布",`<div class="resource-grid">${metricDefs.map(def=>`<article class="panel"><h3>${def.label}</h3><div class="cols ${D.jobs.length===1?"single":""}">${D.jobs.map((j,i)=>`<div><div class="caption"><i class="swatch" style="background:${colors[i]}"></i>${esc(j.label)}</div>${histogram(current.filter(t=>t.job_id===j.id),def,colors[i],Math.max(0,...current.filter(t=>finite(t.metrics[def.key])&&(def.key!=="duration_sec"||t.censored===false)).map(t=>t.metrics[def.key])))}${action("metric",j.id+":"+def.key,"查看有效 Trial 与排除项")}</div>`).join("")}</div>${def.key==="input_tokens"?'<p class="caption">缓存不重复加总。各 adapter/账本仅作描述，配对差值另行准入。</p>':""}</article>`).join("")}</div>`);
  }
  const dimensions=[...new Set(D.trials.flatMap(t=>Object.keys(t.coverage||{})))];
  function coverage(){
    return section("job-coverage","数据覆盖",`<div class="panel scroll"><table><thead><tr><th>维度</th>${D.jobs.map(j=>`<th>${esc(j.label)}：完整 / 部分 / 缺失 / 矛盾 / 其他</th>`).join("")}</tr></thead><tbody>${dimensions.map(d=>`<tr><td>${labels[d]||esc(d)}</td>${D.jobs.map(j=>{const rows=current.filter(t=>t.job_id===j.id),counts=rows.reduce((m,t)=>(m[t.coverage?.[d]||"unknown"]=(m[t.coverage?.[d]||"unknown"]||0)+1,m),{});return `<td>${action("coverage",j.id+":"+d,`${counts.complete||0} / ${counts.partial||0} / ${(counts.absent||0)+(counts.missing||0)} / ${counts.contradictory||0} / ${rows.length-(counts.complete||0)-(counts.partial||0)-(counts.absent||0)-(counts.missing||0)-(counts.contradictory||0)}`)} <span class="caption">分母 ${rows.length}</span></td>`;}).join("")}</tr>`).join("")}</tbody></table><p class="caption">点击查看 Trial × 维度矩阵。缺失、矛盾和不适用分别保留；完整性数据齐全也不能证明不存在违规。</p></div>`);
  }
  function trialTable(){
    const sorted=current.slice().sort((a,b)=>(a.outcome==="失败"?0:1)-(b.outcome==="失败"?0:1)||String(a.task_name||a.trial_key).localeCompare(String(b.task_name||b.trial_key)));
    const pageCount=Math.ceil(sorted.length/25);page=Math.max(0,Math.min(page,Math.max(0,pageCount-1)));
    return section("job-trials","任务列表与样本下钻",`<div class="panel"><div class="chart-head"><p class="caption">当前 ${current.length} Trial · 已列入深读计划 ${current.filter(t=>t.selected&&t.depth!=="metrics").length} · 有人工发现 ${current.filter(t=>t.findings.length).length}。筛选只改变阅读范围，不改变抽样计划。</p><div class="buttons"><button class="btn" data-page="-1" ${page===0?"disabled":""}>上一页</button><span class="caption">${pageCount?page+1:0} / ${pageCount}</span><button class="btn" data-page="1" ${page+1>=pageCount?"disabled":""}>下一页</button></div></div><div class="scroll"><table><thead><tr><th>任务 / Job</th><th>结果与数据</th><th>轮次 / 耗时 / 输入</th><th>样本与待复核</th><th>详情</th></tr></thead><tbody>${sorted.slice(page*25,page*25+25).map(t=>`<tr><td>${link(t)}<br><span class="caption">${esc(D.jobs.find(j=>j.id===t.job_id)?.label)} · ${esc(t.model)}</span></td><td>${tag(t.outcome)} ${tag(t.health)}</td><td class="number">${fmt(t.metrics.rounds)} 轮 / ${fmt(t.metrics.duration_sec)} 秒${t.censored?"（超时/取消）":""}<br>${fmt(t.metrics.input_tokens)} token</td><td>${t.selected&&t.depth!=="metrics"?"深读计划":"全量测量"}<br>${t.findings.length} 发现 · ${t.candidates.length} 候选</td><td><a href="${esc(D.details_dir+t.detail)}">Trial</a>${D.pairs.find(p=>p.detail&&[p.left_trial_key,p.right_trial_key].includes(t.trial_key))?` · <a href="${esc(D.details_dir+D.pairs.find(p=>p.detail&&[p.left_trial_key,p.right_trial_key].includes(t.trial_key)).detail)}">配对</a>`:""}</td></tr>`).join("")}</tbody></table>${!current.length?'<p class="empty">当前筛选没有匹配的 Trial。</p>':""}</div></div>`);
  }
  function filtered(){
    const q=state.query.toLowerCase();
    return D.trials.filter(t=>(!q||[t.task_name,t.trial_key,t.model,t.agent].join(" ").toLowerCase().includes(q))&&(!state.outcome||t.outcome===state.outcome)&&(!state.health||t.health===state.health));
  }
  function render(){
    current=filtered();const keys=new Set(current.map(t=>t.trial_key));
    currentPairs=D.pairs.filter(p=>[p.left_trial_key,p.right_trial_key].filter(Boolean).every(k=>keys.has(k)));
    document.getElementById("job-scope").textContent=`当前 ${current.length} / ${D.trials.length} Trial${D.pairs.length?` · ${currentPairs.length} / ${D.pairs.length} pair（两侧都在筛选范围）`:""}。所有图表、分母和结论均基于当前筛选。`;
    const focusResources=D.focus.some(f=>["tokens","latency"].includes(f))&&!D.focus.includes("all")&&D.focus.length<=2;
    content.innerHTML=overview()+pairSection()+(focusResources?resources()+coverage():coverage()+resources())+trialTable();
    updateStatistics();
  }
  try{workerUrl=URL.createObjectURL(new Blob([`onmessage=e=>postMessage((${jobStatistics.toString()})(e.data));`],{type:"text/javascript"}));worker=new Worker(workerUrl);worker.onmessage=e=>paintStatistics(e.data);worker.onerror=()=>{worker.terminate();worker=null;const host=document.getElementById("pair-statistics");if(host)host.textContent="配对区间暂不可用，仍可查看每个 pair 的原始值与排除原因。";};}catch{worker=null;}
  function updateStatistics(){
    const version=++statsVersion;if(!D.pairs.length)return;
    const eligible=currentPairs.filter(p=>["strict","conditional"].includes(p.grade));
    const series=[{label:"通过率差",unit:"比例",mean:true,denominator:eligible.length,values:eligible.filter(p=>p.outcome!=="未知或不合格").map(p=>({task:p.task_name,value:(byKey.get(p.right_trial_key)?.outcome==="通过"?1:0)-(byKey.get(p.left_trial_key)?.outcome==="通过"?1:0)}))}];
    for(const label of ["模型轮次","完成耗时","输入 token"]){
      const metricRows=eligible.map(p=>({task:p.task_name,m:p.metrics.find(m=>m.label===label)}));
      series.push({label,unit:label==="模型轮次"?"轮":label==="完成耗时"?"秒":"token",denominator:eligible.length,values:metricRows.filter(r=>r.m?.n_available===1).map(r=>({task:r.task,value:r.m.delta,left:r.m.left,right:r.m.right})),excluded:metricRows.flatMap(r=>r.m?.exclusions||[])});
    }
    const message={version,series,seed:D.bootstrap.seed,samples:D.bootstrap.samples};
    if(worker)worker.postMessage(message);else setTimeout(()=>paintStatistics({version,results:series.map(s=>({label:s.label,unit:s.unit,leftMedian:median(s.values.map(v=>v.left).filter(finite)),rightMedian:median(s.values.map(v=>v.right).filter(finite)),ratio:median(s.values.filter(v=>finite(v.left)&&finite(v.right)&&v.left!==0).map(v=>v.right/v.left)),n:s.values.length,denominator:s.denominator,estimate:s.mean?(s.values.length?s.values.reduce((n,r)=>n+r.value,0)/s.values.length:null):median(s.values.map(r=>r.value)),interval:null,tasks:new Set(s.values.map(v=>v.task)).size,excluded:s.excluded}))}),0);
  }
  function paintStatistics(result){
    if(result.version!==statsVersion)return;
    const host=document.getElementById("pair-statistics");if(!host)return;
    host.innerHTML=`<div class="scroll"><table><thead><tr><th>配对指标</th><th>双方中位数</th><th>右减左 / 比值</th><th>95% 区间</th><th>有效 / 排除 · 任务数</th></tr></thead><tbody>${result.results.map(r=>`<tr><td>${action("pair-metric",r.label,esc(r.label))}</td><td>${r.label==="通过率差"?"—":fmt(r.leftMedian)+" / "+fmt(r.rightMedian)}</td><td>${fmt(r.estimate)} ${esc(r.unit)}${r.label!=="通过率差"?`<br><span class="caption">右/左 ${fmt(r.ratio)}</span>`:""}</td><td>${r.interval?r.interval.map(fmt).join(" ～ "):"未计算"}</td><td>${r.n} / ${r.denominator-r.n}（分母 ${r.denominator}）<br><span class="caption">${r.tasks} 个任务</span></td></tr>`).join("")}</tbody></table></div><p class="caption">固定 seed ${D.bootstrap.seed}，${worker?"按任务聚类重采样 "+D.bootstrap.samples.toLocaleString()+" 次":"当前浏览器无法计算重采样区间，仅显示描述统计"}；每次保留该任务的全部 repeat。连续指标为配对中位差，通过率为均值差；小样本区间不证明总体优越性。</p>`;
  }
  function inspect(kind,key){
    let rows=current,title="当前 Trial",explanation="统计单位为 Trial；仅包含当前筛选范围。",extra="";
    const jobId=key.split(":")[0];
    if(["all","outcome","health","metric","coverage"].includes(kind))rows=rows.filter(t=>t.job_id===jobId);
    if(kind==="outcome"){title="验证结果";explanation="通过率分母为有已知验证结果的 Trial；未知结果单列。F2P/P2P 是测试计数，完整原始与对账后记录见详情。";}
    if(kind==="health"){title="数据健康";explanation="health 与验证结果分别计数；基础设施失败不自动等于 verifier 失败。";}
    if(kind==="issues"){title="需要关注的 Trial";rows=rows.filter(t=>t.outcome==="失败"||t.health!=="valid"||t.candidates.length);explanation="根据验证失败、数据健康或候选信号列出，不把这些信号裁决为共同根因。";}
    if(kind==="metric"){
      const def=metricDefs.find(d=>d.key===key.split(":")[1]);title=def.label+"有效与排除";explanation="缺失不补零；完成耗时排除超时/取消与状态未知。";
      extra=`<table><thead><tr><th>Trial</th><th>值</th><th>纳入状态</th></tr></thead><tbody>${rows.map(t=>`<tr><td>${link(t)}</td><td>${fmt(t.metrics[def.key])} ${def.unit}</td><td>${!finite(t.metrics[def.key])?"缺失":def.key==="duration_sec"&&t.censored!==false?"排除：超时或状态未知":"有效"}</td></tr>`).join("")}</tbody></table>`;
    }
    if(kind==="coverage"){
      title="Trial × 维度覆盖矩阵";explanation="各维度独立保留完整、部分、缺失、矛盾与不适用；完整性覆盖不能证明不存在违规。";
      extra=`<table><thead><tr><th>Trial</th>${dimensions.map(d=>`<th>${labels[d]||esc(d)}</th>`).join("")}</tr></thead><tbody>${rows.map(t=>`<tr><td>${link(t)}</td>${dimensions.map(d=>`<td>${show(t.coverage?.[d]||"unknown")}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
    }
    if(["pairs","quadrant","pair-metric"].includes(kind)){
      title=kind==="quadrant"?key:kind==="pair-metric"?key+"配对口径":"配对资格";explanation="只有严格或有条件 pair 纳入；逐指标缺失、超时和非等价口径各自排除。";
      let pairs=kind==="quadrant"?currentPairs.filter(p=>["strict","conditional"].includes(p.grade)&&p.outcome===key):currentPairs;
      extra=`<table><thead><tr><th>任务</th><th>资格</th><th>结果 / 差异</th><th>排除或限制</th></tr></thead><tbody>${pairs.map(p=>{const m=p.metrics.find(m=>m.label===key);return `<tr><td>${p.detail?`<a href="${esc(D.details_dir+p.detail)}">${esc(p.task_name)}</a>`:esc(p.task_name)}</td><td>${show(p.grade)}</td><td>${m?fmt(m.delta)+" "+m.unit:esc(p.outcome)}</td><td>${esc(m?m.exclusions.join("；"):p.reasons)}</td></tr>`;}).join("")}</tbody></table>`;
    }
    if(!extra)extra=`<table><thead><tr><th>Trial</th><th>验证结果</th><th>数据状态</th></tr></thead><tbody>${rows.map(t=>`<tr><td>${link(t)}<br><span class="caption">${esc(detailScope(t))}</span></td><td>${esc(t.outcome)}</td><td>${show(t.health)}</td></tr>`).join("")}</tbody></table>`;
    document.getElementById("job-dialog-content").innerHTML=`<h2 id="job-dialog-title">${esc(title)}</h2><p class="caption">${esc(explanation)}</p><div class="scroll">${extra}</div>`;
    const dialog=document.getElementById("job-dialog");dialog.showModal();document.body.classList.add("evidence-open");document.getElementById("job-dialog-close").focus({preventScroll:true});
  }
  function close(){document.getElementById("job-dialog").close();document.body.classList.remove("evidence-open");lastTrigger?.focus({preventScroll:true});}
  document.getElementById("job-dialog-close").addEventListener("click",close);
  document.getElementById("job-dialog").addEventListener("cancel",e=>{e.preventDefault();close();});
  root.addEventListener("click",e=>{const inspectButton=e.target.closest("[data-inspect]");if(inspectButton){lastTrigger=inspectButton;inspect(inspectButton.dataset.inspect,inspectButton.dataset.key);}const paging=e.target.closest("[data-page]");if(paging){page+=Number(paging.dataset.page);const top=document.getElementById("job-trials").getBoundingClientRect().top;const host=document.getElementById("job-trials");host.outerHTML=trialTable();scrollBy(0,document.getElementById("job-trials").getBoundingClientRect().top-top);}});
  for(const [id,field] of [["task-filter","query"],["outcome-filter","outcome"],["health-filter","health"]])document.getElementById(id).addEventListener(id==="task-filter"?"input":"change",e=>{state[field]=e.target.value;page=0;render();});
  document.getElementById("clear-filters").addEventListener("click",()=>{Object.keys(state).forEach(k=>state[k]="");["task-filter","outcome-filter","health-filter"].forEach(id=>document.getElementById(id).value="");page=0;render();});
  window.addEventListener("pagehide",()=>{worker?.terminate();if(workerUrl)URL.revokeObjectURL(workerUrl);});
  render();
})();
