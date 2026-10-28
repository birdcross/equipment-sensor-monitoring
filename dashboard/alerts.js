(function(root){
  function detect(hourly,rules){
    const result=[];
    for(const [sensor,rule] of Object.entries(rules)){
      if(!rule.enabled)continue;
      let run=[];
      const flush=()=>{
        if(run.length>=rule.hours){
          const first=run[0],last=run.at(-1),values=run.map(r=>r[sensor+'_mean']);
          result.push({id:JSON.stringify([sensor,first.timestamp,last.timestamp,rule.low,rule.high,rule.hours]),sensor,
            start:first.timestamp,end:last.timestamp,hours:run.length,low:rule.low,high:rule.high,
            min:Math.min(...values),max:Math.max(...values),direction:values[0]<rule.low?'하한 미만':'상한 초과'});
        }run=[];
      };
      for(const r of hourly){
        const v=r[sensor+'_mean'];
        if(r.assumed_off||!Number.isFinite(v)||!(v<rule.low||v>rule.high)){flush();continue;}
        if(run.length){const prev=run.at(-1),pv=prev[sensor+'_mean'];
          if(Date.parse(r.timestamp+'Z')-Date.parse(prev.timestamp+'Z')!==3600000||(pv<rule.low)!==(v<rule.low))flush();}
        run.push(r);
      }flush();
    }
    return result.sort((a,b)=>b.start.localeCompare(a.start)||a.sensor.localeCompare(b.sensor));
  }
  function baseline(hourly,sensors){
    const first=hourly[0].timestamp.slice(0,7),q=(a,p)=>a[Math.floor((a.length-1)*p)];
    return Object.fromEntries(Object.keys(sensors).map(s=>{const a=hourly.filter(r=>!r.assumed_off&&r.timestamp.startsWith(first)).map(r=>r[s+'_mean']).filter(Number.isFinite).sort((a,b)=>a-b);
      return [s,{enabled:true,low:Math.floor(q(a,.01)*100)/100,high:Math.ceil(q(a,.99)*100)/100,hours:2}];}));
  }
  const api={detect,baseline};if(typeof module!=='undefined')module.exports=api;else root.AlertEngine=api;
})(typeof window!=='undefined'?window:globalThis);
