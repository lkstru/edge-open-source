'use strict';
const $=id=>document.getElementById(id);
const names=new Intl.DisplayNames(['zh-TW'],{type:'region'});
const english=new Intl.DisplayNames(['en'],{type:'region'});
const labels={verified:'通過 Mac 驗證',failed:'本次未通過',no_candidates:'來源無候選',not_checked:'尚未測試',source_error:'來源讀取失敗'};
let snapshot=null;
const stale=()=>!snapshot || !Number.isFinite(Date.parse(snapshot.generated_at)) || Date.now()-Date.parse(snapshot.generated_at)>snapshot.stale_after_minutes*60000;
function render(){
 const query=$('search').value.trim().toLowerCase();
 const rows=Object.entries(snapshot.countries).sort((a,b)=>b[1].verified-a[1].verified||a[0].localeCompare(b[0])).filter(([code,data])=>(!query||[code,names.of(code),english.of(code)].join(' ').toLowerCase().includes(query))&&($('filter').value!=='available'||data.verified>0));
 $('countries').replaceChildren();
 for(const [code,data]of rows){
  const tr=document.createElement('tr');
  const country=document.createElement('td');country.textContent=names.of(code);
  const small=document.createElement('small');small.textContent=code;country.append(small);
  const status=document.createElement('td');status.textContent=data.verified&&stale()?'驗證已過期':labels[data.state]||'未知狀態';status.className=data.verified&&!stale()?'available':'unavailable';
  const count=document.createElement('td');count.textContent=`${data.verified} / ${data.tested}`;
  const action=document.createElement('td');
  if(data.verified&&!stale()) {const a=document.createElement('a');a.href=`countries/${code}.conf`;a.textContent='下載';a.download=`lkstru-${code}.conf`;action.append(a);}else{action.textContent='—';}
  tr.append(country,status,count,action);$('countries').append(tr);
 }
 if(!rows.length){const tr=document.createElement('tr');const td=document.createElement('td');td.colSpan=4;td.textContent='沒有符合條件的國家。';tr.append(td);$('countries').append(tr);}
 $('result-count').textContent=`顯示 ${rows.length} / ${Object.keys(snapshot.countries).length} 個國家與地區`;
 const enabled=snapshot.nodes.length>0&&!stale();
 $('download').setAttribute('aria-disabled',String(!enabled));
 if(enabled){$('download').href='subscribe.conf';$('download').download='lkstru-edge.conf';}else $('download').removeAttribute('href');
 $('copy').disabled=!enabled;
 $('notice').className=stale()?'warning':'';
 $('notice').textContent=stale()?'清單已超過 30 分鐘。請在 Mac 重新驗證並發布後再匯入。':snapshot.nodes.length?'只匯出本次通過測試的節點。請在 iPhone 再確認可達性與出口國家。':'本次沒有通過測試的節點；設定會拒絕連線，不會自動直連。';
}
$('search').addEventListener('input',()=>{if(snapshot)render();});
$('filter').addEventListener('change',()=>{if(snapshot)render();});
$('copy').addEventListener('click',async()=>{try{await navigator.clipboard.writeText(new URL('subscribe.conf',location.href).href);$('copy').textContent='已複製';}catch{$('notice').textContent='無法使用剪貼簿，請長按下載連結複製網址。';}});
fetch('nodes.json',{cache:'no-store'}).then(r=>{if(!r.ok)throw Error('HTTP '+r.status);return r.json();}).then(data=>{
 if(!data.countries||!Array.isArray(data.nodes))throw Error('資料格式錯誤');snapshot=data;
 $('node-count').textContent=data.nodes.length;$('country-count').textContent=Object.values(data.countries).filter(c=>c.verified>0).length;
 $('updated').textContent=new Date(data.finished_at||data.generated_at).toLocaleString('zh-TW',{timeZone:'Asia/Taipei',hour12:false})+'（台北）';render();
 setInterval(render,60000);
}).catch(()=>{$('notice').textContent='清單讀取失敗。請重新整理；目前不提供下載。';$('notice').className='warning';$('updated').textContent='無法讀取';$('countries').replaceChildren();});
