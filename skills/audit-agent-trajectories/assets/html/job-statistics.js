"use strict";
function jobStatistics(message){
    function med(a){if(!a.length)return null;const b=a.slice().sort((x,y)=>x-y),i=Math.floor(b.length/2);return b.length%2?b[i]:(b[i-1]+b[i])/2;}
    function percentile(a,p){const b=a.slice().sort((x,y)=>x-y),at=(b.length-1)*p,lo=Math.floor(at);return b[lo]+(b[Math.min(lo+1,b.length-1)]-b[lo])*(at-lo);}
    let seed=message.seed>>>0;function random(){seed=(Math.imul(1664525,seed)+1013904223)>>>0;return seed/4294967296;}
    return {version:message.version,results:message.series.map(series=>{
      const grouped=new Map();series.values.forEach(v=>{if(!grouped.has(v.task))grouped.set(v.task,[]);grouped.get(v.task).push(v.value);});const groups=[...grouped.values()];
      const values=series.values.map(v=>v.value),distribution=[];
      if(groups.length){for(let i=0;i<message.samples;i++){const sample=[];for(let j=0;j<groups.length;j++){const group=groups[Math.floor(random()*groups.length)];for(const value of group)sample.push(value);};distribution.push(series.mean?sample.reduce((a,b)=>a+b,0)/sample.length:med(sample));}}
      return {label:series.label,unit:series.unit,leftMedian:med(series.values.map(v=>v.left).filter(v=>typeof v==="number")),rightMedian:med(series.values.map(v=>v.right).filter(v=>typeof v==="number")),ratio:med(series.values.filter(v=>typeof v.left==="number"&&typeof v.right==="number"&&v.left!==0).map(v=>v.right/v.left)),n:values.length,denominator:series.denominator,tasks:groups.length,excluded:series.excluded,estimate:series.mean?(values.length?values.reduce((a,b)=>a+b,0)/values.length:null):med(values),interval:distribution.length?[percentile(distribution,.025),percentile(distribution,.975)]:null};
    })};
  }
