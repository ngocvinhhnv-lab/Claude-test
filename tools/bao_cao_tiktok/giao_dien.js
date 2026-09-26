(function(){
function sel(t,s){(document.querySelectorAll('[data-tabs="'+t+'"] > button')).forEach(function(b){var on=b.dataset.t===s;b.setAttribute('aria-selected',on);var p=document.getElementById(b.dataset.t);if(p)p.hidden=!on});}
document.querySelectorAll('[data-tabs]').forEach(function(bar){bar.addEventListener('click',function(e){var b=e.target.closest('button');if(!b)return;sel(bar.dataset.tabs,b.dataset.t);if(bar.dataset.tabs==='main'){try{localStorage.setItem('tt_tab',b.dataset.t)}catch(x){} if(history.replaceState)history.replaceState(null,'','#'+b.dataset.t)}});});
var h=(location.hash||'').slice(1);var st=null;try{st=localStorage.getItem('tt_tab')}catch(x){}
var first=document.querySelector('[data-tabs="main"] > button').dataset.t;
var ok=function(t){return t&&document.querySelector('[data-tabs="main"] > button[data-t="'+t+'"]')};
sel('main',ok(h)?h:(ok(st)?st:first));
document.querySelectorAll('[data-tabs]:not([data-tabs="main"])').forEach(function(bar){sel(bar.dataset.tabs,bar.querySelector('button').dataset.t)});
// table enhancer
document.querySelectorAll('table.x').forEach(function(tb){
 var ths=tb.tHead.rows[0].cells;var body=tb.tBodies[0];
 // bars
 [].forEach.call(ths,function(th,ci){if(!th.classList.contains('b'))return;var mx=0;[].forEach.call(body.rows,function(r){var v=+r.cells[ci].dataset.v||0;if(v>mx)mx=v});[].forEach.call(body.rows,function(r){var c=r.cells[ci];var v=+c.dataset.v||0;c.classList.add('bar');c.style.setProperty('--w',(mx?v/mx*100:0).toFixed(1)+'%')})});
 [].forEach.call(ths,function(th,ci){if(!th.classList.contains('s'))return;th.tabIndex=0;var go=function(){var asc=!th.classList.contains('desc')&&th.classList.contains('asc')?false:!th.classList.contains('asc')&&th.classList.contains('desc')?true:th.classList.contains('n')?false:true;
  [].forEach.call(ths,function(t){t.classList.remove('asc','desc')});th.classList.add(asc?'asc':'desc');
  var rows=[].slice.call(body.rows);rows.sort(function(a,b){var x=a.cells[ci],y=b.cells[ci];var xv=x.dataset.v,yv=y.dataset.v;if(xv!==undefined&&yv!==undefined){xv=+xv;yv=+yv}else{xv=x.textContent.trim().toLowerCase();yv=y.textContent.trim().toLowerCase()}return (xv<yv?-1:xv>yv?1:0)*(asc?1:-1)});rows.forEach(function(r){body.appendChild(r)})};
  th.addEventListener('click',go);th.addEventListener('keydown',function(e){if(e.key==='Enter'||e.key===' '){e.preventDefault();go()}})});
});
// filters
document.querySelectorAll('[data-filter]').forEach(function(box){var tb=document.getElementById(box.dataset.filter);var q=box.querySelector('input'),S=[].slice.call(box.querySelectorAll('select'));var cnt=box.querySelector('.cnt');
 var run=function(){var s=(q&&q.value||'').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g,'').replace(/đ/g,'d');var n=0;[].forEach.call(tb.tBodies[0].rows,function(r){var ok=(!s||r.dataset.q.indexOf(s)>=0)&&S.every(function(x){return !x.value||r.dataset[x.dataset.k||'g']===x.value});r.hidden=!ok;if(ok)n++});if(cnt)cnt.textContent=n+' dòng'};
 if(q)q.addEventListener('input',run);S.forEach(function(x){x.addEventListener('change',run)});run();});
// details: top video/KOC
var D={};try{D=JSON.parse(document.getElementById('t50d').textContent)}catch(e){}
function f(n){return (n||0).toLocaleString('vi-VN')}
document.querySelectorAll('details.it').forEach(function(d){d.addEventListener('toggle',function(){if(!d.open||d.dataset.done)return;d.dataset.done=1;var x=D[d.dataset.i]||{v:[],k:[]};var box=d.querySelector('.vk');
 var v=x.v.length?'<ol>'+x.v.map(function(r){return '<li><a href="https://www.tiktok.com/@'+r[1]+'/video/'+r[0]+'" target="_blank" rel="noopener">'+esc(r[5]||'(không có mô tả)')+'</a> <span class="muted">· @'+esc(r[1])+' · '+f(r[2])+' lượt xem · '+r[4]+'</span></li>'}).join('')+'</ol>':'<p class="muted">Chưa tìm thấy video gắn đúng sản phẩm này trong lượt quét.</p>';
 var k=x.k.length?'<ol>'+x.k.map(function(r){return '<li><a href="https://www.tiktok.com/@'+r[0]+'" target="_blank" rel="noopener">@'+esc(r[0])+'</a> <span class="muted">· '+f(r[1])+' lượt xem · '+f(r[2])+' follower · '+r[3]+' video</span></li>'}).join('')+'</ol>':'<p class="muted">Chưa có KOC.</p>';
 box.innerHTML='<div><h3>Top video gắn SP</h3>'+v+'</div><div><h3>Top KOC theo lượt xem về SP</h3>'+k+'</div>';})});
document.addEventListener('click',function(e){var a=e.target.closest('a[href^="#d-"]');if(!a)return;e.preventDefault();var d=document.getElementById(a.getAttribute('href').slice(1));if(!d)return;var gp=d.closest('.pane[id^="g-"]');if(gp)sel('grp',gp.id);sel('main','top');if(!d.open)d.open=true;d.scrollIntoView({block:'start'});});
function esc(s){return String(s).replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})}
})();
