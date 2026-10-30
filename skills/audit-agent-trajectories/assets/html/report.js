"use strict";
(() => {
  const D = JSON.parse(document.getElementById("audit-data").textContent);
  const root = document.getElementById("app");
  const colors = ["#2671d9", "#d15c32"];
  const esc = s => String(s ?? "未知").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const fmt = n => typeof n === "number" ? n.toLocaleString("zh-CN", {maximumFractionDigits:3}) : esc(n);
  const short = n => n >= 1e6 ? (n / 1e6).toFixed(1) + "M" : n >= 1e3 ? (n / 1e3).toFixed(1) + "k" : fmt(n);
  const ref = (id, text="证据与口径") => `<a href="#${esc(id)}" data-evidence="${esc(id)}">${esc(text)}</a>`;
  const empty = text => `<p class="empty">${esc(text)}</p>`;
  const tag = (text, cls="") => `<span class="tag ${esc(cls)}">${esc(text)}</span>`;
  const hasValue = v => v !== undefined && v !== null && v !== "" && (!Array.isArray(v) || v.length > 0);
  const words = {confirmed:"已确认",rejected:"已排除",indeterminate:"尚不能确定",limited:"有限",high:"高",medium:"中",low:"低",complete:"完整",partial:"部分缺失",absent:"缺失",missing:"缺失",contradictory:"相互矛盾",unknown:"未知",valid:"可分析",degraded:"证据受限",infra_failed:"基础设施失败",behavior_unverified:"行为未经验证",strict:"严格配对",conditional:"有条件配对",descriptive_only:"仅并列描述",ineligible:"不符合配对条件",heuristic:"自动候选",includes_cache:"输入已包含缓存",excludes_cache:"输入不包含缓存",editing:"编辑",verification:"验证",exploration:"探索",other:"其他",manual:"人工标注"};
  const textValue = v => typeof v === "boolean" ? (v?"是":"否") : typeof v === "number" ? fmt(v) : esc(words[v] || v);
  const readable = v => Array.isArray(v) ? `<ul class="plain-list">${v.filter(hasValue).map(x=>`<li>${readable(x)}</li>`).join("")}</ul>` : v && typeof v === "object" ? kv(v) : textValue(v);
  const kv = obj => Object.entries(obj || {}).filter(([,v]) => hasValue(v)).map(([k,v]) => `<div class="kv"><strong>${esc(k)}</strong><div>${readable(v)}</div></div>`).join("");
  const columns = fn => `<div class="cols ${D.trials.length===1?"single":""}">${D.trials.map((t,i)=>`<article class="panel trial-${i===1?"b":"a"}"><h3 class="trial-title">${esc(t.trial_key)} · ${esc(t.model)}</h3>${fn(t,i)}</article>`).join("")}</div>`;
  const section = (id,title,body) => `<section id="${id}"><h2>${title}</h2>${body}</section>`;
  const validCounts = D.trials.reduce((c,t)=>(c[t.outcome]=(c[t.outcome]||0)+1,c),{});
  const healthCounts = D.trials.reduce((c,t)=>(c[t.health]=(c[t.health]||0)+1,c),{});
  const header = `<div class="eyebrow">TRAJECTORY AUDIT · ${esc(D.presentation_version)}</div><h1>${esc(D.scope)}轨迹审计</h1><p class="lead">从结果与数据覆盖，走到任务推进、交付链和支持结论的证据。</p><div class="tags">${D.trials.map(t=>tag(`${t.trial_key} · ${t.depth} · 方法 ${t.methodology_version}`)).join("")}</div><nav><a href="#overview">结果与范围</a><a href="#task-comparison">时序分段</a><a href="#semantic-alignment">同目标对齐</a><a href="#resources">资源与曲线</a><a href="#health">健康与 verifier</a><a href="#delivery">交付与耗时</a><a href="#findings">裁决与候选</a></nav>`;
  const topFindings = D.trials.flatMap(t=>t.findings.slice(0,5).map(f=>({t,f}))).slice(0,5);
  const overview = section("overview","结果与结论可信范围",`<div class="panel"><h3>全量测量 · 当前 ${D.trials.length} 个 Trial</h3><p>Verifier：通过 ${validCounts["通过"]||0} / 失败 ${validCounts["失败"]||0} / 未知 ${validCounts["未知"]||0}。健康：基础设施失败 ${healthCounts.infra_failed||0} / 行为未经验证 ${healthCounts.behavior_unverified||0}。</p><p class="caption">Verifier 结果与健康状态分别计数，不能相加为互斥结果分类。${D.trials.map(t=>ref(t.score_ref,t.trial_key)).join(" · ")}</p><p>metrics 仅展示确定性指标；standard 中的深读机制适用于对应样本；full 仍需要原始证据闭环。此页只包含单 Trial 或一对 Trial，不生成总体根因分布。</p>${topFindings.length?`<h3>优先结论</h3>${topFindings.map(({t,f})=>`<p>${tag(f.level)} ${ref(f.ref,f.summary||f.finding_id||"Finding")}<span class="caption"> · ${esc(t.trial_key)} · ${textValue(f.adjudication)} · ${textValue(f.confidence)}</span></p>`).join("")}`:empty("尚无人工裁决结论；下方展示全量测量和待复核候选。")} ${D.unmatched_findings?`<p class="note">${D.unmatched_findings} 条 findings 缺少当前 trial_key 对应关系，未纳入展示。</p>`:""}</div>${D.pair?`<div class="panel" style="margin-top:18px"><h3>配对资格：${esc(D.pair.grade)}</h3><p>${esc(D.pair.reasons.join("；"))}。结果组合：${esc(D.pair.quadrant)}。</p><p>${ref(D.pair.ref)}</p><div class="scroll"><table><thead><tr><th>指标</th><th>左 / 右</th><th>右减左</th><th>有效 / 排除</th><th>范围与限制</th></tr></thead><tbody>${D.pair.metrics.map(m=>`<tr><td>${ref(m.ref,m.label)}</td><td>${fmt(m.left)} / ${fmt(m.right)}</td><td>${fmt(m.delta)} ${esc(m.unit)}</td><td>${m.n_available} / ${m.n_excluded}（1 pair）</td><td>${esc(m.exclusions.join("；")||"本 pair 描述")}</td></tr>`).join("")}</tbody></table></div></div>`:""}`);
  const resources = section("resources","模型资源与请求曲线",columns(t=>`<div class="metrics">${t.metrics.map(m=>`<div class="metric"><div class="label">${esc(m.label)}</div><div class="value">${ref(m.ref,typeof m.value==="number"?fmt(m.value):"未知")}</div><div class="detail">${esc(m.unit)} · 有效 ${m.valid} / 缺失 ${1-m.valid}（1 Trial）</div></div>`).join("")}</div><p class="caption">Token 覆盖：${esc(t.tokens.status)}；input/cache 关系：${esc(t.semantics)}。Cache read：${fmt(t.tokens.cache_read_tokens)}，cache creation：${fmt(t.tokens.cache_creation_tokens)}。缓存另列，累计图仅累加报告输入。</p>`)+`<div class="panel" style="margin-top:18px"><div class="chart-head"><div><h3>逐请求资源曲线</h3><p class="caption">观察后续轮次是否落在更高输入区间；曲线本身不证明额外轮次的原因。</p></div><div class="curve-controls"><div class="buttons"><button class="btn" id="round-mode" aria-pressed="true">模型请求序号</button><button class="btn" id="time-mode" aria-pressed="false">执行时间</button></div><select id="curve-metric" aria-label="曲线指标"><option value="input">累计输入 Token</option><option value="context">单次请求输入长度</option><option value="output">累计输出 Token</option><option value="reasoning">累计 Reasoning</option><option value="uncached">累计未缓存输入</option></select></div></div><div class="legend" id="curve-legend"></div><div id="context-chart" class="plot"></div><div id="chart-detail" class="chart-detail" aria-live="polite">悬停查看数值，点击曲线区域或用方向键定位请求，展开对应证据。</div><p id="curve-coverage" class="caption"></p></div>`);
  const coverageKeys = [...new Set(D.trials.flatMap(t=>Object.keys(t.coverage||{})))];
  const health = section("health","数据健康、覆盖与 verifier",`<div class="panel scroll"><table><thead><tr><th>Trial / health</th>${coverageKeys.map(k=>`<th>${esc(k)}</th>`).join("")}</tr></thead><tbody>${D.trials.map(t=>`<tr><td>${ref(t.coverage_ref,t.trial_key)}<br>${tag(t.health)}</td>${coverageKeys.map(k=>`<td>${tag(t.coverage[k]||"unknown",["complete","partial","absent","contradictory"].includes(t.coverage[k])?t.coverage[k]:"unknown")}</td>`).join("")}</tr>`).join("")}</tbody></table><p class="caption">complete / partial / absent / contradictory / 不适用须逐维解释。完整性覆盖 complete 也不证明无违规；未观察到证据不能当作绿色安全结论。</p></div>`+columns(t=>`<p>${tag(t.outcome)} ${ref(t.score_ref,"Raw / reconciled 与测试覆盖")}</p><div class="scroll"><table><thead><tr><th>Verifier 字段</th><th>Raw</th><th>Reconciled</th></tr></thead><tbody>${[...new Set([...Object.keys(t.score.raw||{}),...Object.keys(t.score.reconciled||{})])].map(k=>`<tr><td>${esc(k)}</td><td>${fmt((t.score.raw||{})[k])}</td><td>${fmt((t.score.reconciled||{})[k])}</td></tr>`).join("")}</tbody></table></div><p class="caption">对账变化：${esc(t.score.changed)}；对账文档：${esc(t.score.reconciliation_documented)}；CTRF 失败测试：${fmt(t.score.failed_tests_in_ctrf)}。</p><div class="facts">${kv({任务目标:t.contract.task_contract,验证解释:t.contract.verifier_explanation})}</div><p>${ref(t.contract_ref,"任务契约与失败解释标注")}</p>`));
  const phaseMetrics = {
    input_observed:{label:"输入 Token",missing:"input_missing",unit:"token"},
    output_observed:{label:"输出 Token",missing:"output_missing",unit:"token"},
    reasoning_observed:{label:"Reasoning（输出子项）",missing:"reasoning_missing",unit:"token"},
    uncached_observed:{label:"非缓存输入",missing:"uncached_missing",unit:"token"},
    rounds:{label:"模型请求",unit:"次"},duration_sec:{label:"观察时间窗口",unit:"秒"}
  };
  const phaseOptions = Object.entries(phaseMetrics).map(([k,v])=>`<option value="${k}">${esc(v.label)}</option>`).join("");
  function rangeLabel(p){return `${esc(p.session_id)} · R${fmt(p.start_round)}–${fmt(p.end_round)}`;}
  function stageValue(p,key){
    if(!p)return "无独立对应段";
    const v=p[key],m=phaseMetrics[key],missing=m.missing?p[m.missing]:0;
    return typeof v==="number"?`${fmt(v)} ${m.unit}${missing?` · 缺 ${missing} 轮`:""}`:"未记录";
  }
  const phases = section("task-comparison","人工语义时序",`<div class="panel stage-intro"><div class="chart-head"><div><p>按实际目标、方案实验、集成、测试返修和交付状态变化细分。每侧保持自己的时序，阶段数和编号不要求对应。</p><p class="caption">按观察证据人工标注；自动 E/B/I/V/P 仅作辅助。未标注时不从工具类别推断语义。</p></div><select id="stage-metric" aria-label="阶段消耗指标">${phaseOptions}</select></div></div><div id="semantic-timeline" class="cols semantic-timeline ${D.trials.length===1?"single":""}"></div><div class="stage-footnotes">${D.trials.map(t=>`<p>${esc(t.trial_key)} · ${ref(t.reconciliation_ref,`已归属 ${t.reconciliation.semantic_assigned_rounds} / 未归属或辅助 ${t.reconciliation.unassigned_or_auxiliary_rounds} 轮`)} · ${ref(t.auto_ref,"自动阶段依据（启发式）")}</p>`).join("")}</div>`);
  const alignment = D.trials.length===2?section("semantic-alignment","同目标对齐",`<div class="panel"><div class="chart-head"><p class="caption">按人工映射或唯一同名目标对齐；不改写原时序。多个阶段归并时列出全部原范围；一侧缺少对应工作保持未知。</p><select id="alignment-metric" aria-label="同目标对齐指标">${phaseOptions}</select></div><div class="scroll"><table><thead><tr><th>语义目标</th><th>左侧</th><th>右侧</th><th>差额 · 占总差异</th><th>对比解释</th></tr></thead><tbody id="semantic-alignment-body"></tbody></table></div><p id="alignment-share-note" class="caption"></p></div>`):"";
  function renderStages(){
    const key=document.getElementById("stage-metric").value,m=phaseMetrics[key];
    const max=Math.max(0,...D.trials.flatMap(t=>t.semantic_stages.map(p=>p[key]).filter(v=>typeof v==="number")));
    document.getElementById("semantic-timeline").innerHTML=D.trials.map((t,i)=>`<article class="panel trial-${i===1?"b":"a"}"><h3 class="trial-title">${esc(t.trial_key)} · ${t.semantic_stages.length} 段</h3>${t.semantic_stages.length?t.semantic_stages.map((p,j)=>{
      const missing=m.missing?p[m.missing]:0,width=typeof p[key]==="number"&&max>0?p[key]/max*100:0;
      return `<div class="semantic-phase"><span class="semantic-number" style="color:${colors[i]}">${String(j+1).padStart(2,"0")}</span><div><h4>${ref(p.ref,p.title||"未命名阶段")}</h4><div class="caption">${rangeLabel(p)} · ${p.rounds} 请求 · ${fmt(p.tool_calls)} 工具</div><div class="stage-track"><i class="stage-fill ${missing?"incomplete":""}" style="width:${width}%;background-color:${colors[i]}"></i></div><div class="caption">${m.label} ${ref(p.ref,stageValue(p,key))}</div>${p.actions?`<p>${esc(p.actions)}</p>`:""}${p.result?`<p class="semantic-result">${esc(p.result)}</p>`:""}</div></div>`;
    }).join(""):empty(t.depth==="metrics"?"metrics 模式不生成语义阶段。":"尚无人工语义标注；请先深读原始轨迹，未自动填充。")}</article>`).join("");
  }
  function renderAlignment(){
    const host=document.getElementById("semantic-alignment-body");if(!host)return;
    const key=document.getElementById("alignment-metric").value,account=D.alignment_contributions?.[key];
    const signed=n=>typeof n==="number"?(n>0?"+":n<0?"−":"")+fmt(Math.abs(n)):"未计算";
    const percentage=n=>typeof n==="number"?(n>0?"+":n<0?"−":"")+fmt(Math.abs(n*100))+"%":"未计算";
    const max=Math.max(0,...(D.semantic_alignment||[]).flatMap(g=>g.sides.map(p=>p?.[key]).filter(v=>typeof v==="number")));
    host.innerHTML=(D.semantic_alignment||[]).map((g,index)=>{const c=account?.items[index];return `<tr><td>${ref(g.ref,g.title)}</td>${g.sides.map((p,i)=>`<td>${p?`<b style="color:${colors[i]}">${stageValue(p,key)}</b><div class="caption">${p.ranges.map(r=>ref(r.ref,`${r.session_id} R${r.start_round}–${r.end_round}`)).join(" + ")}</div><div class="stage-track"><i class="stage-fill" style="width:${typeof p[key]==="number"&&max>0?p[key]/max*100:0}%;background-color:${colors[i]}"></i></div>`:empty("无独立对应段")}</td>`).join("")}<td>${c?`${ref(account.ref,signed(c.delta))}<div>${percentage(c.share)}</div>${c.structural_absence?'<div class="caption">已证实一侧独有工作</div>':""}${c.exclusions.length?`<div class="caption">${esc(c.exclusions.join("；"))}</div>`:""}`:empty("未提供可比差额")}</td><td>${esc(g.summary||"仅并列描述；编号与时序不决定对应关系。")}</td></tr>`;}).join("")||`<tr><td colspan="5">未提供人工语义阶段，保留空缺。</td></tr>`;
    if(account&&typeof account.denominator==="number"){
      if(typeof account.residual_delta==="number")host.innerHTML+=`<tr><td>辅助 / 未归属账本差额</td><td colspan="2">未强塞入语义阶段</td><td>${signed(account.residual_delta)}<div>${percentage(account.residual_share)}</div></td><td>与总差异同范围的剩余量；不直接解释为浪费。</td></tr>`;
      host.innerHTML+=`<tr><td><b>总差异</b></td><td colspan="2">${esc(account.scope)}</td><td><b>${ref(account.ref,signed(account.denominator))}</b><div>${account.denominator===0?"占比无定义":"100%"}</div></td><td>右侧减左侧；${account.complete_partition?"各目标与辅助差额闭合":"部分目标未满足比较条件，不补零"}。</td></tr>`;
    }
    document.getElementById("alignment-share-note").textContent=account?account.note+(account.exclusions.length?" 当前不可计算："+account.exclusions.join("；"):""):"当前指标未提供可比差额，不计算占比。";
  }
  const delivery = section("delivery","交付链与生命周期耗时",columns(t=>`<div class="chain"><span>修改：${fmt(t.process.mutations)}</span><span>持久化：未知</span><span>验证：${fmt(t.process.validations)}</span><span>捕获：${t.delivery?.path?"已记录":"缺失"}</span><span>verifier：${esc(t.outcome)}</span></div><p>最终修改后识别到验证：${esc(t.process.validation_after_last_mutation)}。同一 revision / patch 对齐：未知。</p><p>${ref(t.delivery_ref,"修改 → 持久化 → 验证 → 捕获 → verifier")}</p><h3>阶段耗时（独立展示）</h3>${Object.entries(t.latency.phase_duration_sec||{}).map(([k,v])=>`<div class="time-row"><span>${esc(k)}</span><span class="track"><i style="width:${typeof v==="number"&&t.latency.duration_sec>0?Math.max(0,Math.min(100,v/t.latency.duration_sec*100)):0}%"></i></span><span>${fmt(v)} 秒</span></div>`).join("")}<p class="caption">${ref(t.timing_ref,"开始/结束、完成或超时与来源")}。阶段区间可能重叠，不将它们堆叠成互斥总时长。等待与未解释时间：未知。</p>`));
  const findings = section("findings","结论与待复核问题",columns(t=>`${t.findings.length?t.findings.map(f=>`<article class="find">${tag(f.level)} ${tag(words[f.adjudication]||f.adjudication||"未裁决")}<h4>${ref(f.ref,f.summary||f.finding_id||"未命名结论")}</h4>${hasValue(f.observation)?`<p>${esc(f.observation)}</p>`:""}${hasValue(f.interpretation)?`<p>${esc(f.interpretation)}</p>`:""}${hasValue(f.confidence)?`<p class="caption">置信度：${textValue(f.confidence)} · ${ref(f.ref,"查看依据与其他解释")}</p>`:""}</article>`).join(""):empty(t.depth==="metrics"?"本页仅展示确定性指标。":"尚无人工裁决结论。")}${t.candidates.length?`<details class="candidate-list"><summary>${t.candidates.length} 项待复核候选</summary>${t.candidates.map(c=>`<div class="find"><p>${ref(c.ref,c.candidate_type)}</p><p>${esc(c.summary)}</p></div>`).join("")}</details>`:""}`));
  const evidenceDialog = `<dialog id="evidence-dialog" aria-labelledby="evidence-title"><div class="evidence-toolbar"><span class="eyebrow">依据与口径</span><button type="button" class="btn" id="evidence-close" aria-label="关闭依据，返回报告">关闭</button></div><div id="evidence-content"></div></dialog>`;
  root.innerHTML = (D.overview_href?`<a class="back-link" href="${esc(D.overview_href)}">← 返回 Job 总览</a>`:"")+header+overview+phases+alignment+resources+health+delivery+findings+`<footer>当前范围：${esc(D.scope)} · ${D.trials.length} Trial。点击数字或结论可查看依据与口径。</footer>`+evidenceDialog;
  document.getElementById("stage-metric").addEventListener("change",renderStages);renderStages();
  document.getElementById("alignment-metric")?.addEventListener("change",renderAlignment);renderAlignment();
  const evidenceById = new Map(D.evidence.map(e=>[e.id,e]));
  const dialog = document.getElementById("evidence-dialog");
  let evidenceTrigger=null, previousHash="";
  const ownerOf = id => D.trials.find(t=>Object.entries(t).some(([k,v])=>k.endsWith("_ref")&&v===id)||t.metrics.some(m=>m.ref===id)||t.findings.some(f=>f.ref===id)||t.candidates.some(c=>c.ref===id)||t.semantic_stages.some(p=>p.ref===id)||t.curves.some(c=>c.points.some(p=>p.ref===id)));
  const summaryRows = e => {
    const f=e.facts||{};
    if(f.round_key){
      return {请求:`第 ${f.round_index} 轮`,输入:hasValue(f.input_tokens)?`${fmt(f.input_tokens)} token`:"未记录",输出:hasValue(f.output_tokens)?`${fmt(f.output_tokens)} token`:null,Reasoning:hasValue(f.reasoning_tokens)?`${fmt(f.reasoning_tokens)} token`:null,未缓存输入:hasValue(f.uncached_input_tokens)?`${fmt(f.uncached_input_tokens)} token`:null,执行时间:hasValue(f.elapsed_sec)?`${fmt(f.elapsed_sec)} 秒`:null,自动阶段:f.stage?({E:"探索",B:"基线验证",I:"实现",V:"验证与返修",P:"稳定通过后继续工作"}[f.stage]||f.stage):null,动作类型:words[f.action]||f.action};
    }
    if(Object.hasOwn(f,"denominator")&&Object.hasOwn(f,"value"))return {数值:hasValue(f.value)?`${fmt(f.value)} ${f.unit||""}`:"未记录",统计范围:`${f.denominator} 个 Trial；有效 ${f.valid}，缺失 ${f.missing}`};
    if(e.title.startsWith("Finding"))return {观察事实:f.observation,解释:f.interpretation,裁决:words[f.adjudication]||f.adjudication,支持证据:f.direct_evidence,其他解释:f.alternative_explanations,置信度:words[f.confidence]||f.confidence,限制:f.limitations,首错决策:f.first_error_decision,关键实现:f.key_implementation,验证后果:f.verifier_consequence};
    if(f.raw||f.reconciled){
      const score=f.reconciled||{}, raw=f.raw||{};
      const result=v=>typeof v!=="number"?"未知":v>0?"通过":"失败";
      const tests=prefix=>hasValue(score[prefix+"_total"])?`${fmt(score[prefix+"_passed"])} / ${fmt(score[prefix+"_total"])} 通过`:"未记录";
      return {原始结果:result(raw.reward),对账后结果:result(score.reward),功能测试:tests("f2p"),回归测试:tests("p2p"),记录中的失败测试:f.failed_tests_in_ctrf,结果是否变化:f.changed};
    }
    if(f.coverage){
      const labels={identity:"任务身份",trace:"执行记录",delivery:"交付产物",verifier:"独立验证",environment:"环境",integrity:"评测完整性",tokens:"Token 用量",latency:"耗时"};
      return {数据状态:words[f.health]||f.health,...Object.fromEntries(Object.entries(f.coverage).map(([k,v])=>[labels[k]||k,words[v]||v]))};
    }
    if(e.title.startsWith("语义阶段"))return {目标:f.goal,关键动作:f.actions,结果:f.result,会话:f.session_id,请求范围:`R${f.start_round}–${f.end_round}`,模型轮次:f.rounds,工具调用:f.tool_calls,已观察输出:hasValue(f.output_observed)?`${fmt(f.output_observed)} token`:"未记录",Reasoning:hasValue(f.reasoning_observed)?`${fmt(f.reasoning_observed)} token`:"未记录",非缓存输入:hasValue(f.uncached_observed)?`${fmt(f.uncached_observed)} token`:"未记录",已观察输入:hasValue(f.input_observed)?`${fmt(f.input_observed)} token`:"未记录",缺少输入的轮次:f.input_missing,耗时:hasValue(f.duration_sec)?`${fmt(f.duration_sec)} 秒`:"未记录",异常:f.anomalies,标注方式:words[f.annotation_method]||f.annotation_method,限制:f.uncertainty};
    if(Object.hasOwn(f,"normalized_rounds"))return {总轮次:f.normalized_rounds,已记录输入的轮次:f.observed_input_rounds,缺少输入的轮次:f.missing_input_rounds,已归属阶段:f.semantic_assigned_rounds,未归属或辅助轮次:f.unassigned_or_auxiliary_rounds,已观察输入:hasValue(f.observed_input)?`${fmt(f.observed_input)} token`:"未记录",与总账的差额:hasValue(f.ledger_minus_observed)?`${fmt(f.ledger_minus_observed)} token`:"未知",说明:f.note};
    if(f.process||f.delivery)return {修改次数:f.process?.mutations,验证次数:f.process?.validations,最后修改后是否验证:f.process?.validation_after_last_mutation,补丁是否捕获:f.delivery?.path?"已记录":"未记录",版本对齐:"现有记录尚不能确认"};
    if(e.title==="生命周期阶段耗时")return {总耗时:hasValue(f.duration_sec)?`${fmt(f.duration_sec)} 秒`:"未记录",是否超时或取消:f.censored,开始时间:f.started_at,结束时间:f.finished_at};
    if(Object.hasOwn(f,"n_available"))return {左侧:hasValue(f.left)?`${fmt(f.left)} ${f.unit}`:"未记录",右侧:hasValue(f.right)?`${fmt(f.right)} ${f.unit}`:"未记录",右减左:hasValue(f.delta)?`${fmt(f.delta)} ${f.unit}`:"未计算",有效配对:f.n_available,排除配对:f.n_excluded,排除原因:f.exclusions};
    if(f.grade)return {配对等级:words[f.grade]||f.grade,结果组合:f.quadrant,理由:f.reasons};
    if(f.task_contract||f.verifier_explanation)return {任务目标:f.task_contract,验证解释:f.verifier_explanation};
    if(Array.isArray(f))return {说明:"这些阶段由修改与验证事件自动划分，仅供复核。",会话:f.map(b=>`${b.session_id}：${b.stage_string}；验证 ${b.validation_rounds} 轮，结果未知 ${b.unknown_validation_rounds} 轮`)};
    if(f.candidate_type)return {观察到的信号:f.summary,状态:"待复核的自动候选",位置:hasValue(f.step_id)?`第 ${f.step_id} 步`:null};
    return {说明:"此项保留了可复核的来源记录，更多内容可在技术详情中查看。"};
  };
  function evidenceBody(e){
    const owner=ownerOf(e.id), f=e.facts||{};
    const finding=owner?.findings.find(item=>item.ref===e.id);
    const title=finding?.summary || (e.title.startsWith("Finding")?"结论依据":e.title==="Raw / reconciled verifier"?"独立验证结果":e.title);
    return `<h2 id="evidence-title">${esc(title)}</h2>${owner?`<p class="caption">${esc(owner.trial_key)} · ${esc(owner.model)}</p>`:""}<div class="evidence-summary">${kv(summaryRows(e))}</div>${e.limitation?`<p class="evidence-limit">${esc(e.limitation)}</p>`:""}<details class="technical-details"><summary>技术详情与来源</summary><p class="caption">供复核原始字段与来源定位。</p><pre>${esc(JSON.stringify({facts:e.facts,source:e.source},null,2))}</pre></details>`;
  }
  function openEvidence(id,trigger){
    const e=evidenceById.get(id);if(!e)return false;
    if(!dialog.open){previousHash=evidenceById.has(location.hash.slice(1))?"":location.hash;evidenceTrigger=trigger||document.activeElement;}
    document.getElementById("evidence-content").innerHTML=evidenceBody(e);
    dialog.dataset.evidenceId=id;
    if(!dialog.open)dialog.showModal();
    dialog.scrollTop=0;document.body.classList.add("evidence-open");
    document.getElementById("evidence-close").focus({preventScroll:true});
    return true;
  }
  function closeEvidence(){
    if(!dialog.open)return;
    dialog.close();document.body.classList.remove("evidence-open");
    if(evidenceById.has(location.hash.slice(1)))history.replaceState(null,"",location.pathname+location.search+previousHash);
    evidenceTrigger?.focus?.({preventScroll:true});
  }
  document.getElementById("evidence-close").addEventListener("click",closeEvidence);
  dialog.addEventListener("cancel",e=>{e.preventDefault();closeEvidence();});
  dialog.addEventListener("click",e=>{if(e.target===dialog){const box=dialog.getBoundingClientRect();if(e.clientX<box.left||e.clientX>box.right||e.clientY<box.top||e.clientY>box.bottom)closeEvidence();}});
  document.addEventListener("click",e=>{const a=e.target.closest("[data-evidence]");if(a&&evidenceById.has(a.dataset.evidence)){e.preventDefault();openEvidence(a.dataset.evidence,a);history.replaceState(null,"","#"+a.dataset.evidence);}});
  const openHash = () => {const id=location.hash.slice(1);if(evidenceById.has(id))openEvidence(id);else if(id==="evidence")document.getElementById("findings").scrollIntoView();};
  window.addEventListener("hashchange",openHash);openHash();

  // Keep all five metrics available even when one has no observed data.
  const curveMetrics = {
    input:{field:"cumulative",label:"累计输入 Token",usage:"input",cumulative:true,note:"只累加报告输入；缓存不重复加总。"},
    context:{field:"input",label:"单次请求输入长度",usage:"input",cumulative:false,note:"这里是报告的输入 token；缓存包含关系未声明时，不能等同完整上下文。"},
    output:{field:"cumulative_output",label:"累计输出 Token",usage:"output",cumulative:true,note:"累加报告输出；Reasoning 单独查看，不再次加入输出。"},
    reasoning:{field:"cumulative_reasoning",label:"累计 Reasoning",usage:"reasoning",cumulative:true,note:"只累加明确记录的 reasoning token；不从总输出或文字长度推算。"},
    uncached:{field:"cumulative_uncached",label:"累计未缓存输入",usage:"uncached",cumulative:true,note:"输入含缓存时减去已记录的缓存读取；输入已排除缓存时直接使用输入。缓存关系未知或读取数矛盾时保留缺失。"}
  };
  const series = D.trials.flatMap((t,i)=>t.curves.map((c,j)=>({label:`${t.trial_key} / ${c.session}`,color:colors[i],dash:j%2?"6 4":null,points:c.points,trial:t})));
  document.getElementById("curve-legend").innerHTML=series.map(s=>`<span><i class="swatch" style="background:${s.color}"></i>${esc(s.label)}</span>`).join("");
  const timeReady=series.length>0&&series.every(s=>s.points.length>0&&s.points.every(p=>typeof p.elapsed==="number"));
  document.getElementById("time-mode").disabled=!timeReady;
  let mode="round", selectedMetric="input", current=[];
  const metricGap=(p,metric)=>metric.cumulative&&(p.gaps?.[metric.usage]??(metric.usage==="input"&&p.gap));
  function curveCoverage(metric){
    const coverage=series.map(s=>{const observed=s.points.filter(p=>typeof p[metric.field]==="number").length;return `${s.label}：有效 ${observed} / 缺失 ${s.points.length-observed}（${s.points.length} 请求）`;}).join("；");
    document.getElementById("curve-coverage").textContent=(coverage||"未提供逐请求记录。")+"。"+metric.note+(metric.cumulative?"缺失处断线，后续累计只代表已观察小计。":"")+(timeReady?"执行时间来自请求时间标注。":"未提供完整请求时间，执行时间轴不可用。");
  }
  const NS="http://www.w3.org/2000/svg";
  const node=(tag,attrs={},text)=>{const n=document.createElementNS(NS,tag);Object.entries(attrs).forEach(([k,v])=>n.setAttribute(k,v));if(text!==undefined)n.textContent=text;return n;};
  const x=p=>mode==="time"?p.elapsed:p.n;
  function draw(hostId,key,title,metric){
    const host=document.getElementById(hostId);host.replaceChildren();
    const usable=series.filter(s=>s.points.some(p=>typeof p[key]==="number"));
    if(!usable.length){host.innerHTML=empty(`未提供${metric.label}的有效逐请求数据，无法绘制；缺失不会补成 0。`);return;}
    const width=Math.max(340,Math.min(1180,host.clientWidth)),height=350,left=57,right=30,top=34,bottom=45,pw=width-left-right,ph=height-top-bottom;
    const xmax=Math.max(1,...series.flatMap(s=>s.points.map(x))),ymax=Math.max(1,...usable.flatMap(s=>s.points.map(p=>p[key]??0)))*1.1;
    const sx=v=>left+v/xmax*pw,sy=v=>top+ph-v/ymax*ph;
    const svg=node("svg",{viewBox:`0 0 ${width} ${height}`,role:"img","aria-label":title});host.append(svg);
    svg.append(node("text",{x:0,y:16,style:"fill:var(--ink);font-weight:600"},title));
    for(let i=0;i<=4;i++){const y=ymax*i/4;svg.append(node("line",{x1:left,x2:width-right,y1:sy(y),y2:sy(y),class:"axis"}));svg.append(node("text",{x:left-8,y:sy(y)+4,"text-anchor":"end"},short(y)));}
    for(let i=0;i<=4;i++){const v=xmax*i/4;svg.append(node("text",{x:sx(v),y:height-23,"text-anchor":i===0?"start":i===4?"end":"middle"},Math.round(v)+(mode==="time"?"s":"")));}
    svg.append(node("text",{x:width-right,y:height-3,"text-anchor":"end"},mode==="time"?"相对执行时间（秒）":"会话内模型请求序号"));
    for(const s of usable){let d="",open=false;for(const p of s.points){if(typeof p[key]!=="number"){open=false;continue;}d+=(open?"L":"M")+sx(x(p))+","+sy(p[key]);open=true;}const attrs={d,fill:"none",stroke:s.color,"stroke-width":2.4};if(s.dash)attrs["stroke-dasharray"]=s.dash;svg.append(node("path",attrs));if(s.points.filter(p=>typeof p[key]==="number").length===1){const p=s.points.find(p=>typeof p[key]==="number");svg.append(node("circle",{cx:sx(x(p)),cy:sy(p[key]),r:3,fill:s.color}));}}
    const guide=node("line",{y1:top,y2:top+ph,class:"guide",visibility:"hidden"});svg.append(guide);
    const tooltip=document.createElement("div");tooltip.className="tooltip";tooltip.hidden=true;host.append(tooltip);
    const overlay=node("rect",{x:left,y:top,width:pw,height:ph,fill:"transparent",tabindex:0,role:"button","aria-label":"曲线详情：左右方向键定位请求，Enter 展开证据"});svg.append(overlay);
    let at=0,marks=[];
    function show(domain){marks.forEach(m=>m.remove());marks=[];guide.setAttribute("x1",sx(domain));guide.setAttribute("x2",sx(domain));guide.setAttribute("visibility","visible");current=[];let body=`<strong>${mode==="time"?"执行 "+fmt(domain)+" 秒":"请求位置 "+fmt(domain)}</strong>`;
      for(const s of usable){const p=s.points.reduce((best,p)=>Math.abs(x(p)-domain)<Math.abs(x(best)-domain)?p:best,s.points[0]);current.push({s,p});body+=`<div>${esc(s.label)} · R${p.n}${p.semantic_title?` · ${esc(p.semantic_title)}`:""}<br>${typeof p[key]==="number"?fmt(p[key]):"缺失"} token${metricGap(p,metric)?"（已观察小计）":""}</div>`;if(typeof p[key]==="number"){const mark=node("circle",{cx:sx(x(p)),cy:sy(p[key]),r:4,fill:s.color});svg.insertBefore(mark,overlay);marks.push(mark);}}
      tooltip.innerHTML=body;tooltip.hidden=false;tooltip.style.left=Math.max(0,Math.min(host.clientWidth-290,sx(domain)+5))+"px";tooltip.style.top="34px";
    }
    function select(){document.getElementById("chart-detail").innerHTML=current.map(({s,p})=>`<p>${esc(s.label)} · R${p.n} · ${esc(metric.label)} ${typeof p[key]==="number"?fmt(p[key]):"缺失"} token${metricGap(p,metric)?"（已观察小计）":""} · ${ref(p.ref,"请求来源与口径")}${p.semantic_ref?" · "+ref(p.semantic_ref,p.semantic_title||"语义阶段"):""}</p>`).join("");}
    overlay.addEventListener("pointermove",e=>{const box=svg.getBoundingClientRect();at=Math.max(0,Math.min(xmax,((e.clientX-box.left)*width/box.width-left)/pw*xmax));show(at);});
    overlay.addEventListener("pointerleave",()=>{tooltip.hidden=true;guide.setAttribute("visibility","hidden");marks.forEach(m=>m.remove());marks=[];});
    overlay.addEventListener("click",()=>{show(at);select();});
    overlay.addEventListener("keydown",e=>{if(["ArrowLeft","ArrowRight","Enter"," "].includes(e.key)){e.preventDefault();if(e.key==="ArrowLeft"||e.key==="ArrowRight")at=Math.max(0,Math.min(xmax,at+(e.key==="ArrowLeft"?-1:1)));show(at);select();}});
  }
  function redraw(){
    const metric=curveMetrics[selectedMetric];
    current=[];
    document.getElementById("chart-detail").textContent="悬停查看数值，点击曲线区域或用方向键定位请求，展开对应证据。";
    curveCoverage(metric);
    draw("context-chart",metric.field,metric.label+" · token",metric);
  }
  document.getElementById("curve-metric").addEventListener("change",e=>{selectedMetric=e.target.value;redraw();});
  for(const [id,next] of [["round-mode","round"],["time-mode","time"]])document.getElementById(id).addEventListener("click",()=>{mode=next;document.getElementById("round-mode").setAttribute("aria-pressed",mode==="round");document.getElementById("time-mode").setAttribute("aria-pressed",mode==="time");redraw();});
  let resizeTimer;window.addEventListener("resize",()=>{clearTimeout(resizeTimer);resizeTimer=setTimeout(redraw,100);});redraw();
})();
